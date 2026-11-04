import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from unidecode import unidecode

from brscans.manhwa.models import Chapter, Manhwa
from brscans.wrapper.sources.Generic import Generic


class MangaThemesia(Generic):
    """Tema MangaThemesia (TS): arenascan, asterscans, akazascans,
    rokaricomics e rackusreads.

    A busca é `/?s=` (com `?title=` o site devolve o catálogo inteiro), os
    capítulos ficam em `.bxcl li` e o leitor em `#readerarea img`. Sem
    cloudscraper: httpx com UA de Chrome passa nas cinco de dentro da Lambda.
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        )
    }

    def __init__(self, url, headers=None) -> None:
        super().__init__(url, headers)
        self.name = "MangaThemesia"

    @staticmethod
    def _get(url: str, params=None) -> httpx.Response:
        # timeout explícito: a busca do painel chama direto, sem o health patch
        return httpx.get(
            url,
            headers=MangaThemesia.HEADERS,
            params=params,
            timeout=30,
            follow_redirects=True,
        )

    @staticmethod
    def _source_url(source) -> str:
        return source.source if hasattr(source, "source") else source

    def search(self, query: str):
        return MangaThemesia.cards(
            MangaThemesia._get(self.url, params={"s": query}).text, self.url
        )

    @staticmethod
    def cards(html: str, base: str):
        soup = BeautifulSoup(html, "html.parser")
        # `.bs` embrulha o `.bsx` no layout novo; o mesmo link aparece duas
        # vezes e o dedupe por href abaixo descarta a repetição.
        boxes = soup.select(".listupd .bsx, .listupd .bs")
        by_url = {}
        for box in boxes:
            link = box.select_one("a[href*='/manga/']")
            image = box.select_one("img")
            if link is None:
                continue
            href = urljoin(base + "/", link.get("href"))
            if href in by_url:
                continue
            title = link.get("title") or (image.get("alt") if image else "") or ""
            src = (image.get("data-src") or image.get("src")) if image else None
            if src:
                src = re.sub(r"-\d+x\d+(?=\.\w{3,4}$)", "", src)
            by_url[href] = {
                "id": href.rstrip("/").split("/")[-1],
                "title": " ".join(unidecode(title).split()),
                "url": href,
                "image": src,
            }
        return list(by_url.values())

    @staticmethod
    def info(url, capthers: bool = False):
        response = MangaThemesia._get(url)
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.select_one("h1.entry-title")
        summary = soup.select_one("div.entry-content")
        image = soup.select_one(".thumb img")
        image = (image.get("data-src") or image.get("src")) if image else None
        if image:
            image = re.sub(r"-\d+x\d+(?=\.\w{3,4}$)", "", image)

        manhwa = {
            "id": str(response.url).rstrip("/").split("/")[-1],
            "url": str(response.url),
            "title": unidecode(title.get_text(strip=True)) if title else "",
            "summary": summary.get_text(" ", strip=True) if summary else "",
            "image": image,
        }

        if capthers:
            manhwa["chapters"] = MangaThemesia.chapters(url)

        return manhwa

    @staticmethod
    def chapters(manhwa: Manhwa):
        source = MangaThemesia._source_url(manhwa)
        soup = BeautifulSoup(MangaThemesia._get(source).text, "html.parser")

        chapters = []
        for item in soup.select("div.bxcl li, div.cl li"):
            link = item.find("a")
            if link is None or not link.get("href"):
                continue
            number = item.select_one("span.chapternum") or link
            date = item.select_one("span.chapterdate")
            url = urljoin(source + "/", link.get("href"))
            chapters.append(
                {
                    "id": url.rstrip("/").split("/")[-1],
                    "title": " ".join(
                        unidecode(" ".join(number.stripped_strings)).split()
                    ),
                    "url": url,
                    "release_date": date.get_text(strip=True).capitalize()
                    if date
                    else "",
                }
            )
        return chapters

    @staticmethod
    def pages(chapter: Chapter, content: str = None):
        source = MangaThemesia._source_url(chapter)
        html = content or MangaThemesia._get(source).text
        soup = BeautifulSoup(html, "html.parser")

        reader = soup.find(id="readerarea")
        if reader is None:
            return []

        pages = []
        for image in reader.find_all("img"):
            src = image.get("data-src") or image.get("src")
            if src:
                pages.append(src.strip())
        return pages

    @staticmethod
    def chapter(chapter: Chapter):
        source = MangaThemesia._source_url(chapter)
        html = MangaThemesia._get(source).text
        soup = BeautifulSoup(html, "html.parser")
        title = soup.select_one("h1.entry-title")
        title = title.get_text(" ", strip=True) if title else ""

        return {
            "title": title,
            "chapter": None,
            "pages": MangaThemesia.pages(chapter, html),
        }
