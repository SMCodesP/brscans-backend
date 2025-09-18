import re

import httpx
from bs4 import BeautifulSoup, ResultSet, Tag
from cloudscraper import CloudScraper
from unidecode import unidecode

from brscans.wrapper.sources.Generic import Generic


class MangaBuddy(Generic):
    scraper = CloudScraper.create_scraper()

    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "MangaBuddy"

    @staticmethod
    def info(url, capthers: bool = False):
        response = Generic.scraper.get(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        id = soup.find("meta", property="og:url").get("content").split("/")[-2]
        title = soup.find("div", class_="detail").find("h1").get_text().strip()
        image = soup.find("div", class_="img-cover").find("img")
        image = image.get("data-src") or image.get("src")
        image = re.sub(r"-\d+x\d+(?=\.\w{3,4}$)", "", image)

        manhwa = {
            "id": id,
            "url": url,
            "title": unidecode(title),
            "summary": "",
            "image": image,
        }

        if capthers:
            manhwa["chapters"] = MangaBuddy.chapters(url)

        return manhwa

    @staticmethod
    def chapters(url):
        response = Generic.scraper.get(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find("ul", id="chapter-list").find_all("li")

        chapters = []

        for cape in capes[:2]:
            title = cape.find("a").find("strong").get_text().strip()
            chapter_url = "https://mangabuddy.com" + cape.find("a").get("href")
            chapter = {
                "id": chapter_url.split("/")[-1],
                "title": unidecode(title),
                "url": chapter_url,
                "release_date": cape.find("time", class_="chapter-update")
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
            response = MangaBuddy.scraper.get(chapter)
            html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find("div", id="chapter-images").find_all("img")
        print(capes)

        pages = []

        for cape in capes:
            src = cape.get("data-src") or cape.get("src")
            url = src.strip()
            pages.append(url)

        return pages

    @staticmethod
    def chapter(chapter_link: str):
        response = MangaBuddy.scraper.get(chapter_link)
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
            "pages": MangaBuddy.pages(chapter_link, html),
        }



def extract_vars(soup):
    scripts = soup.find_all("script")

    js_text = " ".join(script.get_text() for script in scripts)

    patterns = {
        "bookId": r'var\s+bookId\s*=\s*(\d+);',
        "bookSlug": r'var\s+bookSlug\s*=\s*"([^"]+)";',
        "chapterSlug": r'var\s+chapterSlug\s*=\s*"([^"]+)";',
        "chapterId": r'var\s+chapterId\s*=\s*(\d+);',
        "pageTitle": r'var\s+pageTitle\s*=\s*"([^"]+)";',
        "pageSubTitle": r'var\s+pageSubTitle\s*=\s*"([^"]+)";',
        "bookCover": r'var\s+bookCover\s*=\s*"([^"]+)";',
    }

    result = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, js_text)
        if match:
            result[key] = match.group(1)

    return result
