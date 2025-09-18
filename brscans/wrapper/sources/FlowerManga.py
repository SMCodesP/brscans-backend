import httpx
from bs4 import BeautifulSoup, ResultSet, Tag
from cloudscraper import CloudScraper
from unidecode import unidecode

from brscans.wrapper.sources.Generic import Generic
from brscans.manhwa.models import Chapter, Manhwa


class FlowerManga(Generic):
    scraper = CloudScraper.create_scraper()

    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "FlowerManga"

    @staticmethod
    def chapters(manhwa: Manhwa):
        response = FlowerManga.scraper.post(manhwa.source)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        print(soup.prettify())

        capes: ResultSet[Tag] = soup.find("ul", class_="version-chap").find_all(
            "li", class_="wp-manga-chapter"
        )

        chapters = []

        for cape in capes:
            link = cape.find("a")
            title = link.get_text().strip()
            url = link.get("href")
            chapter = {
                "id": url.split("/")[-2],
                "title": unidecode(title),
                "url": url,
                "release_date": cape.find("span", class_="chapter-release-date")
                .get_text()
                .strip()
                .capitalize(),
            }
            chapters.append(chapter)

        return chapters
