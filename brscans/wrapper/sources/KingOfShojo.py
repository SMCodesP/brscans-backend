from copyreg import constructor
import re
from cloudscraper import CloudScraper
import requests
from unidecode import unidecode
import httpx
from bs4 import BeautifulSoup, ResultSet, Tag, NavigableString, Comment

from brscans.wrapper.sources.Generic import Generic


class KingOfShojo(Generic):
    scraper = CloudScraper.create_scraper()

    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "KingOfShojo"

    def homepage(self):
        response = self.client.get(self.url)
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
                "upscaled_image": f"http://localhost:8000/wrapper/anime4k?image={image}",
            }
            manhwas.append(manhwa)

        return manhwas

    @staticmethod
    def info(url, capthers: bool = False):
        response = KingOfShojo.scraper.post(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        id = soup.find("meta", property="og:url").get("content").split("/")[-2]
        title = soup.find("h1", class_="entry-title").get_text().strip()
        summary = soup.find("div", class_="entry-content").get_text().strip()
        image = soup.find("img", class_="wp-post-image")
        image = image.get("src") or image.get("data-src")
        image = re.sub(r"-\d+x\d+(?=\.\w{3,4}$)", "", image)

        manhwa = {
            "id": id,
            "url": url,
            "title": unidecode(title),
            "summary": summary,
            "image": image,
        }

        if capthers:
            manhwa["chapters"] = KingOfShojo.chapters(url)

        return manhwa

    @staticmethod
    def chapters(url):
        response = KingOfShojo.scraper.get(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        print(soup)

        capes: ResultSet[Tag] = soup.find("div", id="chapterlist").find_all(
            "div", class_="eph-num"
        )

        chapters = []

        for cape in capes:
            title = cape.find("span", class_="chapternum").get_text().strip()
            url = cape.find("a").get("href")
            chapter = {
                "id": url.split("/")[-2],
                "title": unidecode(title),
                "url": url,
                "release_date": cape.find("span", class_="chapterdate")
                .get_text()
                .strip()
                .capitalize(),
            }
            chapters.append(chapter)

        return chapters

    @staticmethod
    def pages(chapter: str, content: str = None):
        if content:
            html = content
        else:
            response = Generic.scraper.get(chapter)
            html = response.text

        soup = BeautifulSoup(html, "html.parser")

        container = soup.find("div", id="readerarea").find("p")
        capes: ResultSet[Tag] = container.find_all("img")

        pages = []

        for cape in capes:
            src = cape.get("data-src") or cape.get("src")
            url = src.strip()
            pages.append(url)

        return pages

    @staticmethod
    def chapter(chapter_link: str):
        response = KingOfShojo.scraper.get(chapter_link)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        chapter = soup.find("li", class_="active")
        title = soup.find("h1", class_="entry-title")
        if chapter:
            chapter = chapter.get_text().strip()

        if title:
            title = title.get_text().strip()

        return {
            "title": title,
            "chapter": chapter,
            "pages": KingOfShojo.pages(chapter_link, html),
        }
