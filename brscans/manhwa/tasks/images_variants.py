from datetime import datetime
from io import BytesIO
from uuid import uuid4
from django.conf import settings
from django.core.files.base import ContentFile
import httpx
from zappa.asynchronous import task_sns
from brscans.manhwa.models import ImageVariants, Page
from brscans.utils.generate_presigned_url import generate_presigned_url
from brscans.utils.image import batch_urls, process_merge_images
from brscans.utils.image_url import image_url
from brscans.utils.resize_image import resize_image
from os.path import join


@task_sns
def merge_pages_original(urls: list, chapter: int, folder: str):
    batches = batch_urls(urls)

    for batch in batches:
        variants = ImageVariants.objects.create()
        variants.save()
        page = Page.objects.create(
            chapter_id=chapter, images=variants, quantity_merged=len(batch)
        )
        page.save()
        merge_batch_original(batch, variants.pk, folder)

    return {"Message": "Created batches merged successfully."}


@task_sns
def merge_batch_original(urls: list, variant_id: int, folder: str):
    image = process_merge_images(urls)
    filename = f"{uuid4().hex}.webp"
    path = join(*folder, filename)

    image.content_type = "image/webp"
    variants = ImageVariants.objects.filter(id=variant_id).first()
    variants.original.save(path, image)
    process_image_translate(variants.pk, variants.original.url, folder)

    return {"Message": "Pages merged successfully."}


@task_sns
def add_original_image_variant(id: int, url: str, folder: str, translate: bool = True):
    variant = ImageVariants.objects.filter(id=id).first()

    if variant:
        filename = f"{uuid4().hex}.webp"
        image = image_url(url, filename)
        image.content_type = "image/webp"
        variant.original.save(join(*folder, filename), image)
        new_url = variant.original.url
        if translate:
            process_image_translate(variant.id, new_url, folder)

    return {}


@task_sns
def process_image_translate(id, url: str, folder: str):
    variant = ImageVariants.objects.filter(id=id).first()
    if variant:
        filename = f"{uuid4().hex}.jpeg"
        path = join(*folder, "translated", filename)
        presign = generate_presigned_url(
            join(settings.PUBLIC_MEDIA_LOCATION, path),
            {"type": "image/jpeg"},
        )

        try:
            httpx.post(
                "https://smcodesp--brscans-translate.modal.run",
                json={"presign": presign, "link": url},
                timeout=0.0001,
            )
        except httpx.ReadTimeout:
            pass
    else:
        print("Image variant not found.")

    return {"Message": "Image translated successfully."}


@task_sns
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


@task_sns
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
