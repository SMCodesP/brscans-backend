import re

import httpx
from bs4 import BeautifulSoup, ResultSet, Tag
from cloudscraper import CloudScraper
from unidecode import unidecode

from brscans.wrapper.sources.Generic import Generic


class Mangadass(Generic):
    scraper = CloudScraper.create_scraper()

    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "Mangadass"

    @staticmethod
    def info(url, capthers: bool = False):
        response = Generic.scraper.get(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        id = soup.find("meta", property="og:url").get("content").split("/")[-2]
        title = soup.find("div", class_="post-title").find("h1").get_text().strip()
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
    def chapters(url):
        response = Generic.scraper.post(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find_all("li", class_=["a-h", "wleft"])

        chapters = []

        for cape in capes:
            title = cape.find("a").get_text().strip()
            chapter_url = "https://mangadass.com" + cape.find("a").get("href")
            chapter = {
                "id": chapter_url.split("/")[-1],
                "title": unidecode(title),
                "url": chapter_url,
                "release_date": cape.find("span", class_="chapter-time")
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
            response = Mangadass.scraper.get(chapter)
            html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find("div", class_="read-content").find_all("img")

        pages = []

        for cape in capes:
            src = cape.get("data-src") or cape.get("src")
            url = src.strip()
            pages.append(url)

        return pages

    @staticmethod
    def chapter(chapter_link: str):
        response = Mangadass.scraper.get(chapter_link)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        chapter = soup.find("option", class_="selected")
        title = soup.find("meta", property="og:title")
        if chapter:
            chapter = chapter.get_text().strip()

        if title:
            title = title.get("content")
        else:
            title = ""

        return {
            "title": title,
            "chapter": chapter,
            "pages": Mangadass.pages(chapter_link, html),
        }
