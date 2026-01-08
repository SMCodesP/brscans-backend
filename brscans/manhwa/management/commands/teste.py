from django.core.management.base import BaseCommand

from brscans.manhwa.tasks.images_variants import merge_pages_original


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        merge_pages_original(
            [
                "https://gg.asuracomic.net/storage/media/151882/conversions/01-optimized.webp",
                "https://gg.asuracomic.net/storage/media/151929/conversions/02-optimized.webp",
                "https://gg.asuracomic.net/storage/media/151969/conversions/03-optimized.webp",
                "https://gg.asuracomic.net/storage/media/152014/conversions/04-optimized.webp",
                "https://gg.asuracomic.net/storage/media/152055/conversions/05-optimized.webp",
                "https://gg.asuracomic.net/storage/media/152100/conversions/06-optimized.webp",
                "https://gg.asuracomic.net/storage/media/152132/conversions/07-optimized.webp",
                "https://gg.asuracomic.net/storage/media/152175/conversions/08-optimized.webp",
                "https://gg.asuracomic.net/storage/media/152221/conversions/09-optimized.webp",
                "https://gg.asuracomic.net/storage/media/152271/conversions/10-optimized.webp",
                "https://gg.asuracomic.net/storage/media/152323/conversions/11-optimized.webp",
                "https://gg.asuracomic.net/storage/media/152371/conversions/12-optimized.webp",
                "https://gg.asuracomic.net/storage/media/152421/conversions/13-optimized.webp",
                "https://gg.asuracomic.net/storage/media/152472/conversions/14-optimized.webp",
            ],
            4809,
            ["chapters", str(4809)],
            158,
        )
