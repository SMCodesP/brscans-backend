"""Verificação de saúde da fonte (URL original) de um Manhwa.

Usa o próprio wrapper, do mesmo jeito que sync_chapters faz em produção:
`get_source_by_link(manhwa.source).chapters(manhwa)`. A função só testa e
classifica; quem chama decide persistir (endpoint/task do painel).
"""

import socket
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlparse

import httpx
import requests
from requests.exceptions import TooManyRedirects
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import SSLError as RequestsSSLError
from requests.exceptions import Timeout as RequestsTimeout

from brscans.wrapper.sources import get_source_by_link

# O wrapper usa timeout=None, que travava a auditoria. 30s é o teto para
# classificar como timeout em vez de fonte morta, e vale para o relógio
# inteiro (conexão + TLE + leitura): sem o deadline, um connect pendurado
# ignora o timeout de leitura e a checagem nunca termina.
REQUEST_TIMEOUT = httpx.Timeout(30.0)
REQUESTS_TIMEOUT = (30, 30)
# Teto da checagem inteira. Webtoon pagina a lista e há wrapper que faz health
# check de várias URLs; passou disso, o admin precisa de resposta, não espera.
CHECK_TIMEOUT = 120
# getaddrinfo não respeita timeout de socket e trava vários minutos quando o
# resolver local engasga (toonclash.com: SERVFAIL nos DNS públicos). Resolver
# antes, com prazo curto, transforma isso em 'dead' determinístico.
DNS_TIMEOUT = 10
# Regra do mutirão: no máximo 1 requisição por domínio a cada 2s.
MIN_INTERVAL = 2.0

# requests segue até 30 saltos; a 4ª visita à mesma URL já é loop.
MAX_LOOP = 3

_last_request: dict[str, float] = {}
# Por thread: a task do painel pode checar vários mangás em paralelo e o log
# de uma checagem não pode se misturar com o da outra.
_state = threading.local()


def _entries() -> list[dict]:
    if not hasattr(_state, "log"):
        _state.log = []
    return _state.log


_CHALLENGE_MARKERS = (
    "just a moment",
    "cf-browser-verification",
    "cf_chl_",
    "challenge-platform",
    "attention required",
    "captcha",
    "cf-turnstile",
)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _throttle(host: str) -> None:
    last = _last_request.get(host)
    if last is not None:
        wait = MIN_INTERVAL - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _last_request[host] = time.monotonic()


def _remember(url, status, final_url, body) -> None:
    log = _entries()
    if len(log) < 200:
        log.append(
            {"url": url, "status": status, "final_url": final_url, "body": body[:4000]}
        )


def _guard_loop(url: str, exc_class) -> None:
    """Aborta um redirect em loop na 4ª visita à mesma URL.

    O requests segue até 30 saltos; com o throttle de 2s por domínio isso
    gastaria um minuto por manga. O loop é sinal de domínio morto, não de
    fonte lenta.
    """
    if sum(entry["url"] == url for entry in _entries()) >= MAX_LOOP:
        raise exc_class("redirect em loop")


@contextmanager
def _capture():
    """Registra toda requisição HTTP do bloco.

    O wrapper mistura cloudscraper/requests e httpx; o `send` é o ponto comum
    de cada biblioteca, então instrumentar ali pega as duas.
    """
    requests_send = requests.sessions.Session.send
    httpx_request = httpx.Client.request

    def remember_attempt(url):
        _remember(url, 0, url, "")

    def req_send(self, request, **kwargs):
        _guard_loop(request.url, TooManyRedirects)
        remember_attempt(request.url)
        _throttle(_host(request.url))
        kwargs.setdefault("timeout", REQUESTS_TIMEOUT)
        response = requests_send(self, request, **kwargs)
        _entries()[-1] = {
            "url": request.url,
            "status": response.status_code,
            "final_url": str(response.url),
            "body": response.text[:4000],
        }
        return response

    def hx_request(self, method, url, **kwargs):
        _guard_loop(str(url), httpx.TooManyRedirects)
        remember_attempt(str(url))
        _throttle(_host(str(url)))
        if kwargs.get("timeout") in (None, httpx.USE_CLIENT_DEFAULT):
            kwargs["timeout"] = REQUEST_TIMEOUT
        response = httpx_request(self, method, url, **kwargs)
        _entries()[-1] = {
            "url": str(response.request.url),
            "status": response.status_code,
            "final_url": str(response.url),
            "body": response.text[:4000],
        }
        return response

    requests.sessions.Session.send = req_send
    httpx.Client.request = hx_request
    try:
        yield
    finally:
        requests.sessions.Session.send = requests_send
        httpx.Client.request = httpx_request


def _exc_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:300].replace("\n", " ")


def _is_challenge(body: str) -> bool:
    lowered = body.lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)


def _is_cloudflare_exc(exc: Exception) -> bool:
    return type(exc).__module__.startswith("cloudscraper")


def _net_status(exc: Exception) -> str | None:
    if isinstance(exc, (RequestsTimeout, httpx.TimeoutException)):
        return "timeout"
    if isinstance(exc, (RequestsSSLError, RequestsConnectionError)):
        return "dead"
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return "dead"
    return None


