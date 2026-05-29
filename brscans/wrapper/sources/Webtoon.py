import re
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup, ResultSet, Tag
from unidecode import unidecode

from brscans.manhwa.models import Chapter, Manhwa
from brscans.wrapper.sources.Generic import Generic


class Webtoon(Generic):
    BASE_URL = "https://www.webtoons.com"
    HEADERS = {
        "Accept-Language": "en",
        "Referer": BASE_URL,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
    }

    def __init__(self, url, headers=None) -> None:
        self.headers = headers or self.HEADERS
        self.url = url
        self.client = httpx.Client(
            timeout=None,
            headers=self.headers,
            follow_redirects=True,
        )
        self.name = "Webtoon"

    @staticmethod
    def _get(url: str):
        return httpx.get(
            url,
            headers=Webtoon.HEADERS,
            timeout=None,
            follow_redirects=True,
        )

    @staticmethod
    def _source_url(source):
        return source.source if hasattr(source, "source") else source

    @staticmethod
    def _title_no(url: str):
        query = parse_qs(urlparse(url).query)
        title_no = query.get("title_no", [None])[0]
        if title_no:
            return title_no

        match = re.search(r"title_no=(\d+)", url)
        return match.group(1) if match else url.rstrip("/").split("/")[-1]

    @staticmethod
    def _chapter_number(url: str):
        query = parse_qs(urlparse(url).query)
        episode_no = query.get("episode_no", [None])[0]
        if episode_no:
            return episode_no

        match = re.search(r"episode_no=(\d+)", url)
        return match.group(1) if match else url.rstrip("/").split("/")[-1]

    @staticmethod
    def _remove_page_query(url: str):
        return re.sub(r"([?&])page=\d+&?", r"\1", url).rstrip("?&")

    @staticmethod
    def _episode_title(title: Tag):
        nested_title = title.find("span")
        title_element = nested_title or title
        return title_element.get_text(strip=True)

    @staticmethod
    def search(query: str, lang: str = "en"):
        response = Webtoon._get(
            f"{Webtoon.BASE_URL}/{lang}/search?keyword="
            f"{quote_plus(query)}&page=1"
        )
        soup = BeautifulSoup(response.text, "html.parser")
        items: ResultSet[Tag] = soup.find_all("li")

        manhwas = []
        seen = set()

        for item in items:
            link = item.find("a", href=re.compile(r"/list\?title_no=\d+"))
            title = item.find("strong", class_="title")
            image = item.find("img")

            if not link or not title or not image:
                continue

            url = link.get("href")
            if url in seen:
                continue

            seen.add(url)
            manhwas.append(
                {
                    "id": Webtoon._title_no(url),
                    "title": unidecode(title.get_text(strip=True)).upper(),
                    "url": url,
                    "image": image.get("src"),
                    "upscaled_image": (
                        f"http://localhost:8000/wrapper/anime4k?image="
                        f"{image.get('src')}"
                    ),
                }
            )

        return manhwas

    @staticmethod
    def info(url, capthers: bool = False):
        response = Webtoon._get(url)
        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        title = soup.find("h1", class_="subj") or soup.find(
            "meta", property="og:title"
        )
        summary = soup.find("meta", property="og:description")
        image = soup.find("meta", property="og:image")
        canonical = soup.find("link", rel="canonical")

        source_url = canonical.get("href") if canonical else url
        if title and title.name != "meta":
            title_text = title.get_text(strip=True)
        elif title:
            title_text = title.get("content", "")
        else:
            title_text = ""

        manhwa = {
            "id": Webtoon._title_no(source_url),
            "url": source_url,
            "title": unidecode(title_text),
            "summary": summary.get("content", "").strip()
            if summary
            else "Resumo não encontrado",
            "image": image.get("content") if image else "",
        }

        if capthers:
            manhwa["chapters"] = Webtoon.chapters(source_url)

        return manhwa

    @staticmethod
    def chapters(manhwa: Manhwa):
        source_url = Webtoon._remove_page_query(Webtoon._source_url(manhwa))
        chapters = []
        scraped_episode_numbers = set()
        page = 1

        while True:
            separator = "&" if "?" in source_url else "?"
            paginated_url = f"{source_url}{separator}page={page}"
            response = Webtoon._get(paginated_url)
            soup = BeautifulSoup(response.text, "html.parser")

            episode_list = soup.find("ul", id="_listUl")
            if not episode_list:
                break

            episode_items: ResultSet[Tag] = episode_list.find_all(
                "li", class_="_episodeItem"
            )
            if not episode_items:
                break

            new_episodes_found = False

            for item in episode_items:
                episode_number = item.get("data-episode-no")
                link = item.find("a")
                title = item.find("span", class_="subj")

                if not episode_number or not link or not title:
                    continue

                if episode_number in scraped_episode_numbers:
                    continue

                new_episodes_found = True
                scraped_episode_numbers.add(episode_number)
                url = link.get("href")
                release_date = item.find("span", class_="date")

                chapters.append(
                    {
                        "id": episode_number,
                        "title": unidecode(Webtoon._episode_title(title)),
                        "url": url,
                        "release_date": release_date.get_text(strip=True)
                        if release_date
                        else "",
                    }
                )

            if not new_episodes_found:
                break

            page += 1

        return sorted(chapters, key=lambda chapter: int(chapter["id"]))

    @staticmethod
    def pages(chapter: Chapter, content: str = None):
        if content:
            html = content
        else:
            response = Webtoon._get(Webtoon._source_url(chapter))
            html = response.text

        soup = BeautifulSoup(html, "html.parser")
        image_list = soup.find("div", id="_imageList")
        if not image_list:
            return []

        capes: ResultSet[Tag] = image_list.find_all("img", class_="_images")
        pages = []

        for cape in capes:
            src = cape.get("data-url") or cape.get("src")
            if src:
                pages.append(src.strip())

        return pages

    @staticmethod
    def chapter(chapter: Chapter):
        chapter_url = Webtoon._source_url(chapter)
        response = Webtoon._get(chapter_url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("meta", property="og:title")
        chapter_element = soup.find("h1", class_="subj_episode")

        return {
            "title": title.get("content") if title else "",
            "chapter": chapter_element.get_text(strip=True)
            if chapter_element
            else Webtoon._chapter_number(chapter_url),
            "pages": Webtoon.pages(chapter_url, html),
        }
