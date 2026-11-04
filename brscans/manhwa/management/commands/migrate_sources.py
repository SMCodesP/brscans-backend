"""Migração automática de fonte, execução única (depois do backup do banco).

Só migra com confiança alta: mesmo título normalizado (ou título alternativo)
e a fonte nova tem capítulos >= o maior capítulo que temos. O resto vai para a
lista de revisão, nunca chuta. NSFW só vai para fonte de conteúdo equivalente.
"""

from types import SimpleNamespace

from django.core.management.base import BaseCommand

from brscans.manhwa.models import Manhwa, SourceStatus
from brscans.manhwa.source_migration import (
    MigrationError,
    _number,
    migrate_manhwa,
    normalize_title,
)
from brscans.wrapper.sources import nsfw_sources, searchable_sources


def _titles(manhwa):
    return [t for t in (manhwa.title, manhwa.original_title) if t]


def _biggest(manhwa):
    numbers = [_number(c.title) for c in manhwa.chapters.all()]
    return max([n for n in numbers if n is not None] or [0])


def _candidates(manhwa):
    """URLs da fonte nova com título igual e capítulos >= os nossos."""
    wanted = {normalize_title(t) for t in _titles(manhwa)}
    biggest = _biggest(manhwa)
    seen = set()
    for host, Source in searchable_sources.items():
        if manhwa.is_nsfw != (host in nsfw_sources):
            continue
        for title in _titles(manhwa):
            try:
                items = Source(f"https://{host}").search(title) or []
            except Exception as exc:  # noqa: BLE001 - fonte fora não para o resto
                print(f"[migrate] {host}: {type(exc).__name__}: {exc}")
                continue
            for item in items:
                url = item.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                if normalize_title(item.get("title")) not in wanted:
                    continue
                try:
                    chapters = Source.chapters(SimpleNamespace(source=url))
                except Exception:  # noqa: BLE001 - candidato ruim, tenta o próximo
                    continue
                numbers = [_number(c.get("title")) for c in chapters or []]
                if max([n for n in numbers if n is not None] or [0]) < biggest:
                    continue
                yield url


def _plan(manhwa, dry_run):
    for url in _candidates(manhwa):
        if dry_run:
            print(f"[plano] {manhwa.pk} {manhwa.title} -> {url}")
            return "migraria"
        try:
            result = migrate_manhwa(manhwa, url)
        except MigrationError as exc:
            print(f"[migrate] {manhwa.pk} {manhwa.title}: {exc}")
            continue
        print(f"[migrate] {manhwa.pk} {manhwa.title} -> {result}")
        return "migrado"
    print(f"[revisão] {manhwa.pk} {manhwa.title}")
    return "revisão"


class Command(BaseCommand):
    help = "Migra automaticamente os mangas com fonte problemática."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="imprime o plano, não altera"
        )
        parser.add_argument("--manhwa", type=int, help="só este Manhwa (id)")

    def handle(self, *args, **options):
        if not options["dry_run"]:
            self.stdout.write("Isto altera o banco. Ctrl+C para abortar.")
        qs = Manhwa.objects.exclude(
            source_status__in=[SourceStatus.OK, SourceStatus.REDIRECTED]
        ).prefetch_related("chapters")
        if options["manhwa"]:
            qs = qs.filter(pk=options["manhwa"])
        manhwas = list(qs.order_by("id"))
        self.stdout.write(f"{len(manhwas)} mangas com fonte problemática.")
        counts = {}
        for manhwa in manhwas:
            outcome = _plan(manhwa, options["dry_run"])
            counts[outcome] = counts.get(outcome, 0) + 1
        self.stdout.write(str(counts))
