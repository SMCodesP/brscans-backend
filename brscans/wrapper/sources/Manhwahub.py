import re

import httpx
from bs4 import BeautifulSoup, ResultSet, Tag
from cloudscraper import CloudScraper
from unidecode import unidecode

from brscans.wrapper.sources.Generic import Generic


class Manhwahub(Generic):
    scraper = CloudScraper.create_scraper()

    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "Manhwahub"

    @staticmethod
    def info(url, capthers: bool = False):
        response = Manhwahub.scraper.get(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        print(soup.find("body").prettify())

        print("url", soup.find("meta", property="og:url"))
        id = soup.find("meta", property="og:url").get("content").split("/")[-2]
        title = soup.find("div", class_="post-title").find("h1").get_text().strip()
        summary = soup.find("div", class_="summary__content").get_text().strip()
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
            manhwa["chapters"] = Manhwahub.chapters(url)

        return manhwa

    @staticmethod
    def chapters(url):
        response = Manhwahub.scraper.get(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find("ul", class_="box-list-chapter").find_all(
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

    @staticmethod
    def pages(chapter: str, content: str = None):
        if content:
            html = content
        else:
            response = Manhwahub.scraper.get(chapter)
            html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find_all("img", class_="chapter-img")

        pages = []

        for cape in capes:
            src = cape.get("data-src") or cape.get("src")
            url = src.strip()
            pages.append(url)

        return pages

    @staticmethod
    def chapter(chapter_link: str):
        response = Manhwahub.scraper.get(chapter_link)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        chapter = soup.find("li", class_="active")
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
            "pages": Manhwahub.pages(chapter_link, html),
        }
