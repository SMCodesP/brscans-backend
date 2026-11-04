"""Estado de trabalho por capítulo: trava com validade, backoff e desistência.

Fica no banco, não em memória, porque o disparo da tradução é fire-and-forget
(a conclusão só aparece numa execução seguinte) e porque o cron roda em
Lambdas paralelas, onde só um UPDATE condicional garante que uma linha é
levada por uma execução só.
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, F, Q
from django.utils import timezone

from brscans.manhwa.models import Chapter, Page
from brscans.utils.tasks import Saturation

PENDING, RUNNING, DONE, DESISTED = "pending", "running", "done", "desisted"
ACTIVE = [PENDING, RUNNING, DONE]  # "done" volta a valer se aparecer buraco


def _missing_original(page):
    """Página `page` ('' ou 'pages__') sem variant/imagem original."""
    return (
        Q(**{f"{page}isnull": True})
        | Q(**{f"{page}images__isnull": True})
        | Q(**{f"{page}images__original__isnull": True})
        | Q(**{f"{page}images__original": ""})
    )


def _missing_translated(page):
    return Q(**{f"{page}images__translated__isnull": True}) | Q(
        **{f"{page}images__translated": ""}
    )


def _setting(name, default):
    return int(getattr(settings, name, default))


def pending_counts(chapter_id):
    """(sem original, sem tradução, total de páginas)."""
    return pending_counts_bulk([chapter_id])[chapter_id]


def pending_counts_bulk(chapter_ids):
    """Os mesmos contadores de `pending_counts` para vários capítulos numa
    query só (o loop de `count_fix_caps` pagava 3 queries por capítulo)."""
    rows = (
        Page.objects.filter(chapter_id__in=chapter_ids)
        .values("chapter_id")
        .annotate(
            missing_original=Count(
                "id",
                filter=Q(images__isnull=True)
                | Q(images__original__isnull=True)
                | Q(images__original=""),
            ),
            missing_translated=Count(
                "id",
                filter=Q(images__original__isnull=False)
                & ~Q(images__original="")
                & _missing_translated(""),
            ),
            total=Count("id"),
        )
    )
    counts = {row["chapter_id"]: row for row in rows}
    # Capítulo sem página também precisa aparecer (pending 0, total 0).
    for chapter_id in chapter_ids:
        counts.setdefault(
            chapter_id, {"missing_original": 0, "missing_translated": 0, "total": 0}
        )
    return {
        chapter_id: (
            row["missing_original"],
            row["missing_translated"],
            row["total"],
        )
        for chapter_id, row in counts.items()
    }


def backoff_delay(attempts):
    base = _setting("CHAPTER_WORK_BACKOFF_BASE_MINUTES", 30)
    ceiling = _setting("CHAPTER_WORK_BACKOFF_MAX_MINUTES", 240)
    return timedelta(minutes=min(base * 2 ** max(attempts - 1, 0), ceiling))


def _pending_annotation():
    return Count("pages", filter=_missing_original("pages__")) + Count(
        "pages",
        filter=Q(pages__images__original__isnull=False)
        & ~Q(pages__images__original="")
        & _missing_translated("pages__"),
    )


def due_chapters():
    """Capítulos com pendência (ou sem página alguma), sem trava viva e no prazo.

    `pages_count` sai do mesmo join da anotação: filtrar por `pages__isnull`
    criava um segundo join e devolvia uma linha por página, repetindo o
    mesmo capítulo.
    """
    now = timezone.now()
    return (
        Chapter.objects.annotate(
            pending=_pending_annotation(), pages_count=Count("pages")
        )
        .filter(
            Q(pending__gt=0) | Q(pages_count=0),
            work_status__in=ACTIVE,
        )
        .filter(
            Q(work_locked_until__isnull=True) | Q(work_locked_until__lte=now)
        )
        .filter(
            Q(work_next_attempt_at__isnull=True)
            | Q(work_next_attempt_at__lte=now)
        )
        .order_by("-id")  # capítulo novo não espera a fila antiga
    )


def close_finished():
    """Capítulos que o fire-and-forget terminou de traduzir saem da lista de `running`."""
    return (
        Chapter.objects.filter(work_status__in=ACTIVE, pages__isnull=False)
        .annotate(pending=_pending_annotation())
        .filter(pending=0)
        .update(
            work_status=DONE,
            work_locked_until=None,
            work_next_attempt_at=None,
            work_attempts=0,
            work_missing_pages=0,
        )
    )


def claim_chapter(chapter_id, force=False):
    """Leva o capítulo se a trava expirou (ou nunca existiu) e ele é elegível.

    Um único UPDATE condicional: entre Lambdas/threads concorrentes só uma
    execução enxerga a linha elegível. `force` é o override manual (rota
    count_fix_caps): ignora o agendamento e re-arma um desistido, mas continua
    respeitando a trava de quem já está com ele — só a expiração rouba trava.
    """
    now = timezone.now()
    eligible = Q(work_locked_until__isnull=True) | Q(work_locked_until__lte=now)
    if not force:
        eligible &= Q(work_status__in=ACTIVE) & (
            Q(work_next_attempt_at__isnull=True)
            | Q(work_next_attempt_at__lte=now)
        )
    return (
        Chapter.objects.filter(eligible, pk=chapter_id).update(
            work_status=RUNNING,
            # Trava longa: cobre a espera na fila da Lambda de trabalho. Ao começar de
            # verdade, begin_chapter_task a encurta.
            work_locked_until=now
            + timedelta(
                minutes=_setting("CHAPTER_QUEUE_LEASE_MINUTES", 360)
            ),
            work_attempts=1 if force else F("work_attempts") + 1,
        )
        == 1
    )


def begin_chapter_task(chapter_id):
    """Marca que o trabalho do capítulo começou (saiu da fila da Lambda de trabalho).

    A trava do disparo é longa porque a fila pode passar de horas; ao começar,
    volta a valer a trava curta, para um worker morto ser retomado no próximo
    cron em vez de ficar preso até a fila expirar.
    """
    Chapter.objects.filter(pk=chapter_id).update(
        work_locked_until=timezone.now()
        + timedelta(minutes=_setting("CHAPTER_WORK_LEASE_MINUTES", 45))
    )


def release_chapter(
    chapter_id, status, error=None, next_attempt_at=None, progress=None
):
    """Solta a trava e grava o desfecho da tentativa."""
    fields = {
        "work_status": status,
        "work_locked_until": None,
        "work_next_attempt_at": next_attempt_at,
        "work_last_error": error,
    }
    if progress is not None:
        fields["work_missing_pages"] = progress
    if status == DONE:
        fields["work_attempts"] = 0
    Chapter.objects.filter(pk=chapter_id).update(**fields)


def process_chapter(chapter, dispatch, force=False, max_attempts=0):
    """Decide o destino de um capítulo e, se for o caso, dispara o trabalho.

    `dispatch(chapter, needs_sync)` faz o disparo de verdade e é injetado para
    que trava, progresso e desistência sejam testáveis sem rede.
    `max_attempts=None` desliga a desistência do capítulo (quando são as
    páginas que carregam o estado).
    `dispatch` levanta `Saturation` quando o chip recusou por carga: a
    tentativa volta e o capítulo espera o backoff longo (`deferred`), em vez
    de queimar a última chance num 429.

    Retorna: done | desisted | locked | deferred | dispatched | error.
    """
    chapter.refresh_from_db()
    missing_original, missing_translated, page_count = pending_counts(
        chapter.pk
    )
    pending = missing_original + missing_translated
    if page_count == 0:
        pending = 1  # sem páginas não terminou: precisa de sync com a fonte

    if pending == 0:
        release_chapter(chapter.pk, DONE, progress=0)
        return "done"

    # Progresso desde o último disparo: capítulo grande e lento é saudável.
    # O crédito só vale se a tentativa seguir (débito e claim andam juntos):
    # desistir ou perder a trava não consome tentativa.
    moved = (
        chapter.work_attempts
        and chapter.work_missing_pages is not None
        and pending < chapter.work_missing_pages
    )
    attempts = chapter.work_attempts - 1 if moved else chapter.work_attempts

    if max_attempts == 0:
        max_attempts = _setting("CHAPTER_WORK_MAX_ATTEMPTS", 4)
    if max_attempts is not None and not force and attempts >= max_attempts:
        release_chapter(
            chapter.pk,
            DESISTED,
            error=(
                f"desistiu após {attempts} tentativas sem "
                f"progresso ({pending} página(s) pendente(s)); último erro: "
                f"{chapter.work_last_error or 'sem erro registrado'}"
            ),
            progress=pending,
        )
        return "desisted"

    if moved:
        Chapter.objects.filter(pk=chapter.pk).update(
            work_attempts=F("work_attempts") - 1
        )
    if not claim_chapter(chapter.pk, force=force):
        if moved:  # a linha pode ter mudado entre o débito e a tentativa
            Chapter.objects.filter(pk=chapter.pk).update(
                work_attempts=F("work_attempts") + 1
            )
        return "locked"

    needs_sync = missing_original > 0 or page_count == 0
    try:
        dispatch(chapter, needs_sync)
    except Saturation as exc:
        # Recusa por carga: a página/capítulo não está quebrado, só não coube
        # agora. Devolve a tentativa e espera o backoff longo.
        Chapter.objects.filter(pk=chapter.pk).update(
            work_attempts=F("work_attempts") - 1
        )
        release_chapter(
            chapter.pk,
            RUNNING,
            error=str(exc)[:2000],
            next_attempt_at=timezone.now()
            + timedelta(
                minutes=_setting("CHAPTER_SATURATION_BACKOFF_MINUTES", 10)
            ),
            progress=pending,
        )
        return "deferred"
    except Exception as exc:
        chapter.refresh_from_db(fields=["work_attempts"])
        release_chapter(
            chapter.pk,
            RUNNING,
            error=str(exc)[:2000],
            next_attempt_at=timezone.now()
            + backoff_delay(chapter.work_attempts),
            progress=pending,
        )
        return "error"

    # A trava segue até expirar; a próxima execução compara work_missing_pages.
    Chapter.objects.filter(pk=chapter.pk).update(work_missing_pages=pending)
    return "dispatched"


# --- Reparo por página -------------------------------------------------------
# Um capítulo grande não é desistido porque o tradutor saturou: cada página tem
# sua própria tentativa, backoff e desistência, e chega em `translated` (PATCH
# do filler) como único sinal de conclusão.

PAGE_MAX_ATTEMPTS = 3
PAGE_BACKOFF_MINUTES = 30


def due_pages(chapter_id):
    """Páginas do capítulo que precisam de ação agora."""
    now = timezone.now()
    return (
        Page.objects.filter(chapter_id=chapter_id)
        # Só páginas com original: sem original o caminho é o sync do capítulo
        # (baixar da fonte), não o reparo — senão elas gastariam tentativas.
        .filter(images__original__isnull=False)
        .exclude(images__original="")
        .filter(_missing_translated(""))
        .filter(
            Q(work_next_attempt_at__isnull=True)
            | Q(work_next_attempt_at__lte=now)
        )
        .filter(
            Q(
                work_attempts__lt=_setting(
                    "PAGE_MAX_ATTEMPTS", PAGE_MAX_ATTEMPTS
                )
            )
        )
        .select_related("images")
        .order_by("id")
    )


def claim_page(page_id):
    """UPDATE condicional: só uma execução leva a página."""
    now = timezone.now()
    return (
        Page.objects.filter(
            Q(work_next_attempt_at__isnull=True)
            | Q(work_next_attempt_at__lte=now),
            Q(
                work_attempts__lt=_setting(
                    "PAGE_MAX_ATTEMPTS", PAGE_MAX_ATTEMPTS
                )
            ),
            pk=page_id,
        ).update(
            work_attempts=F("work_attempts") + 1,
            work_next_attempt_at=now
            + timedelta(minutes=_setting("PAGE_LEASE_MINUTES", 20)),
        )
        == 1
    )


def release_page(page_id, error=None, next_attempt_at=None, exhausted=False):
    """Grava o desfecho da tentativa da página (não bloqueia a próxima)."""
    fields = {"work_last_error": error}
    if exhausted:
        fields["work_attempts"] = _setting(
            "PAGE_MAX_ATTEMPTS", PAGE_MAX_ATTEMPTS
        )
        fields["work_next_attempt_at"] = None
    else:
        fields["work_next_attempt_at"] = next_attempt_at
    Page.objects.filter(pk=page_id).update(**fields)


def process_page(page, send, force=False):
    """Decide e despacha uma página: done | desisted | locked | deferred |
    dispatched | error.

    `send(page, variant, has_original)` faz o disparo (injetado para teste).
    `Saturation` (429 do Modal) devolve a tentativa e só empurra o próximo
    envio — saturação não é falha da página.
    """
    page.refresh_from_db()
    variant = page.images
    if variant and variant.translated:
        Page.objects.filter(pk=page.pk).update(work_attempts=0)
        return "done"

    if force:
        Page.objects.filter(pk=page.pk).update(
            work_attempts=0, work_next_attempt_at=None
        )
        page.work_attempts = 0
    elif page.work_attempts >= _setting("PAGE_MAX_ATTEMPTS", PAGE_MAX_ATTEMPTS):
        return "desisted"

    if not claim_page(page.pk):
        return "locked"

    has_original = bool(variant and variant.original)
    try:
        send(page, variant, has_original)
    except Saturation as exc:
        Page.objects.filter(pk=page.pk).update(
            work_attempts=F("work_attempts") - 1,
            work_last_error=str(exc)[:2000],
            work_next_attempt_at=timezone.now()
            + timedelta(
                minutes=_setting("PAGE_SATURATION_BACKOFF_MINUTES", 10)
            ),
        )
        return "deferred"
    except Exception as exc:
        page.refresh_from_db(fields=["work_attempts"])
        exhausted = page.work_attempts >= _setting(
            "PAGE_MAX_ATTEMPTS", PAGE_MAX_ATTEMPTS
        )
        release_page(
            page.pk,
            error=str(exc)[:2000],
            next_attempt_at=None
            if exhausted
            else timezone.now()
            + timedelta(minutes=PAGE_BACKOFF_MINUTES * page.work_attempts),
            exhausted=exhausted,
        )
        return "error"

    # Sem resultado ainda: a próxima execução confere `translated`.
    Page.objects.filter(pk=page.pk).update(work_next_attempt_at=None)
    return "dispatched"

