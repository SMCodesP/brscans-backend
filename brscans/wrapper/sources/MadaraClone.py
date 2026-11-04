from urllib.parse import urljoin

from bs4 import BeautifulSoup
from unidecode import unidecode

from brscans.manhwa.models import Chapter, Manhwa
from brscans.wrapper.sources.Generic import Generic


class MadaraClone(Generic):
    """manga18fx.com / manhwa18.cc / mangadna.com — clone PHP do Madara (NSFW).

    Mesmas classes de ficha e capítulo do Madara, mas não é WordPress: a busca
    é `GET /search?q=` (não `?s=`), não há ajax de capítulos, o leitor usa
    `div.read-content` e a capa vem em `div.manga-item`/`div.hthumb`.
    """

    def __init__(self, url, headers=None) -> None:
        super().__init__(url, headers)
        self.name = "MadaraClone"

    def search(self, query: str):
        # Apóstrofo derruba a busca dos três clones (HTTP 500).
        return MadaraClone.cards(
            self.client.get(
                f"{self.url}/search",
                params={"q": query.replace("'", "").replace("’", "")},
            ).text,
            self.url,
        )

    @staticmethod
    def cards(html: str, base: str):
        soup = BeautifulSoup(html, "html.parser")
        manhwas = []
        seen = set()
        for card in soup.select(".thumb-manga, .manga-item, .hthumb"):
            link = card.find("a", href=True)
            image = card.find("img")
            if not link or not image:
                continue
            href = urljoin(base + "/", link["href"])
            if href in seen:
                continue
            seen.add(href)
            manhwas.append(
                {
                    "id": href.rstrip("/").split("/")[-1],
                    "title": unidecode(
                        (link.get("title") or image.get("alt") or "").strip()
                    ),
                    "url": href,
                    "image": image.get("data-src") or image.get("src"),
                }
            )
        return manhwas

    @staticmethod
    def info(url, capthers: bool = False):
        soup = BeautifulSoup(
            MadaraClone.scraper.get(url).text, "html.parser"
        )
        og_url = soup.find("meta", property="og:url")
        title = soup.find("h1")
        # manhwa18.cc põe o selo "18+" dentro do h1.
        title = title.get_text(strip=True).removeprefix("18+") if title else ""

        manhwa = {
            "id": (
                og_url.get("content").rstrip("/").split("/")[-1]
                if og_url
                else url.rstrip("/").split("/")[-1]
            ),
            "url": url,
            "title": unidecode(title),
            "summary": (soup.select_one("div.summary-content") or soup).get_text(
                strip=True
            )[:1000],
            "image": (
                soup.select_one("div.summary_image img").get("src")
                if soup.select_one("div.summary_image img")
                else ""
            ),
        }

        if capthers:
            manhwa["chapters"] = MadaraClone.chapters(manhwa)

        return manhwa

    @staticmethod
    def chapters(manhwa: Manhwa):
        soup = BeautifulSoup(
            MadaraClone.scraper.get(manhwa.source).text, "html.parser"
        )
        # `/manga/slug/chapter-1` nos clones é relativo ao site.
        return Generic._inline_chapters(soup, manhwa.source)

    @staticmethod
    def pages(chapter: Chapter, content: str = None):
        html = content or MadaraClone.scraper.get(chapter.source).text
        soup = BeautifulSoup(html, "html.parser")
        pages = []
        for image in soup.select("div.read-content img"):
            src = image.get("data-src") or image.get("src")
            if src:
                pages.append(src.strip())
        return pages

    @staticmethod
    def chapter(chapter: Chapter):
        html = MadaraClone.scraper.get(chapter.source).text
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("meta", property="og:title")
        return {
            "title": title.get("content") if title else "",
            "chapter": (
                soup.find("h1").get_text(strip=True) if soup.find("h1") else ""
            ),
            "pages": MadaraClone.pages(chapter, html),
        }
