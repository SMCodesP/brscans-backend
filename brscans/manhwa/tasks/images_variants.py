from io import BytesIO
from os.path import join
from uuid import uuid4

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from zappa.asynchronous import task

from brscans.manhwa.models import ImageVariants, Page
from brscans.utils.generate_presigned_url import generate_presigned_url
from brscans.utils.image import (
    batch_images_with_split,
    download_images,
    process_merge_images,
)
from brscans.utils.image_url import image_url
from brscans.utils.resize_image import resize_image


@task
def merge_pages_original(urls: list, chapter: int, folder: str, main_id: str = None):
    images = download_images(urls)
    batches = batch_images_with_split(images)

    for batch in batches:
        if len(batch) == 0:
            continue
        variants = ImageVariants.objects.create()
        variants.save()
        page = Page.objects.create(
            chapter_id=chapter, images=variants, quantity_merged=len(batch)
        )
        page.save()
        merge_batch_original(batch, variants.pk, folder, main_id)

    return {"Message": "Created batches merged successfully."}


def merge_batch_original(
    images: list, variant_id: int, folder: str, main_id: str = None
):
    image = process_merge_images(images)
    filename = f"{uuid4().hex}.webp"
    path = join(*folder, filename)

    image.content_type = "image/webp"
    variants = ImageVariants.objects.filter(id=variant_id).first()
    variants.original.save(path, image)
    process_image_translate(variants.pk, variants.original.url, folder, main_id)

    return {"Message": "Pages merged successfully."}


@task
def add_original_image_variant(id: int, url: str, folder: str, translate: bool = True):
    variant = ImageVariants.objects.filter(id=id).first()

    if variant:
        filename = f"{uuid4().hex}.webp"
        image = image_url(url, filename)
        image.content_type = "image/webp"
        variant.original.save(join(*folder, filename), image)
        new_url = variant.original.url
        # if translate:
        #     process_image_translate(variant.id, new_url, folder)

    return {
        "message": "Image added to variant successfully.",
    }


@task
def process_image_translate(id, url: str, folder: str, main_id: str = None):
    filename = f"{uuid4().hex}.jpeg"
    path = join(*folder, "translated", filename)
    presign = generate_presigned_url(
        join(settings.PUBLIC_MEDIA_LOCATION, path),
        {"type": "image/jpeg"},
    )
    try:
        httpx.post(
            "https://smcodesp--brscans-translate.modal.run",
            json={
                "presign": presign,
                "link": url,
                "image_id": id,
                "context": join("contexts", str(main_id), "context.json"),
                "path": path,
            },
            timeout=1,
        )
    except Exception as e:
        print(e)
        pass

    return {"Message": "Image translated successfully."}


@task
def process_image_variant_medium(id: int, folder: str):
    variant = ImageVariants.objects.filter(id=id).first()

    if variant:
        image = variant.original
        medium = resize_image(image, 300, 300)
        medium = medium.convert("RGB")
        buffer = BytesIO()
        medium.save(buffer, format="WEBP")
        medium_file = ContentFile(buffer.getvalue())

        variant.medium.save(join(*folder, f"{uuid4().hex}.webp"), medium_file)
        variant.save()

    return {"Message": "Image variant medium created successfully."}


@task
def process_image_variant_minimum(id: int, folder: str):
    variant = ImageVariants.objects.filter(id=id).first()

    if variant:
        image = variant.original
        minimum = resize_image(image, 150, 150)
        minimum = minimum.convert("RGB")
        buffer = BytesIO()
        minimum.save(buffer, format="WEBP")
        medium_file = ContentFile(buffer.getvalue())

        variant.minimum.save(join(*folder, f"{uuid4().hex}.webp"), medium_file)
        variant.save()

    return {"Message": "Image variant minimum created successfully."}
