import re

import httpx
from bs4 import BeautifulSoup, ResultSet, Tag
from cloudscraper import CloudScraper
from unidecode import unidecode

from brscans.manhwa.models import Chapter, Manhwa
from brscans.wrapper.sources.Generic import Generic


class Mangadass(Generic):
    scraper = CloudScraper.create_scraper()

    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "Mangadass"

    def search(self, query: str):
        """`/?s=` devolve o catálogo inteiro; a busca é `/search?q=`."""
        return Generic.cards(
            self.client.get(f"{self.url}/search", params={"q": query}).text,
            self.url,
        )

    @staticmethod
    def info(url, capthers: bool = False):
        response = Generic.scraper.get(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        id = (
            soup.find("meta", property="og:url")
            .get("content")
            .rstrip("/")
            .split("/")[-1]
        )
        title = (
            soup.find("div", class_="post-title").find("h1").get_text().strip()
        )
        summary = soup.find("div", class_="ss-manga").get_text().strip()
        image = soup.find("div", class_="summary_image").find("img")
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
            manhwa["chapters"] = Mangadass.chapters(url)

        return manhwa

    @staticmethod
    def chapters(manhwa: Manhwa):
        # GET e não POST: o tema devolve 405 no POST. O "Show more" é só CSS,
        # todos os capítulos já vêm no HTML.
        source = manhwa.source if hasattr(manhwa, "source") else manhwa
        response = Generic.scraper.get(source)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find_all("li", class_="a-h")

        chapters = []

        for cape in capes:
            link = cape.find("a")
            title = link.get_text().strip()
            href = link.get("href")
            chapter_url = href if href.startswith("http") else "https://mangadass.com" + href
            date = cape.find("span", class_="chapter-time")
            chapter = {
                "id": chapter_url.rstrip("/").split("/")[-1],
                "title": unidecode(title),
                "url": chapter_url,
                "release_date": date.get_text().strip().capitalize() if date else "",
            }
            chapters.append(chapter)

        return chapters

    @staticmethod
    def pages(chapter: Chapter, content: str = None):
        if content:
            html = content
        else:
            response = Mangadass.scraper.get(chapter.source)
            html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find(
            "div", class_="read-content"
        ).find_all("img")

        pages = []

        for cape in capes:
            src = cape.get("data-src") or cape.get("src")
            url = src.strip()
            pages.append(url)

        return pages

    @staticmethod
    def chapter(chapter: Chapter):
        response = Mangadass.scraper.get(chapter.source)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        chapter_element = soup.find("option", class_="selected")
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
            "pages": Mangadass.pages(chapter, html),
        }
