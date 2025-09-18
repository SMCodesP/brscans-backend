import httpx
from bs4 import BeautifulSoup, ResultSet, Tag
import cloudscraper
from unidecode import unidecode

from brscans.wrapper.sources.Generic import Generic


class KunManga(Generic):
    scraper = cloudscraper.create_scraper(
        interpreter='js2py',  # Recommended for v3 challenges
        delay=5,              # Allow more time for complex challenges
        debug=True            # Enable debug output to see v3 detection
    )

    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "KunManga"

    @staticmethod
    def chapters(url):
        print("Fetching chapters from KunManga:", url)
        response = KunManga.scraper.get(url)
        html = response.text
        print(html)

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
