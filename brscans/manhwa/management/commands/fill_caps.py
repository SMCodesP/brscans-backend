from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from brscans.manhwa.models import Chapter
from brscans.manhwa.tasks.sync_chapter import sync_chapter


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        chapters = Chapter.objects.filter(
            (
                Q(pages__isnull=True)
                | Q(pages__images__isnull=True)
                | Q(pages__images__translated__isnull=True)
                | Q(pages__images__original__isnull=True)
                | Q(pages__images__original="")
                | Q(pages__images__translated="")
            ),
            manhwa=48,
        )

        for chapter in chapters:
            chapter.pages.all().delete()
            sync_chapter(chapter.pk, 48)
