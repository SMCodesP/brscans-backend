from copyreg import constructor
import re
from cloudscraper import CloudScraper
import requests
from unidecode import unidecode
import httpx
from bs4 import BeautifulSoup, ResultSet, Tag, NavigableString, Comment


class Generic:
    scraper = CloudScraper.create_scraper()

    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "Generic"

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
        response = Generic.scraper.post(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        id = soup.find("meta", property="og:url").get("content").split("/")[-2]
        title = soup.find("div", class_="post-title").find("h1").get_text().strip()
        summary = soup.find("div", class_="summary__content").get_text().strip()
        image = soup.find("div", class_="summary_image").find("img")
        image = image.get("src") or image.get("data-src")

        manhwa = {
            "id": id,
            "url": url,
            "title": unidecode(title),
            "summary": summary,
            "image": image,
        }

        if capthers:
            manhwa["chapters"] = Generic.chapters(url)

        return manhwa

    @staticmethod
    def chapters(url):
        response = Generic.scraper.post(url + f"/ajax/chapters")
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find_all("li", class_="wp-manga-chapter")

        chapters = []

        for cape in capes:
            title = cape.find("a").get_text().strip()
            url = cape.find("a").get("href")
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
    def pages(chapter: str, content):
        if content:
            html = content
        else:
            response = Generic.scraper.get(chapter)
            html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find_all("img", class_="wp-manga-chapter-img")

        pages = []

        for cape in capes:
            src = cape.get("data-src") or cape.get("src")
            url = src.strip()
            pages.append(url)

        return pages

    @staticmethod
    def chapter(chapter_link: str):
        response = Generic.scraper.get(chapter_link)
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
            "pages": Generic.pages(chapter_link, html),
        }
