"""Evento de 2 h (stage `cron`, 512 MB): capítulos novos + reparo de páginas.

O disparo da tradução segue fire-and-forget (POST ao Modal, sem esperar o
resultado); por isso o reparo mede progresso comparando o pendente desta
tentativa com o da anterior, e não esperando resposta.
"""

import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from django.conf import settings
from django.db import close_old_connections
from django.db.models import F, Max

from brscans.manhwa.discord import notify_finished_chapters
from brscans.manhwa.models import Chapter, Manhwa, ManhwaStatus, Page, SourceStatus
from brscans.manhwa.tasks.images_variants import (
    process_image_fill_from_mongo,
    process_image_translate,
)
from brscans.manhwa.tasks.sync_chapter import (
    sync_chapter,
    sync_missing_original_pages,
)
from brscans.manhwa.work import (
    _missing_translated,
    begin_chapter_task,
    close_finished,
    due_chapters,
    due_pages,
    pending_counts,
    process_chapter,
    process_page,
)
from brscans.utils.tasks import drain_local_tasks, task
from brscans.wrapper.sources import get_source_by_link
from brscans.wrapper.sources.Generic import Generic


# Regra do mutirão: no máximo 1 requisição por domínio a cada 2s.
MIN_INTERVAL = 2.0
ZERO_DROPS = {"created": 0, "dispatched": 0, "matched": 0, "deferred": 0}


def _setting(name, default):
    return int(getattr(settings, name, default))


def _host(url):
    return (urlparse(url).hostname or "").lower()


