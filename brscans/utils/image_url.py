from io import BytesIO

import cloudscraper
from django.core.files.base import ContentFile
from PIL import Image

scraper = cloudscraper.create_scraper()


def image_url(url: str, filename):
    response = scraper.get(url)
    image = Image.open(BytesIO(response.content))
    buffer = BytesIO()
    image.save(buffer, "WEBP")

    content_file = ContentFile(buffer.getvalue(), name=filename)
    return content_file
