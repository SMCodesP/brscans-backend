from os.path import join
from uuid import uuid4
from zappa.asynchronous import task
import httpx

from brscans.manhwa.models import Chapter, Page

@task
def upscale_page(page_id: int):
    page = Page.objects.get(pk=page_id)
    if page.images.translated:
        filename = f"{uuid4().hex}.jpeg"
        path = join("chapters", str(page.chapter.id), "upscaled", filename)
        try:
            httpx.post(
                "https://t6fx7fykca.execute-api.sa-east-1.amazonaws.com/dev/upscale",
                json={
                    "link": page.images.translated.url,
                    "path": path
                },
                timeout=1,
            )
        except Exception as e:
            print(e)
            pass


def upscale_pages(chapter_id: int):
    chapter = Chapter.objects.get(pk=chapter_id)
    pages = Page.objects.filter(chapter=chapter)
    for page in pages:
        upscale_page(page.id)
          
    return {"status": "upscaled"}