def _throttle(url, last_request):
    """Pausa de 2 s por domínio, no relógio do lote (um por thread): o
    `sleep` só é pago por quem repete o host, nunca por quem espera outro."""
    host = _host(url)
    wait = MIN_INTERVAL - (time.monotonic() - last_request.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    last_request[host] = time.monotonic()


def dispatch_sync(chapter, needs_sync):
    """Capítulo novo sem páginas: sync_chapter é `scrape`, então o @task
    invoca a Lambda cron em vez de baixar aqui (o cron tem teto de tempo)."""
    sync_chapter(chapter.pk, chapter.manhwa_id)


def dispatch_repair(chapter, needs_sync):
    """Uma task por CAPÍTULO (não por página): cada disparo custa uma
    invocação, e o laço por página roda dentro dela. Nada de download/merge
    aqui: isso é trabalho de outra task.

    O sync dispara daqui, no cron. Sem original, reinicia as
    tentativas para o capítulo não desistir por páginas que o merge vai criar.
    """
    if needs_sync:
        sync_missing_original_pages(chapter.pk, chapter.manhwa_id)
        Chapter.objects.filter(pk=chapter.pk).update(work_attempts=0)
    return repair_pages(chapter.pk)


@task
def repair_pages(chapter_id, force=False):
    """Reparo página a página de um capítulo, com concorrência limitada.

    `force` (rota manual count_fix_caps) re-arma desistidos e ignora o
    backoff; o cron só pega as páginas na hora (due_pages).
    """
    chapter = Chapter.objects.filter(pk=chapter_id).first()
    if not chapter:
        return {"error": "chapter not found"}
    # Saiu da fila: a trava volta a ser curta (um worker morto é retomado).
    begin_chapter_task(chapter.pk)
    # Redisparo (a trava de fila venceu e o cron pegou o capítulo de novo):
    # capítulo COM páginas e completo não precisa de reparo. Capítulo sem
    # página segue para o sync — é lá que ele nasce.
    if not force and chapter.pages.exists():
        missing_original, missing_translated, _ = pending_counts(chapter.pk)
        if not missing_original and not missing_translated:
            return {"skipped": "nothing to repair"}
    if force:
        pages = (
            Page.objects.filter(
                _missing_translated(""),
                chapter_id=chapter.pk,
                images__original__isnull=False,
            )
            .exclude(images__original="")
            .select_related("images")
            .order_by("id")
        )
    else:
        pages = due_pages(chapter.pk)
    pages = list(pages)
    db = _mongo_db()  # levanta RuntimeError se faltar a env
    results = {}

    def dispatch(page):
        # Claim vivo no translator/filler não é falha da página: devolve sem
        # gastar tentativa (dentro do process_page a exceção viraria `error`
        # e queimaria uma das PAGE_MAX_ATTEMPTS).
        if page.images_id and _claimed(db, page.images_id):
            return "busy"
        return process_page(
            page, lambda p, v, ok: _send_page(p, v, ok, db), force=force
        )

    workers = min(_setting("REPAIR_PAGE_WORKERS", 4), len(pages))
    if workers <= 1:
        outcomes = map(dispatch, pages)  # serial (testes e fila vazia)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(dispatch, pages))
    for outcome in outcomes:
        results[outcome] = results.get(outcome, 0) + 1
    return results


def _send_page(page, variant, has_original, db):
    """Despacha uma página; sem original, só o sync do capítulo a resolve."""
    if not has_original:
        raise RuntimeError(
            "página sem original: precisa de sync_missing_original_pages"
        )
    if _claimed(db, variant.pk):
        raise RuntimeError("claim vivo no translator/filler")
    # `.sync` (corpo inline, não um invoke aninhado): o presign + POST ao ack
    # roda aqui e a exceção chega ao process_page para o backoff. Nada espera
    # a tradução terminar — o ack do Modal responde em ~1 s.
    if db["blk_list"].find_one({"image_id": variant.pk}, {"_id": 1}):
        process_image_fill_from_mongo.sync(variant.pk)
        return
    process_image_translate.sync(
        variant.pk,
        variant.original.url,
        ["chapters", str(page.chapter_id)],
        page.chapter.manhwa_id,
    )


def _mongo_db():
    """Base do brscans-ia. Falha ALTO sem MONGODB_URI: sem ela o reparo não
    consegue distinguir 'claim vivo' de 'livre' e re-dispararia às cegas."""
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError(
            "MONGODB_URI ausente: o reparo precisa dela para consultar "
            "translator_claims/filler_claims. Configure a env na função."
        )
    from pymongo import MongoClient

    return MongoClient(uri, serverSelectionTimeoutMS=2000)["brscans-ia"]


def _claimed(db, image_id):
    """True se há claim vivo ('claimed' < 900s) para a página.

    Mesmas regras do `repair_decision` do Tradutor: 'failed' e claim vencido
    podem ser reenviados. Se a consulta falhar, não reenviar (lado seguro:
    o reparo tenta de novo na próxima execução em vez de duplicar).
    """
    alive = {
        "image_id": image_id,
        "state": "claimed",
        "claimed_at": {"$gte": time.time() - 900},
    }
    try:
        return any(
            db[name].find_one(alive, {"_id": 1})
            for name in ("translator_claims", "filler_claims")
        )
    except Exception as exc:
        print(f"[repair] claim de {image_id}: {type(exc).__name__}: {exc}")
        return True


# Fontes que só voltam após um check-source OK no painel; não gastar requisição.
DEAD_SOURCES = [
    SourceStatus.NOT_FOUND,
    SourceStatus.DEAD,
    SourceStatus.OFFLINE,
    SourceStatus.BLOCKED,
    SourceStatus.NO_URL,
]


def _number(title):
    """Número do capítulo que o título carrega; aceita '12,5' e o
    '— Chapter 92'."""
    match = re.search(r"\d+(?:,\d+)?", title or "")
    return float(match.group().replace(",", ".")) if match else None


def _matches_existing(item, existing):
    """Casa pelo que o banco já tem: mesmo slug, mesma URL ou o mesmo número.

    Slug e URL são a identidade do capítulo. O número só entra quando o título
    é o decorado padrão (`index%`): a fonte troca o slug entre ajax e lista
    inline (1.778 capítulos vazios em 02/11/2026), mas também RENUMERA (o 40
    virou 92), e casar só por número zeraria capítulo real. Título não serve
    sozinho: 'Special Episode' é o título de vários episódios distintos.
    """
    if item["id"] in existing["slugs"]:
        return True
    if item["url"] in existing["urls"]:
        return True
    match = re.search(r"(\d+(?:,\d+)?)\s*%$", item.get("title") or "")
    return (
        bool(match)
        and float(match.group(1).replace(",", ".")) in existing["numbers"]
    )


def _discover_manhwa(manhwa, deadline, last_request):
    """Lista e cria os capítulos novos de UM manhwa. Devolve as contagens.

    A pausa de 2 s entre requisições do mesmo host vai AQUI: no laço por host
    ela cobriria também o ajax de cada capítulo novo, que é o que mais pesa.
    """
    drops = dict(ZERO_DROPS)
    if time.monotonic() >= deadline:
        drops["deferred"] = 1
        return drops
    _throttle(manhwa.source, last_request)
    try:
        source = get_source_by_link(manhwa.source)
        # staticmethod vira função simples no attr; os métodos `def chapters`
        # levam `self`, aí comparamos o `__func__`.
        chapters_fn = getattr(source.chapters, "__func__", source.chapters)
        if chapters_fn is not Generic.chapters:
            chapters = source.chapters(manhwa)
        else:
            chapters = source.chapters(manhwa, throttle=lambda: None)
    except Exception as exc:
        print(f"[sync] lista de '{manhwa}': {type(exc).__name__}: {exc}")
        return drops
    # A trava do wrapper ficou parada no começo do manhwa: sem mover o
    # relógio, uma lista vazia devolveria o mesmo "pronto" para a próxima
    # opção do host.
    last_request[_host(manhwa.source)] = time.monotonic()
    print(f"[sync] '{manhwa}': {len(chapters or [])} capítulos na fonte")

    if not chapters:  # None (contrato antigo) ou lista vazia: nada a criar
        return drops
    existing = {"slugs": set(), "urls": set(), "numbers": set()}
    for slug, title, source_url in Chapter.objects.filter(
        manhwa_id=manhwa.pk
    ).values_list("slug", "title", "source"):
        existing["slugs"].add(slug)
        if source_url:
            existing["urls"].add(source_url)
        stripped = (title or "").strip()
        number = _number(stripped)
        if number is not None:
            existing["numbers"].add(number)

    for item in reversed(chapters):  # a fonte lista do novo ao antigo
        if _matches_existing(item, existing):
            drops["matched"] += 1
            continue
        chapter, was_created = Chapter.objects.get_or_create(
            manhwa_id=manhwa.pk,
            slug=item["id"],
            defaults={"title": item["title"], "source": item["url"]},
        )
        if not was_created:
            continue
        drops["created"] += 1
        if process_chapter(chapter, dispatch_sync) == "dispatched":
            drops["dispatched"] += 1
    return drops


def discover_new_chapters(deadline):
    """Cria os capítulos que já estão na fonte e ainda não existem no banco.

    Cada manhwa é consultado uma vez (lista de capítulos). A criação é
    `get_or_create` e o sync de cada capítulo novo passa pela trava, então
    duas Lambdas no mesmo ciclo não recomeçam o mesmo capítulo.

    Antes de criar, casa por slug, URL e número com o que já existe: fonte
    que troca o slug entre ajax e lista inline (kingofshojo 02/11/2026)
    criou 1.778 capítulos, 1.428 deles vazios.

    Os manhwas são agrupados por host e cada host roda numa thread, então o
    `sleep` do throttle de um domínio não segura os outros (43 manhwas em
    ~10 hosts: antes eram 60–80 s de wall-clock por execução).
    """
    # Rodízio: quem não recebeu capítulo há mais tempo é checado primeiro,
    # então todos os manhwas são cobertos em poucas execuções.
    manhwas = list(
        Manhwa.objects.exclude(source_status__in=DEAD_SOURCES)
        .exclude(status=ManhwaStatus.COMPLETED)
        .exclude(source__isnull=True)
        .exclude(source="")
        .annotate(last_chapter=Max("chapters__created_at"))
        .order_by(F("last_chapter").asc(nulls_first=True), "id")
        .only("id", "source")
    )
    by_host = defaultdict(list)
    for manhwa in manhwas:
        by_host[_host(manhwa.source)].append(manhwa)

    def run(batch):
        # Thread do pool: a conexão do Django não pode ser herdada da thread
        # mãe; abre e fecha uma própria.
        close_old_connections()
        last_request = {}
        total = dict(ZERO_DROPS)
        try:
            for manhwa in batch:
                for key, value in _discover_manhwa(
                    manhwa, deadline, last_request
                ).items():
                    total[key] += value
        finally:
            close_old_connections()
        return total

    results = []
    batches = list(by_host.values())
    # Sem lote, o pool levantaria com max_workers=0; o laço vazio devolve ZERO_DROPS.
    workers = min(_setting("DISCOVERY_WORKERS", 8), len(batches))
    # BANCO_SINGLE_THREAD=1 (só testes): sqlite em memória não aceita escrita
    # de outra thread; a produção (Postgres) roda em paralelo normalmente.
    if workers <= 1 or os.environ.get("BANCO_SINGLE_THREAD") == "1":
        results = [run(batch) for batch in batches]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run, batches))

    summary = dict(ZERO_DROPS)
    for result in results:
        for key, value in result.items():
            summary[key] += value
    return summary


