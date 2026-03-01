from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand

from brscans.manhwa.models import Manhwa
from brscans.manhwa.tasks.translate_manhwa import translate_manhwa


class Command(BaseCommand):
    help = "Traduz título e descrição de todos os mangas que ainda não foram traduzidos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limitar quantidade de mangas a traduzir (0 = todos)",
        )

    def handle(self, *args, **options):
        limit = options["limit"]

        manhwas = Manhwa.objects.filter(original_title__isnull=True)
        total = manhwas.count()

        if limit > 0:
            manhwas = manhwas[:limit]

        self.stdout.write(f"Encontrados {total} mangas não traduzidos.")

        translated = 0
        failed = 0
        manhwas_ids = manhwas.values_list("id", flat=True)

        with ThreadPoolExecutor() as executor:
            executor.map(translate_manhwa, manhwas_ids)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nConcluído: {translated} traduzidos, {failed} falharam."
            )
        )
