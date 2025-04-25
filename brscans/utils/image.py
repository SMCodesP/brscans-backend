from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO

from cloudscraper import CloudScraper
from django.core.files.base import ContentFile
from PIL import Image

scraper = CloudScraper.create_scraper()


# Função para baixar imagem a partir de uma URL
def download_image(url):
    response = scraper.get(url)
    if response.status_code != 200:
        print(f"Erro ao baixar imagem: {url}")
    response.raise_for_status()
    return Image.open(BytesIO(response.content))


# Função para fazer merge vertical de imagens
def merge_images(images):
    widths, heights = zip(*(i.size for i in images))
    total_height = sum(heights)
    max_width = max(widths)

    new_image = Image.new("RGB", (max_width, total_height))
    y_offset = 0
    for im in images:
        print(f"Imagem: {im.size}")
        new_image.paste(im, (0, y_offset))
        y_offset += im.height

    return new_image


def download_images(urls):
    with ThreadPoolExecutor() as executor:
        images = list(executor.map(download_image, urls))
    return images


def images_height(images):
    return [{"height": image.height, "width": image.width} for image in images]


# Função principal para processar URLs e retornar lista de ContentFile
def batch_urls(urls):
    time = datetime.now()
    images = download_images(urls)
    sizes = images_height(images)
    print(
        f"Levou {(datetime.now() - time).total_seconds():.2f} segundos para baixar as imagens."
    )

    max_height = 16383
    grouped_images = []
    current_group = []
    current_height = 0
    current_width = None

    for url, size in zip(urls, sizes):
        if current_width is None:
            current_width = size.get("width")

        if current_width == size.get("width"):
            if current_height + size.get("height") <= max_height:
                current_group.append(url)
                current_height += size.get("height")
            else:
                grouped_images.append(current_group)
                current_group = [url]
                current_height = size.get("height")
                current_width = size.get("width")
        else:
            grouped_images.append(current_group)
            current_group = [url]
            current_height = size.get("height")
            current_width = size.get("width")

    if current_group:
        grouped_images.append(current_group)

    return grouped_images


def process_merge_images(urls):
    images = download_images(urls)
    merged_image = merge_images(images)
    buffer = BytesIO()
    merged_image.convert("RGB").save(buffer, format="WEBP")
    return ContentFile(buffer.getvalue(), name="merged_image.webp")
