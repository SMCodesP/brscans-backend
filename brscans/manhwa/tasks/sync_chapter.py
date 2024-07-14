from zappa.asynchronous import task_sns

from brscans.manhwa.models import Chapter, Manhwa
from brscans.manhwa.tasks.images_variants import merge_pages_original
from brscans.wrapper.sources.Generic import Generic


@task_sns
def sync_chapter(chapter_id: dict, manhwa_id: int):
    chapter_records = Chapter.objects.filter(pk=chapter_id).first()
    manhwa = chapter_records.manhwa
    chapter = Generic.chapter(f"{manhwa.source}/{chapter_records.slug}")
    merge_pages_original(
        chapter["pages"], chapter_records.pk, ["chapters", str(chapter_records.pk)]
    )
