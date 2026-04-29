from django.core.management.base import BaseCommand

from brscans.manhwa.tasks.sync_all_manhwas import sync_all_manhwas


class Command(BaseCommand):
    help = "Sincroniza capítulos de todos os mangas cadastrados."

    def handle(self, *args, **options):
        self.stdout.write("Sincronizando todos os mangas...")

        result = sync_all_manhwas()

        self.stdout.write(
            self.style.SUCCESS(
                f"Concluído: {result['synced']}/{result['total']} sincronizados, "
                f"{result['failed']} falharam."
            )
        )
