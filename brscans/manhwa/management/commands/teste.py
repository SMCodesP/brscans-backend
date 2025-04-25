from django.core.management.base import BaseCommand

from brscans.manhwa.tasks.images_variants import merge_batch_original


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        merge_batch_original(
            [
                "https://cdn.rizzfables.com/wp-content/uploads/2024/10/14/ca10-04-76dd.webp"
            ],
            45659,
            ["chapters", "2674"],
        )
