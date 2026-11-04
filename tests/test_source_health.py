"""Autochecagem do classificador de fonte, sem rede.

Cada caso cobre um braço do check_source: o que o admin vê no painel.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

import django
import httpx

django.setup()

from brscans.wrapper import health  # noqa: E402 - precisa dos apps carregados


class FakeTransport:
    """Responde ao httpx.Client.get sem rede, com uma resposta por chamada."""

    def __init__(self, responses, exc=None):
        self.responses = list(responses)
        self.exc = exc
        self.calls = []

    def request(self, client, method, url, **kwargs):
        self.calls.append(str(url))
        if self.exc:
            raise self.exc
        status, body, final_url = self.responses.pop(0)
        return SimpleNamespace(
            status_code=status,
            url=httpx.URL(final_url),
            text=body,
            headers={},
            request=httpx.Request(method, url),
        )

    def chapters(self, manhwa):
        httpx.get(manhwa.source)
        return [] if self.responses == [] else None


class SourceHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.throttle = health._throttle
        health._throttle = lambda host: None
        self.resolver = mock.patch.object(health, "_resolves", lambda host: True)
        self.resolver.start()

    def tearDown(self) -> None:
        self.resolver.stop()
        health._throttle = self.throttle

    def check(self, url, transport, chapters=None):
        def request(client, method, url, **kwargs):
            return transport.request(client, method, url, **kwargs)

        with (
            mock.patch.object(httpx.Client, "request", request),
            mock.patch.object(
                health,
                "get_source_by_link",
                lambda link: SimpleNamespace(chapters=chapters or transport.chapters),
            ),
        ):
            return health.check_source(SimpleNamespace(source=url))

    def test_sem_url(self) -> None:
        self.assertEqual(
            health.check_source(SimpleNamespace(source=""))["source_status"],
            "no_url",
        )

    def test_dominio_novo_com_parser_quebrado(self) -> None:
        transport = FakeTransport(
            [(200, "<html>sem capítulos</html>", "https://mgread.io/")],
            exc=None,
        )
        result = self.check("https://mangayy.org/manga/x/", transport)
        self.assertEqual(result["source_status"], "parser_error")
        self.assertIn("mangayy.org -> mgread.io", result["source_detail"])

    def test_cloudflare_com_challenge(self) -> None:
        transport = FakeTransport(
            [
                (
                    403,
                    "<title>Just a moment...</title>",
                    "https://manhuafast.net/x",
                )
            ]
        )
        result = self.check("https://manhuafast.net/x", transport)
        self.assertEqual(result["source_status"], "blocked")
        self.assertIn("Cloudflare", result["source_detail"])

    def test_403_sem_challenge(self) -> None:
        """Fonte fora do ar (manhuafast) não é captcha: o painel diz offline."""
        transport = FakeTransport([(403, "Forbidden", "https://x.com/y")])
        result = self.check("https://x.com/y", transport)
        self.assertEqual(result["source_status"], "offline")
        self.assertIn("sem challenge", result["source_detail"])

    def test_wrapper_levanta_erro_do_challenge(self) -> None:
        """manhuafast com espelho também bloqueado: `chapters` (e `chapter`)
        levantam HTTPStatusError 403, e o painel precisa dizer blocked, não
        parser_error (senão o cron insiste a cada 2h)."""
        transport = FakeTransport(
            [(403, "Just a moment...", "https://manhuafast.net/x")]
        )
        blocked = httpx.HTTPStatusError(
            "403: challenge no site e no espelho",
            request=httpx.Request("POST", "https://manhuafast.net/x"),
            response=httpx.Response(
                403, request=httpx.Request("POST", "https://manhuafast.net/x")
            ),
        )

        def chapters(manhwa):
            raise blocked

        result = self.check("https://manhuafast.net/x", transport, chapters=chapters)
        self.assertEqual(result["source_status"], "blocked")
        self.assertEqual(result["source_http"], 403)

    def test_404(self) -> None:
        transport = FakeTransport([(404, "", "https://x.com/y")])
        result = self.check("https://x.com/y", transport)
        self.assertEqual(result["source_status"], "not_found")

    def test_dns_morto(self) -> None:
        from requests.exceptions import ConnectionError as ReqConnError

        transport = FakeTransport([], exc=ReqConnError("dns"))
        result = self.check("https://toonclash.com/x", transport)
        self.assertEqual(result["source_status"], "dead")

    def test_dns_que_nao_resolve_nao_chama_http(self) -> None:
        transport = FakeTransport([])
        with mock.patch.object(health, "_resolves", lambda host: False):
            result = self.check("https://toonclash.com/x", transport)
        self.assertEqual(result["source_status"], "dead")
        self.assertIn("DNS", result["source_detail"])
        self.assertEqual(transport.calls, [])

    def test_ok_com_capitulos(self) -> None:
        transport = FakeTransport([(200, "ok", "https://x.com/y")])

        def chapters(manhwa):
            httpx.get(manhwa.source)
            return [{"id": 1}, {"id": 2}]

        result = self.check("https://x.com/y", transport, chapters=chapters)
        self.assertEqual(result["source_status"], "ok")
        self.assertEqual(result["source_chapters"], 2)
        self.assertEqual(result["source_http"], 200)

    def test_redirect_em_loop_para_na_quarta_visita(self) -> None:
        loop_url = "https://manhuaread.com/404.html"

        def loops(manhwa):
            for _ in range(10):
                httpx.get(loop_url)
            return []

        transport = FakeTransport([(301, "", loop_url)] * 10)
        result = self.check(loop_url, transport, chapters=loops)
        self.assertEqual(result["source_status"], "redirected")
        self.assertIn("loop", result["source_detail"])
        self.assertEqual(len(transport.calls), health.MAX_LOOP)

    def test_checagem_travada_vira_timeout(self) -> None:
        import time

        def slow(manhwa):
            time.sleep(5)
            return []

        with mock.patch.object(health, "CHECK_TIMEOUT", 0.05):
            result = health.check_source(
                SimpleNamespace(source="https://x.com/y", chapters=slow)
            )
        self.assertEqual(result["source_status"], "timeout")


if __name__ == "__main__":
    unittest.main()