def _resolves(host: str) -> bool:
    outcome = []

    def lookup():
        try:
            socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
            outcome.append(True)
        except OSError:
            outcome.append(False)

    thread = threading.Thread(target=lookup, daemon=True)
    thread.start()
    thread.join(DNS_TIMEOUT)
    # Sem resposta no prazo é domínio morto para efeito de fonte; o wrapper
    # continuaria travado no getaddrinfo.
    return bool(outcome and outcome[0])


def _redirect_target(entries):
    for entry in entries:
        from_host = _host(entry["url"])
        to_host = _host(entry["final_url"])
        if from_host and to_host and from_host != to_host:
            return from_host, to_host
    return None


def check_source(manhwa) -> dict:
    """Testa `manhwa.source` com o wrapper do próprio site.

    Retorna, no contrato do Manhwa do painel:
      source_status   ok | redirected | not_found | blocked | offline |
                      http_error | timeout | dead | parser_error | no_url
      source_detail   texto curto para o admin (domínio novo, exceção, motivo)
      source_http     código HTTP (None se a conexão nem aconteceu)
      source_chapters capítulos que o parser devolveu (None se falhou)
    """
    url = getattr(manhwa, "source", None) or ""

    def result(status, detail, http=None, chapters=None):
        return {
            "source_status": status,
            "source_detail": detail,
            "source_http": http,
            "source_chapters": chapters,
        }

    if not url:
        return result("no_url", "manhwa sem URL de origem")

    host = _host(url)
    if host and not _resolves(host):
        return result("dead", f"{host}: DNS não resolve o domínio")

    Source = get_source_by_link(url)
    chapters = None
    error = None
    entries = []
    timed_out = False

    def worker():
        nonlocal chapters, error, entries
        entries = _entries()
        entries.clear()
        with _capture():
            try:
                chapters = Source.chapters(manhwa)
            except Exception as exc:  # noqa: BLE001 - relatório, não fluxo de erro
                error = exc

    # Thread daemon: um wrapper travado não segura o worker da task para
    # sempre. timeout_seconds existe desde o Python 3.12; no 3.11 (runtime do
    # Zappa) cai no caminho com thread.
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(CHECK_TIMEOUT)
    if thread.is_alive():
        timed_out = True
        chapters, error = None, None

    if timed_out:
        return result(
            "timeout",
            f"checagem passou de {CHECK_TIMEOUT}s sem terminar",
            entries[0]["status"] if entries else None,
        )

    # Tentativas que nem receberam resposta ficam com status 0.
    answered = [entry for entry in entries if entry["status"]]
    found = len(chapters) if isinstance(chapters, list) else None
    http = answered[0]["status"] if answered else None

    # `Generic.chapter` levanta HTTPStatusError quando a origem e o espelho dão
    # challenge; é bloqueio, não parser (senão o cron insiste a cada 2h).
    if isinstance(error, httpx.HTTPStatusError):
        return result(
            "blocked",
            _exc_text(error),
            error.response.status_code,
        )

    moved = _redirect_target(entries)
    if moved:
        detail = (
            f"{moved[0]} -> {moved[1]} (HTTP {http}, "
            f"{found if found is not None else '?'} capítulos)"
        )
        # Redirecionou mas o wrapper não leu a URL nova: para o pipeline a
        # fonte continua inútil, então o status é de parser, não 'ok'.
        status = "redirected" if found else "parser_error"
        return result(status, detail, http, found)

    if not answered:
        if error is None:
            return result(
                "parser_error",
                f"{type(Source).__name__}.chapters não fez requisição",
            )
        if _is_cloudflare_exc(error):
            return result("blocked", _exc_text(error))
        return result(_net_status(error) or "parser_error", _exc_text(error))

    if isinstance(error, (TooManyRedirects, httpx.TooManyRedirects)):
        return result("redirected", "redirect em loop", http, found)

    for entry in answered:
        status = entry["status"]
        if status in (403, 503):
            if _is_challenge(entry["body"]):
                return result("blocked", f"HTTP {status}: challenge/captcha do Cloudflare", status)
            # Site recusando tudo sem challenge (manhuafast): está fora do ar
            # para nós, não é captcha. A migração trata os dois como mortos,
            # mas o painel precisa dizer a verdade.
            return result(
                "offline",
                f"HTTP {status} sem challenge (fora do ar/bloqueio de IP)",
                status,
            )
        if status in (404, 410):
            return result("not_found", f"HTTP {status}", status)
        if status >= 400:
            return result("http_error", f"HTTP {status}", status)

    if error is not None:
        if _is_cloudflare_exc(error):
            return result("blocked", _exc_text(error), http)
        return result("parser_error", _exc_text(error), http)
    if not chapters:
        return result(
            "parser_error",
            f"HTTP {http} mas 0 capítulos via {type(Source).__name__}",
            http,
            0,
        )
    return result("ok", f"{type(Source).__name__}: {found} capítulos", http, found)
