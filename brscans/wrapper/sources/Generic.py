import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, ResultSet, Tag
from cloudscraper import CloudScraper
from unidecode import unidecode

from brscans.manhwa.models import Chapter, Manhwa


def _is_challenge(response) -> bool:
    """Resposta de bloqueio do Cloudflare: 403/503 com `cf-mitigated` ou com
    a página 'Just a moment'."""
    if response.status_code not in (403, 503):
        return False
    return bool(response.headers.get("cf-mitigated")) or (
        "just a moment" in response.text[:2000].lower()
    )


class Generic:
    scraper = CloudScraper.create_scraper()

    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "Generic"

    @classmethod
    def _fetch(cls, url, **kwargs):
        """CloudScraper, com o httpx como plano B.

        kaliscan derruba a conexão do requests/urllib3 ("server disconnected"),
        mas responde normalmente ao httpx; o resto do wrapper usa o httpx e
        aceita `.text` igual. Se o plano B também falha, sobe o erro dele.
        """
        try:
            return cls.scraper.get(url, **kwargs)
        except Exception:
            response = httpx.request(
                "GET", url, headers=kwargs.get("headers"), timeout=60
            )
            response.raise_for_status()
            return response

    def homepage(self):
        response = self.client.get(self.url, headers={"Referer": self.url})
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        capes: ResultSet[Tag] = soup.find_all("div", class_="page-item-detail")
        manhwas = []

        for cape in capes:
            title = cape.find("h3").get_text().strip()
            image = cape.find("img").get("data-src")
            image = f"{image.rsplit('-', 1)[0]}.{image.split('.')[-1]}"
            manhwa = {
                "id": cape.find("a").get("href").split("/")[-2],
                "title": unidecode(title).upper(),
                "url": cape.find("a").get("href"),
                "image": image,
            }
            manhwas.append(manhwa)

        return manhwas

    def search(self, query: str):
        """Busca do Madara; `self.url` é a base do site (`https://host`).

        Sem `post_type=wp-manga` vários Madara devolvem o site inteiro
        (aquareader, kaliscan, mangaread); com ele, só fichas de wp-manga.
        """
        return Generic.cards(
            self.client.get(
                self.url, params={"s": query, "post_type": "wp-manga"}
            ).text,
            self.url,
        )

    @staticmethod
    def cards(html: str, base: str):
        """Cards da busca; Madara já mudou `.c-tabs-item__content` por
        `.page-item-detail`, então o card é achado pelo link `/manga/`
        (mangatop publica as fichas em `/series/`)."""
        soup = BeautifulSoup(html, "html.parser")
        manhwas = []
        seen = set()
        for link in soup.find_all(
            "a", href=re.compile(r"/(?:manga|series)/[^/?#]+/?$")
        ):
            href = urljoin(base + "/", link.get("href"))
            if href in seen:
                continue
            seen.add(href)
            card = link.find_parent(
                "div", class_="c-tabs-item__content"
            ) or link.find_parent("div", class_="page-item-detail")
            if card is not None:
                link = card
            title = link.select_one(".post-title, h3, h4")
            image = card.find("img") if card is not None else None
            title = (
                title.get_text(strip=True)
                if title
                else ((image.get("alt") or "") if image else "")
            )
            image = (image.get("data-src") or image.get("src")) if image else None
            if image:
                image = re.sub(r"-\d+x\d+(?=\.\w{3,4}$)", "", image)
            manhwas.append(
                {
                    "id": href.rstrip("/").split("/")[-1],
                    "title": unidecode(title).strip(),
                    "url": href,
                    "image": image,
                }
            )
        return manhwas

    @staticmethod
    def info(url, capthers: bool = False):
        response = Generic._fetch(url, headers={"Referer": url})
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        # aquareader não usa `summary_image` nem `post-title`, mas sempre tem
        # og:url/og:image; o og:url vem sem barra final.
        og_url = soup.find("meta", property="og:url")
        title = soup.select_one("div.post-title h1") or soup.find("h1")
        summary = soup.find("div", class_="summary__content")
        image = soup.select_one("div.summary_image img") or soup.find(
            "meta", property="og:image"
        )
        image = (
            (image.get("data-src") or image.get("src"))
            if image and image.name == "img"
            else (image.get("content") if image else "")
        )
        image = re.sub(r"-\d+x\d+(?=\.\w{3,4}$)", "", image or "")

        manhwa = {
            "id": (
                og_url.get("content").rstrip("/").split("/")[-1]
                if og_url
                else url.rstrip("/").split("/")[-1]
            ),
            "url": url,
            "title": unidecode(title.get_text().strip() if title else ""),
            "summary": summary.get_text().strip()
            if summary
            else "Resumo não encontrado",
            "image": image,
        }

        if capthers:
            manhwa["chapters"] = Generic.chapters(url)

        return manhwa

    @staticmethod
    def _inline_chapters(soup, base: str = "") -> list[dict]:
        # O tema padrão lista `li.wp-manga-chapter`; zazamanga troca o `li` por
        # `div.wp-manga-chapter` e aquareader por `a.aqua-ch-item`; os clones
        # NSFW usam `#chapterlist li` sem classe.
        chapters = []

        for cape in soup.select(
            "li.wp-manga-chapter, div.wp-manga-chapter, #chapterlist li, a.aqua-ch-item"
        ):
            link = cape if cape.name == "a" else cape.find("a")
            if not link or not link.get("href"):
                continue
            url = urljoin(base or "", link.get("href"))
            # Só capítulo de verdade (o zazamanga põe banner na mesma lista).
            if not re.search(r"/chapter-[^/]+/?$", url):
                continue
            release = cape.find("span", class_="chapter-release-date")
            title = (
                link.get("data-chapter-name")
                or link.select_one("span.aqua-ch-item__name")
                or link
            )
            chapters.append(
                {
                    # Último segmento inteiro, como os outros temas (e como o
                    # `id` antigo): o slug do banco é `chapter-N`. Sem o prefixo,
                    # o cron via `slug in known` criaria capítulo duplicado.
                    "id": url.rstrip("/").split("/")[-1],
                    "title": unidecode(
                        title.get_text(strip=True).capitalize()
                        if isinstance(title, Tag)
                        else str(title).capitalize()
                    ),
                    "url": url,
                    "release_date": (
                        release.get_text().strip().capitalize() if release else ""
                    ),
                }
            )

        return chapters

    @staticmethod
    def chapters(manhwa: Manhwa, throttle=None):
        """Lista de capítulos; `throttle` é chamado antes de cada requisição.

        A lista vem inline em alguns Madara e só no ajax em outros; o ajax
        ora responde sem barra final, ora com, ora 404 (zazamanga). E alguns
        temas não põem `ul.version-chap` em volta dos capítulos.
        """
        source = manhwa.source
        response = None
        try:
            if throttle:
                throttle()
            response = Generic.scraper.post(
                source.rstrip("/") + "/ajax/chapters/",
                headers={"Referer": source},
            )
        except Exception:  # noqa: BLE001 - ajax fora: a lista está na página
            pass
        if response is None or response.status_code >= 400:
            if throttle:
                throttle()
            response = Generic._fetch(source, headers={"Referer": source})
            # Página que nem respondeu (ou um 404) não é a ficha do manga e
            # pode ter links de outra coisa com ids novos — foi assim que a
            # descoberta criou capítulo duplicado (02/11/2026). Só confia se
            # houver lista estruturada (zazamanga: 404 no ajax, lista em
            # `div.chapter-list`).
            if response.status_code == 404 or not BeautifulSoup(
                response.text, "html.parser"
            ).select_one("#chapterlist, .version-chap"):
                print(f"[chapters] sem lista estruturada em '{source}'")
                return []

        return Generic._inline_chapters(
            BeautifulSoup(response.text, "html.parser"), source
        )

    @staticmethod
    def pages(chapter: Chapter, content: str = None):
        if content:
            html = content
        else:
            response = Generic._fetch(
                chapter.source, headers={"Referer": chapter.source}
            )
            html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.select(
            "img.wp-manga-chapter-img, div.reading-content img"
        )

        pages = []

        for cape in capes:
            src = (cape.get("data-src") or cape.get("src") or "").strip()
            # O leitor do zazamanga põe o banner do topo como `wp-manga-chapter-img`.
            if not src.startswith(("http://", "https://", "//")):
                continue
            url = src
            if url.startswith("//"):
                url = "https:" + url
            pages.append(url)

        return pages

    @staticmethod
    def chapter(chapter: Chapter):
        response = Generic._fetch(chapter.source, headers={"Referer": chapter.source})
        html = response.text
        if _is_challenge(response):
            # Erro de bloqueio com o código HTTP na mensagem: os callers fazem
            # `result["pages"]` e quebrariam com TypeError em silêncio.
            # `health.check_source` reconhece o 403/503.
            raise httpx.HTTPStatusError(
                f"{response.status_code}: challenge no site",
                request=response.request,
                response=response,
            )

        soup = BeautifulSoup(html, "html.parser")
        # `li.active` é do menu de capítulos; sem ele o título de og:title
        # basta para achar o número ("Obra - Chapter 27").
        chapter_element = soup.find("li", class_="active") or soup.find("h1")
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
            "pages": Generic.pages(chapter, html),
        }
