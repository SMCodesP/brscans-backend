from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
import httpx
import requests
import cloudscraper

scraper = cloudscraper.create_scraper()


def image_url(url: str, filename):
    response = scraper.get(url)
    image = Image.open(BytesIO(response.content))
    buffer = BytesIO()
    image.save(buffer, "WEBP")

    content_file = ContentFile(buffer.getvalue(), name=filename)
    return content_file