def repair_pending_pages(deadline):
    """Reparo de páginas faltantes, sem limite de capítulos.

    Cada capítulo é levado pela trava dele (evita dois reparos no mesmo
    capítulo); as páginas dentro dele têm trava própria. `deferred` é o que
    não coube no tempo/fila e volta na próxima execução.
    """
    if not os.environ.get("MONGODB_URI"):
        # Falha explícita, sem gastar tentativa por erro de configuração.
        print("[chapter-worker] reparo DESLIGADO: MONGODB_URI ausente")
        return {"disabled": "MONGODB_URI ausente"}
    results = {}
    for chapter in due_chapters():
        if time.monotonic() >= deadline:
            results["deferred_chapters"] = (
                results.get("deferred_chapters", 0) + 1
            )
            continue
        # As páginas têm estado próprio: o capítulo não desiste por tentativas,
        # só evita dois reparos concorrentes (trava).
        outcome = process_chapter(chapter, dispatch_repair, max_attempts=None)
        results[outcome] = results.get(outcome, 0) + 1
    return results


def _notify_discord():
    """Aviso falhar não pode derrubar sync e reparo."""
    try:
        return notify_finished_chapters()
    except Exception as exc:
        print(f"[discord] {type(exc).__name__}: {exc}")
        return {"error": True}


