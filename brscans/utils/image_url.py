from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
import requests


def image_url(url: str, filename):
    response = requests.get(url)
    image = Image.open(BytesIO(response.content))
    buffer = BytesIO()
    image.save(buffer, "WEBP")

    content_file = ContentFile(buffer.getvalue(), name=filename)
    return content_file
