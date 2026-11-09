import os
from concurrent.futures import ThreadPoolExecutor
from os.path import join
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from brscans.manhwa.models import ImageVariants, Manhwa, Page
from brscans.manhwa.work import begin_chapter_task
from brscans.utils.generate_presigned_url import generate_presigned_url
from brscans.utils.image import (
    download_images,
    merge_page_groups,
    process_merge_images,
)
from brscans.utils.image_contract import image_destination
from brscans.utils.image_url import image_url
from brscans.utils.tasks import _post_ack, task


@task
def merge_pages_original(
    urls: list, chapter: int, folder: str, main_id: str = None
):
    # A espera na fila da Lambda de trabalho é do merge: a trava começa aqui.
    begin_chapter_task(chapter)

    # Só as dimensões: um grupo por vez fica na memória (capítulo não cabe).
    groups = merge_page_groups(urls)
    existing_pages = Page.objects.filter(chapter_id=chapter)

    # Disparo duplicado (o cron redisparou antes de a trava vencer): o capítulo
    # já está completo com esta mesma divisão — refazer custaria download,
    # upload e um capítulo vazio durante o merge.
    if _already_merged(existing_pages, groups):
        return {"Message": "Chapter already merged, skipping."}

    variants, order_pages = [], []

    try:
        # Variants e páginas primeiro (sem original): o capítulo tem a nova
        # divisão inteira antes de qualquer upload, então some o trecho em que
        # o reparo via "capítulo sem página". Dentro de uma transação, o
        # reparo (outro processo) nunca enxerga a divisão pela metade.
        with transaction.atomic():
            variants = ImageVariants.objects.bulk_create(
                [ImageVariants() for _ in groups]
            )
            order_pages = Page.objects.bulk_create(
                Page(
                    chapter_id=chapter,
                    images=variant,
                    quantity_merged=len(group),
                    order=order,
                )
                for order, (variant, group) in enumerate(
                    zip(variants, groups)
                )
            )
        for page, group in zip(order_pages, groups):
            # Um grupo por vez: as imagens saem da memória antes do próximo,
            # então o pico é o maior grupo, não o capítulo inteiro.
            _save_original(page.images, merge_group(group), folder)
        # Tudo baixado e salvo: só agora as antigas saem, no mesmo passo em
        # que a divisão nova já está montada.
        Page.objects.filter(chapter_id=chapter).exclude(
            pk__in=[page.pk for page in order_pages]
        ).delete()
    except Exception:
        # Páginas antigas ficam como estavam; só limpa o que esta tentativa
        # criou (páginas, variants e originais já enviados).
        for variant in variants:
            if variant.original:
                variant.original.delete(save=False)
        Page.objects.filter(pk__in=[page.pk for page in order_pages]).delete()
        for variant in variants:
            variant.delete()
        raise

    # Presign + POST ao ack em paralelo: em série, 300 páginas seguravam a
    # invoke do worker pelo tempo de 300 idas ao tradutor.
    def dispatch(variant):
        try:
            process_image_translate(
                variant.pk, variant.original.url, folder, main_id
            )
        except Exception as e:
            # Uma página sem tradução não pode derrubar o lote; o motivo já
            # ficou em work_last_error (_dispatch_ack).
            print(f"Falha ao disparar variant {variant.pk}:", e)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(dispatch, variants))

    return {"Message": "Created batches merged successfully."}


def _already_merged(existing_pages, groups) -> bool:
    """O capítulo já tem a mesma divisão, com original em todas as páginas?"""
    pages = list(existing_pages.select_related("images").order_by("order"))
    if len(pages) != len(groups):
        return False
    # Não olha `quantity_merged`: as páginas nascem com a divisão nova e
    # ordem antes do upload, então só o original em todas fecha o capítulo.
    return all(page.images and page.images.original for page in pages)


def merge_group(urls: list) -> ContentFile:
    """Baixa e funde um grupo; as imagens saem da memória em seguida."""
    images = download_images(urls)
    try:
        return process_merge_images(images)
    finally:
        for image in images:
            image.close()


