import datetime
from zappa.asynchronous import task_sns

from brscans.manhwa.models import Chapter, Manhwa
from brscans.manhwa.tasks.sync_chapter import sync_chapter
from brscans.wrapper import sources
from brscans.wrapper.sources.Generic import Generic


@task_sns
def sync_chapters(manhwa_id: int):
    manhwa = Manhwa.objects.filter(id=manhwa_id).first()
    Source: Generic = sources.get_source_by_link(manhwa.source)
    chapters = Source.chapters(manhwa.source)
    chapters = reversed(chapters)
    records = []

    for chapter in chapters:
        chapter_records = Chapter.objects.filter(
            slug=chapter["id"], manhwa=manhwa
        ).first()
        if chapter_records == None:
            records.append(chapter)

    for chapter in records[:20]:
        chapter_records = Chapter.objects.create(
            slug=chapter.get("id"),
            title=chapter.get("title"),
            manhwa=manhwa,
            source=chapter.get("url"),
        )
        sync_chapter(chapter_records.pk, manhwa_id)
