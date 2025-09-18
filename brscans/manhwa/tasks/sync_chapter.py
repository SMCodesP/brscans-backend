from django.db.models import Q
from zappa.asynchronous import task

from brscans.manhwa.models import Chapter, ImageVariants, Page
from brscans.manhwa.tasks.images_variants import (
    merge_batch_original,
    merge_pages_original,
    process_image_translate,
)
from brscans.utils.image import batch_images_with_split, batch_urls, download_images
from brscans.wrapper.sources import get_source_by_link
from brscans.wrapper.sources.Generic import Generic


@task
def sync_chapter(chapter_id: dict, manhwa_id: int):
    chapter_records = Chapter.objects.filter(pk=chapter_id).first()
    # manhwa = chapter_records.manhwa
    Source: Generic = get_source_by_link(chapter_records.source)
    chapter = Source.chapter(chapter_records)
    chapter_records.quantity_pages = len(chapter["pages"])
    chapter_records.save()

    merge_pages_original(
        chapter["pages"],
        chapter_records.pk,
        ["chapters", str(chapter_records.pk)],
        manhwa_id,
    )

    return {"Message": "Chapter synced successfully."}


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


@task
def fix_pages(chapter_id: dict):
    chapter_records = Chapter.objects.filter(pk=chapter_id).first()

    variants = ImageVariants.objects.filter(
        Q(translated__isnull=True) | Q(translated=""),
        page__chapter=chapter_records,
        original__isnull=False,
    )

    for variant in variants:
        if variant.original:
            process_image_translate(
                variant.pk,
                variant.original.url,
                ["chapters", str(chapter_records.pk)],
                chapter_records.manhwa.pk,
            )


@task
def sync_missing_original_pages(chapter_id: int, manhwa_id: int):
    """
    Sincroniza páginas que não têm a variant original.
    Verifica se o número de páginas no BD corresponde ao número de páginas na fonte.
    Se não corresponder, recria todas as páginas para manter a ordem correta.
    """
    chapter_records = Chapter.objects.filter(pk=chapter_id).first()
    if not chapter_records:
        return {"error": "Chapter not found"}
    
    # Buscar dados do capítulo na fonte
    Source: Generic = get_source_by_link(chapter_records.source)
    chapter_data = Source.chapter(chapter_records.source)
    page_urls = chapter_data.get("pages", [])
    
    # Contar páginas atuais
    current_pages = Page.objects.filter(chapter=chapter_records).order_by('id')
    current_count = current_pages.count()
    
    # Calcular quantas páginas deveriam existir baseado nas URLs e merge
    # Primeiro baixar as imagens para calcular corretamente
    images = download_images(page_urls)
    expected_pages = len(batch_images_with_split(images))
    
    # Se o número de páginas não corresponder, recriar todas
    if current_count != expected_pages:
        # Deletar todas as páginas para recriar na ordem correta
        current_pages.delete()
        
        # Recriar todas as páginas
        merge_pages_original(
            page_urls,
            chapter_records.pk,
            ["chapters", str(chapter_records.pk)],
            manhwa_id,
        )
        
        return {
            "message": "Chapter pages recreated successfully",
            "pages_deleted": current_count,
            "pages_created": expected_pages,
            "chapter": chapter_records.title
        }
    
    # Se o número corresponder, apenas adicionar originals faltantes
    pages_without_original = current_pages.filter(
        Q(images__original__isnull=True) | Q(images__original="")
    )
    
    if pages_without_original.count() == 0:
        return {"message": "No pages without original found"}
    
    # Processar cada página individualmente
    processed_count = 0
    url_index = 0
    
    for page in current_pages:
        # Quantas URLs esta página precisa (baseado em quantity_merged)
        urls_needed = page.quantity_merged or 1
        
        # Se esta página não tem original
        if page.images and (not page.images.original or page.images.original == ""):
            if url_index + urls_needed <= len(page_urls):
                # Obter as URLs para esta página
                urls_for_page = page_urls[url_index:url_index + urls_needed]
                
                # Adicionar original à página
                add_original_to_page(
                    page.images.pk,
                    urls_for_page,
                    ["chapters", str(chapter_records.pk)],
                    manhwa_id
                )
                processed_count += 1
        
        # Avançar o índice de URLs
        url_index += urls_needed
    
    return {
        "message": "Missing originals added successfully",
        "pages_processed": processed_count,
        "total_pages": current_pages.count(),
        "chapter": chapter_records.title
    }


def add_original_to_page(variant_id: int, urls: list, folder: list, main_id: str):
    """
    Adiciona a variant original a uma página existente sem deletá-la.
    """
    # Baixar as imagens das URLs
    images = download_images(urls)
    
    if images:
        # Processar o merge das imagens
        merge_batch_original(images, variant_id, folder, main_id)
