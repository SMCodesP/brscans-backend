from zappa.asynchronous import task

from brscans.manhwa.models import Chapter, Manhwa
from brscans.manhwa.tasks.sync_chapter import sync_chapter
from brscans.wrapper import sources
from brscans.wrapper.sources.Generic import Generic


@task
def sync_chapters(manhwa_id: int):
    manhwa = Manhwa.objects.filter(id=manhwa_id).first()
    Source: Generic = sources.get_source_by_link(manhwa.source)
    chapters = Source.chapters(manhwa.source)
    print("chapters", chapters)
    chapters = reversed(chapters)
    records = []

    for chapter in chapters:
        chapter_records = Chapter.objects.filter(
            slug=chapter["id"], manhwa=manhwa
        ).first()
        if chapter_records == None:
            records.append(chapter)

    for chapter in records:
        chapter_records = Chapter.objects.create(
            slug=chapter.get("id"),
            title=chapter.get("title"),
            manhwa=manhwa,
            source=chapter.get("url"),
        )
        sync_chapter(chapter_records.pk, manhwa_id)

    return {"Message": "Chapters synced successfully."}
