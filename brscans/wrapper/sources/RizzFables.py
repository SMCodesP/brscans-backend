import re
from cloudscraper import CloudScraper
from slugify import slugify
from unidecode import unidecode
import httpx
from bs4 import BeautifulSoup, ResultSet, Tag

from brscans.wrapper.sources.Generic import Generic
from brscans.manhwa.models import Chapter, Manhwa


class RizzFables(Generic):
    scraper = CloudScraper.create_scraper()

    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "RizzFables"

    @staticmethod
    def info(url, capthers: bool = False):
        response = RizzFables.scraper.post(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        id = url.split("/")[-1]
        title = soup.find("h1", class_="entry-title").get_text().strip()
        # summary = soup.find("div", id="description-container").get_text().strip()
        summary = soup.find("div", class_="entry-content").find("script")
        match = re.search(r'var description = "(.*?)" ;', summary.string, re.DOTALL)
        if match:
            summary = match.group(1).encode().decode("unicode_escape")

        image = soup.find("div", class_="thumb").find("img")
        image = image.get("data-src") or image.get("src")
        image = re.sub(r"-\d+x\d+(?=\.\w{3,4}$)", "", image)

        manhwa = {
            "id": id,
            "url": url,
            "title": unidecode(title),
            "summary": summary,
            "image": image,
        }

        if capthers:
            manhwa["chapters"] = RizzFables.chapters(url)

        return manhwa

    @staticmethod
    def chapters(manhwa: Manhwa):
        response = RizzFables.scraper.get(manhwa.source)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find("div", id="chapterlist").find_all("li")

        chapters = []

        for cape in capes:
            link = cape.find("a")
            title = link.find("span", class_="chapternum").get_text().strip()
            title = unidecode(" ".join(title.split()))
            url = link.get("href")
            chapter = {
                "id": slugify(title),
                "title": title,
                "url": url,
                "release_date": cape.find("span", class_="chapterdate")
                .get_text()
                .strip()
                .capitalize(),
            }
            chapters.append(chapter)

        return chapters

    @staticmethod
    def pages(chapter: Chapter, content: str = None):
        if content:
            html = content
        else:
            response = RizzFables.scraper.get(chapter.source)
            html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find("div", id="readerarea").find_all("img")

        pages = []

        for cape in capes:
            src = cape.get("data-src") or cape.get("src")
            url = src.strip()
            pages.append(url)

        return pages

    @staticmethod
    def chapter(chapter: Chapter):
        response = RizzFables.scraper.get(chapter.source)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        chapter_element = soup.find("select", id="chapter").find("option", selected=True)
        title = soup.find("meta", property="og:title")
        if chapter_element:
            chapter_element = chapter_element.get_text().strip()

        if title:
            title = title.get("content")
        else:
            title = ""

        return {
            "title": title,
            "chapter": chapter_element,
            "pages": RizzFables.pages(chapter, html),
        }
