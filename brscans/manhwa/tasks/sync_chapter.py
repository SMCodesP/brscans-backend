import os

from django.db.models import Q
from brscans.utils.tasks import task

from brscans.manhwa.models import Chapter, ImageVariants, Page
from brscans.manhwa.tasks.images_variants import (
    merge_batch_original,
    merge_pages_original,
    process_image_translate,
    process_image_fill_from_mongo,
)
from brscans.utils.image import (
    batch_urls,
    download_images,
    merge_page_groups,
)
from brscans.manhwa.work import begin_chapter_task
from brscans.wrapper.sources import get_source_by_link
from brscans.wrapper.sources.Generic import Generic


@task
def sync_chapter(chapter_id: dict, manhwa_id: int):
    """Scrape (Lambda cron): lê a fonte e manda o merge ao Modal."""
    chapter_records = Chapter.objects.filter(pk=chapter_id).first()

    # Guard: skip if chapter already has pages (prevents duplication on retry)
    if chapter_records.pages.exists():
        return {"Message": "Chapter already has pages, skipping."}

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
    chapter = Source.chapter(chapter_records)
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

    # Conectar ao MongoDB para verificar se já temos o blk_list salvo
    has_mongodb_fallback = False
    try:
        from pymongo import MongoClient

        mongo_uri = os.environ.get("MONGODB_URI")
        if not mongo_uri:
            raise RuntimeError("MONGODB_URI não configurada")
        mongo_client = MongoClient(mongo_uri)
        db = mongo_client["brscans-ia"]
        collection = db["blk_list"]
        has_mongodb_fallback = True
    except Exception as e:
        print("Erro ao inicializar MongoDB no fix_pages:", e)

    failures = []
    for variant in variants:
        if variant.original:
            # O translator guardou o blk_list: retomar no fill evita OCR+inpaint.
            fallback_found = False
            if has_mongodb_fallback:
                try:
                    fallback_found = bool(
                        collection.find_one(
                            {"image_id": variant.pk}, {"_id": 1}
                        )
                    )
                except Exception as e:
                    print(f"Erro ao verificar fallback MongoDB para variant {variant.pk}:", e)

            try:
                # `.sync`: o POST precisa falhar aqui para a página ficar com o
                # motivo em work_last_error; `@task` só enfileira o invoke.
                if fallback_found:
                    print(f"blk_list no MongoDB para variant {variant.pk}: continuando do fill")
                    process_image_fill_from_mongo.sync(variant.pk)
                else:
                    print("Iniciando tradução (do zero via Modal)")
                    process_image_translate.sync(
                        variant.pk,
                        variant.original.url,
                        ["chapters", str(chapter_records.pk)],
                        chapter_records.manhwa.pk,
                    )
            except Exception as e:
                # Uma página falhando não pode parar o lote das outras; o erro
                # já ficou registrado na página (_dispatch_ack).
                print(f"Falha ao disparar variant {variant.pk}:", e)
                failures.append(variant.pk)
        else:
            print("Variante sem original")

    return {"failed": failures}


@task
def sync_missing_original_pages(chapter_id: int, manhwa_id: int):
    """Scrape (Lambda cron): lê a fonte e manda o download ao Modal.

    O download/medição (que falha parcial e não pode apagar página boa) fica
    em apply_missing_originals, com as mesmas proteções.
    """
    chapter_records = Chapter.objects.filter(pk=chapter_id).first()
    if not chapter_records:
        return {"error": "Chapter not found"}

    Source: Generic = get_source_by_link(chapter_records.source)
    chapter_data = Source.chapter(chapter_records)
    page_urls = chapter_data.get("pages", [])

    apply_missing_originals(chapter_id, manhwa_id, page_urls)

    return {"Message": "Missing originals sync dispatched."}


@task
def apply_missing_originals(chapter_id: int, manhwa_id: int, page_urls: list):
    """
    Sincroniza páginas que não têm a variant original.
    Verifica se o número de páginas no BD corresponde ao número de páginas na fonte.
    Se não corresponder, recria todas as páginas para manter a ordem correta.
    """
    chapter_records = Chapter.objects.filter(pk=chapter_id).first()
    if not chapter_records:
        return {"error": "Chapter not found"}
    # A espera na fila da Lambda de trabalho é do merge: a trava curta começa aqui.
    begin_chapter_task(chapter_records.pk)

    # Contar páginas atuais
    current_pages = Page.objects.filter(chapter=chapter_records).order_by("id")
    current_count = current_pages.count()

    # Calcular quantas páginas deveriam existir: só as dimensões são lidas,
    # sem manter as imagens na memória. Download parcial apagaria páginas boas.
    try:
        expected_pages = len(merge_page_groups(page_urls))
    except RuntimeError:
        return {"error": "Falha ao baixar imagens da fonte"}

    # Se o número de páginas não corresponder, recriar todas; o merge baixa e
    # recria num passo só, sem apagar antes.
    if current_count != expected_pages:
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
            "chapter": chapter_records.title,
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
        if page.images and (
            not page.images.original or page.images.original == ""
        ):
            if url_index + urls_needed <= len(page_urls):
                # Obter as URLs para esta página
                urls_for_page = page_urls[url_index : url_index + urls_needed]

                # `.sync`: já estamos na Lambda de trabalho; um disparo aqui só enfileiraria
                # outra task pesada e a página ficaria sem original até lá.
                add_original_to_page.sync(
                    page.images.pk,
                    urls_for_page,
                    ["chapters", str(chapter_records.pk)],
                    manhwa_id,
                )
                processed_count += 1

        # Avançar o índice de URLs
        url_index += urls_needed

    return {
        "message": "Missing originals added successfully",
        "pages_processed": processed_count,
        "total_pages": current_pages.count(),
        "chapter": chapter_records.title,
    }


@task
def add_original_to_page(
    variant_id: int, urls: list, folder: list, main_id: str
):
    """
    Adiciona a variant original a uma página existente sem deletá-la.
    Baixa as imagens e faz o merge.
    """
    # Baixar as imagens das URLs (falha = exceção; nada é apagado aqui)
    images = download_images(urls)
    try:
        merge_batch_original(images, variant_id, folder, main_id)
    finally:
        for image in images:
            image.close()
