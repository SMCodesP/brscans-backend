from io import BytesIO

import cloudscraper
from django.core.files.base import ContentFile
from PIL import Image

scraper = cloudscraper.create_scraper()


def image_url(url: str, filename: str, referer_url: str = None):  # Adicione o referer como parâmetro
    if referer_url is None:
        from brscans.utils.image import get_referer_from_url
        referer_url = get_referer_from_url(url)

    headers = {
        'Referer': referer_url,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'  # User-Agent real
    }
    response = scraper.get(url, headers=headers)
    print(url)
    
    image = Image.open(BytesIO(response.content))
    buffer = BytesIO()
    image.save(buffer, "WEBP", quality=95)

    content_file = ContentFile(buffer.getvalue(), name=filename)
    return content_file