def _save_original(variant, image, folder: str):
    # Path do id da variant, não UUID: o retry reescreve o mesmo objeto em vez
    # de deixar o anterior órfão no S3. `storage.save` renomearia (o storage
    # tem file_overwrite=False), então grava direto no path; o `update` não
    # passa pelo save do modelo e não mexe em `translated` (retry já pode tê-lo).
    path = join(*folder, "original", f"{variant.pk}.webp")
    image.content_type = "image/webp"
    variant.original.storage._save(path, image)
    ImageVariants.objects.filter(pk=variant.pk).update(original=path)
    variant.original.name = path


def merge_batch_original(
    images: list, variant_id: int, folder: str, main_id: str = None
):
    image = process_merge_images(images)
    try:
        variants = ImageVariants.objects.filter(id=variant_id).first()
        _save_original(variants, image, folder)
        process_image_translate(
            variants.pk, variants.original.url, folder, main_id
        )
    finally:
        image.close()

    return {"Message": "Pages merged successfully."}


@task
def add_original_image_variant(
    id: int, url: str, folder: str, translate: bool = True
):
    variant = ImageVariants.objects.filter(id=id).first()

    if variant:
        _save_original(variant, image_url(url, "original.webp"), folder)

    return {
        "message": "Image added to variant successfully.",
    }


def _dispatch_ack(variant_id: int, url: str, payload: dict) -> dict:
    """Dispara e, se falhar, grava o erro na página antes de reerguer.

    O reparo (`process_page`) precisa da exceção para aplicar backoff; os
    chamadores em lote (sync, botão do capítulo) engolem e seguem — em ambos
    os casos a página fica com o motivo em `work_last_error`.
    """
    try:
        return _post_ack(url, payload)
    except Exception as exc:
        Page.objects.filter(images_id=variant_id).update(
            work_last_error=str(exc)[:2000]
        )
        raise


def _manga_summary(main_id) -> str | None:
    """Título e sinopse da fonte para o prompt: sem eles o tradutor chuta o
    gênero dos personagens (ex.: protagonista disfarçada de homem)."""
    if not main_id:
        return None
    row = Manhwa.objects.filter(pk=main_id).values("title", "description").first()
    if not row:
        return None
    return f"{row['title']}\n{row['description'] or ''}".strip()[:2000]


@task
def process_image_translate(id, url: str, folder: str, main_id: str = None):
    path, content_type = image_destination(
        folder, "raw", uuid4().hex, "image/webp"
    )
    presign = generate_presigned_url(
        join(settings.PUBLIC_MEDIA_LOCATION, path),
        {"type": content_type},
    )
    _dispatch_ack(
        id,
        settings.TRANSLATOR_URL,
        {
            "presign": presign,
            "link": url,
            "image_id": id,
            "context": join("contexts", str(main_id), "context.json"),
            "path": path,
            "folder": join(*folder),
            "summary": _manga_summary(main_id),
        },
    )
    return {"Message": "Image translation accepted."}


@task
def process_image_fill_from_mongo(variant_id: int):
    from pymongo import MongoClient

    mongo_uri = os.environ.get("MONGODB_URI")
    if not mongo_uri:
        raise RuntimeError(
            "Variável de ambiente obrigatória ausente: MONGODB_URI. "
            "Configure na environment_variables do Zappa antes do deploy."
        )

    mongo_client = MongoClient(mongo_uri)
    db = mongo_client["brscans-ia"]
    collection = db["blk_list"]

    doc = collection.find_one({"image_id": variant_id})
    if not doc:
        print(
            f"Documento nao encontrado no MongoDB para variant_id {variant_id}"
        )
        return {"Message": "No blk_list found in MongoDB."}

    # Executa o post direto para o fill de tradução na AWS
    _dispatch_ack(
        variant_id,
        settings.FILL_URL,
        {
            "blk_list": doc["blk_list"],
            "prompt": doc["prompt"],
            "new_message": doc["new_message"],
            "folder": doc["folder"],
            "path_raw": doc["path_raw"],
            "context_path": doc["context_path"],
            "id": doc["image_id"],
        },
    )
    return {"Message": "Fill accepted."}

