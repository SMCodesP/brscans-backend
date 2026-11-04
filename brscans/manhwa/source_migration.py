"""Migração de fonte (estilo Mihon): troca de onde o Manhwa lê, sem criar outro.

Uma função só, usada pelo painel e pelo command automático. O Manhwa é o
mesmo: favoritos, comentários, notificações e is_nsfw não se mexem; páginas e
traduções existentes nunca são apagadas nem refeitas.
"""

import re
from hashlib import sha256
from types import SimpleNamespace
from urllib.parse import urlparse

from django.db import transaction
from unidecode import unidecode

from brscans.manhwa.discord import chapter_number
from brscans.manhwa.models import Chapter, Manhwa
from brscans.manhwa.tasks.panel import check_manhwa_source
from brscans.wrapper.sources import get_source_by_link


class MigrationError(Exception):
    """Falha que o admin precisa ver: fonte não leu, 0 capítulos ou URL de outro manga.

    `upstream` marca falha da fonte nova (502) em vez de pedido inválido (400).
    """

    def __init__(self, message, upstream=False):
        super().__init__(message)
        self.upstream = upstream


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", unidecode(title or "").lower())


def _number(title) -> float | None:
    """Número do capítulo pelo mesmo parser do Discord ('12', '12.5')."""
    raw = chapter_number(SimpleNamespace(title=title or ""))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def migrate_manhwa(manhwa, url: str) -> dict:
    """Migra `manhwa` para `url` e devolve `{source, matched, created, unmatched}`.

    Lê a fonte antes de abrir a transação (rede dentro do atomic seguraria o
    lock). Capítulo sem número no título não casa e vai para `unmatched`; o
    capítulo que só existe na fonte nova é criado aqui, mas as páginas ficam
    para o sync normal (o orçamento do cron continua valendo).
    """
    url = (url or "").strip()
    if (
        not url.startswith(("http://", "https://"))
        or not urlparse(url).hostname
    ):
        raise MigrationError("Informe a URL da página do manga no novo site.")

    Source = get_source_by_link(url)
    try:
        info = Source.info(url) or {}
        items = Source.chapters(SimpleNamespace(source=url))
    except Exception as exc:  # noqa: BLE001 - vira 400/502 com o motivo
        raise MigrationError(
            f"A fonte nova não respondeu: {type(exc).__name__}: {exc}"[:300],
            upstream=True,
        ) from exc
    if not items:
        raise MigrationError(
            "A fonte nova não devolveu capítulos.", upstream=True
        )

    canonical = info.get("url") or url
    # identifier é sha256(também) da URL gravada: se o site redirecionou, a
    # URL colada não é a que create_manhwa vai procurar depois.
    identifier = sha256(canonical.encode("utf-8")).hexdigest()
    taken = (
        Manhwa.objects.filter(identifier=identifier)
        .exclude(pk=manhwa.pk)
        .first()
    )
    if taken:
        raise MigrationError(
            f"Essa URL já é do manga #{taken.pk} ({taken.title})."
        )

    fields = {"source": canonical, "identifier": identifier}
    external_id = info.get("id")
    if external_id is not None:
        # external_id é único por site: trocar junto, senão o próximo
        # create_manhwa da URL nova criaria um segundo Manhwa.
        new_hash = sha256(str(external_id).encode("utf-8")).hexdigest()
        clash = (
            Manhwa.objects.filter(hash_external_id=new_hash)
            .exclude(pk=manhwa.pk)
            .exists()
        )
        if clash:
            raise MigrationError(
                "A ficha nova já pertence a outro manga do banco."
            )
        fields.update(external_id=str(external_id), hash_external_id=new_hash)

    by_number: dict[float, list] = {}
    for item in items:
        number = _number(item.get("title"))
        if number is not None:
            by_number.setdefault(number, []).append(item)

    matched, created, unmatched = 0, 0, []
    # shortcut: update() não checa identifier de origem; duas migrações
    # simultâneas, a última escrita vence. Admin é raro, sobe se virar API.
    with transaction.atomic():
        Manhwa.objects.filter(pk=manhwa.pk).update(**fields)
        numbers = {
            pk: _number(title)
            for pk, title in Chapter.objects.filter(
                manhwa_id=manhwa.pk
            ).values_list("pk", "title")
        }
        existing = sorted(
            Chapter.objects.filter(manhwa_id=manhwa.pk),
            key=lambda c: (numbers[c.pk] is None, numbers[c.pk] or 0),
        )
        claimed = set()
        for chapter in existing:
            number = numbers[chapter.pk]
            candidates = by_number.get(number) if number is not None else None
            item = None
            while candidates:
                candidate = candidates.pop(0)
                if str(candidate["id"]) not in claimed:
                    item = candidate
                    break
            if item is None:
                unmatched.append(chapter.title)
                continue
            claimed.add(str(item["id"]))
            matched += 1
            if chapter.source != item["url"] or chapter.slug != str(item["id"]):
                # slug é a chave do dedupe do cron: sem trocar, ele duplicaria.
                Chapter.objects.filter(pk=chapter.pk).update(
                    source=item["url"], slug=str(item["id"])
                )
        slugs = {chapter.slug for chapter in existing}
        for item in items:
            slug = str(item["id"])
            if slug in claimed or slug in slugs:
                continue
            Chapter.objects.create(
                manhwa_id=manhwa.pk,
                slug=slug,
                title=item.get("title") or slug,
                source=item["url"],
            )
            created += 1

    # @task: enfileira (Modal/thread pool), não espera o laudo. Fora do
    # atomic de propósito; a correção pode levar até CHECK_TIMEOUT.
    check_manhwa_source(manhwa.pk)

    return {
        "source": canonical,
        "matched": matched,
        "created": created,
        "unmatched": unmatched,
    }
