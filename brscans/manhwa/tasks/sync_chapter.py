from zappa.asynchronous import task_sns

from brscans.manhwa.models import Chapter, Manhwa, Page
from brscans.manhwa.tasks.images_variants import merge_pages_original
from brscans.utils.image import batch_urls
from brscans.wrapper.sources import get_source_by_link
from brscans.wrapper.sources.Generic import Generic


@task_sns
def sync_chapter(chapter_id: dict, manhwa_id: int):
    chapter_records = Chapter.objects.filter(pk=chapter_id).first()
    # manhwa = chapter_records.manhwa
    Source: Generic = get_source_by_link(chapter_records.source)
    chapter = Source.chapter(chapter_records.source)
    chapter_records.quantity_pages = len(chapter["pages"])
    chapter_records.save()

    merge_pages_original(
        chapter["pages"], chapter_records.pk, ["chapters", str(chapter_records.pk)]
    )


def sync_chapter_fix(chapter_id: dict):
    chapter_records = Chapter.objects.filter(pk=chapter_id).first()
    Source: Generic = get_source_by_link(chapter_records.source)
    chapter = Source.chapter(chapter_records.source)
    chapter_records.quantity_pages = len(chapter["pages"])
    chapter_records.save()

    pages = Page.objects.filter(chapter=chapter_records)

    batches = batch_urls(chapter["pages"])

    return {
        "chapter_name": chapter_records.title,
        "chapter": chapter_records.pk,
        "pages": len(chapter["pages"]),
        "batches": len(batches),
        "pages_db": pages.count(),
    }
