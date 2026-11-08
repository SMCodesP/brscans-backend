import json
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from unidecode import unidecode

from brscans.manhwa.models import Chapter, Manhwa


class Comizy:
    """comizy.io — destino do redirect de mangabuddy.com.

    Site Next.js: o HTML só tem esqueleto, os dados vêm no `__NEXT_DATA__`.
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    API = "https://api.comizy.io"

    def __init__(self, url=None, headers=None) -> None:
        self.url = url
        self.headers = headers or self.HEADERS
        self.name = "Comizy"

    @staticmethod
    def _source_url(source) -> str:
        return source.source if hasattr(source, "source") else source

    @staticmethod
    def _get(url: str, **kwargs) -> httpx.Response:
        return httpx.get(
            url, headers=Comizy.HEADERS, timeout=None, follow_redirects=True, **kwargs
        )

    @staticmethod
    def _next_data(html: str) -> dict:
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.S,
        )
        return json.loads(match.group(1)) if match else {}

    @staticmethod
    def _page_props(html: str) -> dict:
        return Comizy._next_data(html).get("props", {}).get("pageProps", {})

    @staticmethod
    def _manga(html: str) -> dict:
        return Comizy._page_props(html).get("initialManga") or {}

    def search(self, query: str):
        """Busca do Next.js: resultados em `pageProps.ssrItems`."""
        # params= e não f-string: título com `&`/`#` cortava a query.
        props = Comizy._page_props(
            Comizy._get(f"{self.url}/search", params={"q": query}).text
        )
        return [
            {
                "id": item.get("id") or item.get("slug"),
                "title": unidecode(item.get("name") or ""),
                "url": urljoin("https://comizy.io/", item.get("url") or ""),
                "image": item.get("cover"),
            }
            for item in props.get("ssrItems") or []
            if item.get("url")
        ]

    @staticmethod
    def info(url, capthers: bool = False):
        response = Comizy._get(url)
        manga = Comizy._manga(response.text)
        if not manga:
            raise ValueError(f"{url}: sem __NEXT_DATA__ de obra")

        manhwa = {
            "id": manga.get("slug")
            or str(response.url).rstrip("/").split("/")[-1],
            "url": str(response.url),
            "title": unidecode(manga.get("name") or ""),
            "summary": manga.get("summary") or "",
            "image": manga.get("cover") or manga.get("cover_censored") or "",
        }

        if capthers:
            manhwa["chapters"] = Comizy.chapters(url)

        return manhwa

    @staticmethod
    def chapters(manhwa: Manhwa):
        response = Comizy._get(Comizy._source_url(manhwa))
        manga = Comizy._manga(response.text)
        site = re.match(r"https?://[^/]+", str(response.url)).group(0)

        return [
            {
                "id": item["slug"],
                "title": unidecode(item.get("name") or item["slug"]),
                "url": site + item["url"],
                "release_date": (
                    item.get("updatedAt") or item.get("updated_at") or ""
                )[:10],
            }
            for item in Comizy._all_chapters(manga)
        ]

    @staticmethod
    def _all_chapters(manga: dict) -> list[dict]:
        """O __NEXT_DATA__ só traz os 50 mais recentes; a API do site traz todos."""
        embedded = manga.get("chapters") or []
        if not manga.get("id"):
            return embedded
        try:
            response = Comizy._get(f"{Comizy.API}/titles/{manga['id']}/chapters")
            response.raise_for_status()
            items = (response.json().get("data") or {}).get("chapters") or []
        except (httpx.HTTPError, ValueError) as exc:
            print(f"[comizy] API de capítulos falhou, usando o HTML: {exc}")
            return embedded
        # API com menos itens que o HTML = resposta quebrada; fica com o HTML.
        return items if len(items) >= len(embedded) else embedded

    @staticmethod
    def pages(chapter: Chapter, content: str = None):
        html = content or Comizy._get(Comizy._source_url(chapter)).text

        # O DOM só renderiza as 10 primeiras páginas; a lista inteira está no
        # `initialChapter.images` do __NEXT_DATA__.
        payload = Comizy._page_props(html).get("initialChapter") or {}
        if payload.get("images"):
            return payload["images"]

        soup = BeautifulSoup(html, "html.parser")
        reader = soup.find("div", class_="flux-reader")
        images = reader.find_all("img") if reader else []
        return [img["src"] for img in images if img.get("src")]

    @staticmethod
    def chapter(chapter: Chapter):
        html = Comizy._get(Comizy._source_url(chapter)).text
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("meta", property="og:title")
        heading = soup.find("h1")

        return {
            "title": title.get("content") if title else "",
            "chapter": heading.get_text(strip=True) if heading else "",
            "pages": Comizy.pages(chapter, html),
        }
