"""Tasks disparadas pelo painel. Rodam no executor/Zappa; nunca na request."""

from hashlib import sha256

from django.utils import timezone

from brscans.manhwa.models import ImageVariants, Manhwa
from brscans.manhwa.tasks.images_variants import add_original_image_variant
from brscans.manhwa.tasks.sync_chapter import fix_pages
from brscans.manhwa.tasks.sync_chapters import sync_chapters
from brscans.utils.tasks import task
from brscans.wrapper import sources


@task
def create_manhwa(link: str, limit: int = 5, is_nsfw: bool = False):
    """Same flow as ManhwaViewSet.download, but without calling sync_chapter
    synchronously (it is a `task`; inside a thread worker it would only queue).
    """
    identifier = sha256(link.encode("utf-8")).hexdigest()
    manhwa = Manhwa.objects.filter(identifier=identifier).first()
    if manhwa:
        if is_nsfw and not manhwa.is_nsfw:
            Manhwa.objects.filter(pk=manhwa.pk).update(is_nsfw=True)
        return sync_chapters(manhwa.pk, limit)

    Source = sources.get_source_by_link(link)
    result = Source.info(link, capthers=False)

    manhwa = Manhwa.objects.create(
        external_id=result.get("id"),
        hash_external_id=sha256(
            str(result.get("id")).encode("utf-8")
        ).hexdigest(),
        title=result.get("title"),
        slug=result.get("slug", None),
        source=result.get("url"),
        description=result.get("summary"),
        identifier=identifier,
        is_nsfw=is_nsfw,
    )
    thumbnail = ImageVariants.objects.create()
    manhwa.thumbnail = thumbnail
    manhwa.save()
    add_original_image_variant(
        thumbnail.pk, result.get("image"), ["chapters", str(manhwa.pk)], False
    )
    return sync_chapters(manhwa.pk, limit)


@task
def check_manhwa_source(manhwa_id: int):
    from brscans.wrapper.health import check_source

    manhwa = Manhwa.objects.filter(pk=manhwa_id).first()
    if not manhwa:
        return None
    data = check_source(manhwa)
    Manhwa.objects.filter(pk=manhwa_id).update(
        **data, source_checked_at=timezone.now()
    )
    return data


@task
def panel_sync_manhwa(manhwa_id: int, limit: int = 5):
    return sync_chapters(manhwa_id, limit)


@task
def panel_fix_chapter(chapter_id: int):
    """Conserta só as páginas com problema; nunca apaga página.

    Página editada à mão (manual_translated) fica intocada: refazer a
    tradução passaria por cima do que o admin salvou.
    """
    from brscans.manhwa.models import Chapter
    from brscans.manhwa.tasks.sync_chapter import add_original_to_page

    chapter = Chapter.objects.filter(pk=chapter_id).first()
    if not chapter:
        return None

    pages = list(chapter.pages.select_related("images").order_by("id"))
    if any(page.images is None for page in pages):
        # recriar as páginas apagaria as boas; o conserto não pode fazer isso
        return {"error": "Página sem imagem: recriar apagaria as boas."}

    manual = [p.pk for p in pages if p.images.manual_translated]
    refetch = [
        p
        for p in pages
        if not p.images.original and not p.images.manual_translated
    ]
    refetch_pks = {p.pk for p in refetch}

    # Antes de repor originals: senão a página nova seria postada duas vezes
    # (fix_pages e add_original_to_page). fix_pages é @task: chamar aqui
    # enfileiraria outra task, então roda o corpo direto (`.sync`).
    fix_pages.sync(chapter.pk)

    if refetch:
        if not chapter.source:
            return {"error": "Capítulo sem URL da fonte."}
        urls = sources.get_source_by_link(chapter.source).chapter(chapter)[
            "pages"
        ]
        if len(urls) != sum(p.quantity_merged or 1 for p in pages):
            # não dá para saber qual URL é de qual página; recriar apagaria
            return {
                "error": "Páginas e fonte não batem: recriar apagaria as "
                "boas. Conserte à mão."
            }
        start = 0
        for page in pages:
            count = page.quantity_merged or 1
            if page.pk in refetch_pks:
                add_original_to_page(
                    page.images.pk,
                    urls[start : start + count],
                    ["chapters", str(chapter.pk)],
                    chapter.manhwa_id,
                )
            start += count

    return {"refetched": sorted(refetch_pks), "manual": manual}
