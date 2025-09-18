from brscans.manhwa.models import Chapter, Manhwa
from brscans.manhwa.tasks.sync_chapter import fix_pages
from brscans.manhwa.tasks.sync_chapters import sync_chapters
from django.db.models import Q


def fix_manhwas():
    chapters = Chapter.objects.filter(
        (
            Q(pages__isnull=True)
            | Q(pages__images__isnull=True)
            | Q(pages__images__translated__isnull=True)
            | Q(pages__images__translated="")
        ),
        pages__images__original__isnull=False,
    ).distinct()

    for chapter in chapters[:20]:
        fix_pages(chapter.pk)

    return True
