import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from unidecode import unidecode

from brscans.manhwa.models import Chapter, Manhwa
from brscans.wrapper.sources.Generic import Generic


class KingOfShojo(Generic):
    """kingofshojo.com — tema "king" (BSX), não Madara.

    Cards em `div.bsx`, capítulos em `div#chapterlist .eph-num`,
    descrição em `div.entry-content`, capa em `div.thumb img`.
    """

    def __init__(self, url, headers=None) -> None:
        super().__init__(url, headers)
        self.name = "KingOfShojo"

    def search(self, query: str):
        response = self.client.get(
            self.url, params={"s": query, "post_type": "wp-manga"}
        )
        return KingOfShojo.cards(response.text)

    @staticmethod
    def cards(html: str, base: str = "https://kingofshojo.com/"):
        soup = BeautifulSoup(html, "html.parser")
        manhwas = []
        for box in soup.find_all("div", class_="bsx"):
            link = box.find("a")
            image = box.find("img")
            title = box.find("div", class_="tt")
            if not link or not image:
                continue
            href = urljoin(base, link.get("href"))
            manhwas.append(
                {
                    "id": href.rstrip("/").split("/")[-1],
                    "title": unidecode(title.get_text(strip=True)).upper()
                    if title
                    else "",
                    "url": href,
                    "image": image.get("src") or image.get("data-src"),
                }
            )
        return manhwas

    @staticmethod
    def info(url, capthers: bool = False):
        response = Generic.scraper.get(url)
        soup = BeautifulSoup(response.text, "html.parser")

        canonical = soup.find("meta", property="og:url").get("content")
        title = soup.find("h1", class_="entry-title")
        summary = soup.find("div", class_="entry-content")
        image = soup.find("div", class_="thumb").find("img")
        image = image.get("data-src") or image.get("src")
        image = re.sub(r"-\d+x\d+(?=\.\w{3,4}$)", "", image)

        manhwa = {
            "id": canonical.rstrip("/").split("/")[-1],
            "url": url,
            "title": unidecode(title.get_text(strip=True) if title else ""),
            "summary": summary.get_text(strip=True) if summary else "",
            "image": image,
        }

        if capthers:
            manhwa["chapters"] = KingOfShojo.chapters(url)

        return manhwa

    @staticmethod
    def chapters(manhwa: Manhwa):
        source = manhwa.source if hasattr(manhwa, "source") else manhwa
        response = Generic.scraper.get(source)
        soup = BeautifulSoup(response.text, "html.parser")

        chapters = []
        for cape in soup.select("div#chapterlist div.eph-num"):
            link = cape.find("a")
            href = link.get("href")
            url = href if href.startswith("http") else f"https://kingofshojo.com{href}"
            number = cape.find("span", class_="chapternum")
            date = cape.find("span", class_="chapterdate")
            title = number or link
            chapters.append(
                {
                    "id": url.rstrip("/").split("/")[-1],
                    "title": unidecode(title.get_text(strip=True)),
                    "url": url,
                    "release_date": date.get_text(strip=True).capitalize()
                    if date
                    else "",
                }
            )
        return chapters

    @staticmethod
    def pages(chapter: Chapter, content: str = None):
        source = chapter.source if hasattr(chapter, "source") else chapter
        html = content or Generic.scraper.get(source).text
        soup = BeautifulSoup(html, "html.parser")

        reader = soup.find(id="readerarea") or soup
        pages = []
        for image in reader.find_all("img"):
            src = image.get("data-src") or image.get("src")
            if src:
                pages.append(src.strip())
        return pages

    @staticmethod
    def chapter(chapter: Chapter):
        source = chapter.source if hasattr(chapter, "source") else chapter
        html = Generic.scraper.get(source).text
        soup = BeautifulSoup(html, "html.parser")

        title = soup.find("h1", class_="entry-title")
        active = soup.find("li", class_="active")

        return {
            "title": title.get_text(strip=True) if title else "",
            "chapter": active.get_text(strip=True) if active else "",
            "pages": KingOfShojo.pages(chapter, html),
        }