def handler(event=None, context=None):
    """Uma passada, com teto duro de tempo (o que não couber volta no próximo).

    Descoberta e reparo sem limite de capítulos, até o teto de tempo; o que
    não couber volta na próxima. Rodando na stage `cron` de 512 MB, cada
    @task daqui vai para a Lambda de trabalho, onde o trabalho de
    verdade roda.
    """
    started = time.monotonic()
    budget = _setting("CHAPTER_RUN_SECONDS", 120)
    deadline = started + budget

    # A descoberta SEMPRE roda: capítulos novos são o objetivo do cron, e com
    # o catálogo todo traduzido não há pendência que a faça rodar por engano.
    closed = close_finished()
    summary = {
        "closed": closed,
        "discord": _notify_discord(),
        "sync": discover_new_chapters(deadline),
        "repair": repair_pending_pages(deadline),
    }
    # Espera a fila local só dentro do teto; a Lambda congela ao retornar.
    summary["drained"] = drain_local_tasks(
        max(
            0,
            min(
                _setting("CHAPTER_DRAIN_SECONDS", 60),
                deadline - time.monotonic(),
            ),
        )
    )
    summary["seconds"] = round(time.monotonic() - started, 1)
    summary["inflight"] = summary["drained"]["pending"]
    print(f"[chapter-worker] {summary}")
    return summary
