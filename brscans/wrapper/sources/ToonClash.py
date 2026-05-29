import httpx
from bs4 import BeautifulSoup
from brscans.wrapper.sources.Generic import Generic
from brscans.manhwa.models import Chapter, Manhwa


class ToonClash(Generic):
    client = httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    def __init__(self, url, headers=None) -> None:
        super().__init__(url, headers)
        self.name = "ToonClash"

    @staticmethod
    def info(url, capthers: bool = False):
        manhwa = Generic.info(url, capthers=False)
        if capthers:
            manhwa["chapters"] = ToonClash.chapters(url)
        return manhwa

    @staticmethod
    def chapters(manhwa: Manhwa):
        source_url = manhwa.source if hasattr(manhwa, "source") else manhwa
        response = ToonClash.client.get(source_url)
        soup = BeautifulSoup(response.text, "html.parser")
        
        chapters = []
        for cape in soup.find_all("li", class_="wp-manga-chapter"):
            link = cape.find("a")
            release_span = cape.find("span", class_="chapter-release-date")
            chapters.append({
                "id": link.get("href").split("/")[-2],
                "title": link.get_text().strip(),
                "url": link.get("href"),
                "release_date": release_span.get_text().strip().capitalize() if release_span else "None",
            })
        return chapters

    @staticmethod
    def pages(chapter: Chapter, content: str = None):
        if not content:
            source_url = chapter.source if hasattr(chapter, "source") else chapter
            content = ToonClash.client.get(source_url).text
        return Generic.pages(chapter, content)

    @staticmethod
    def chapter(chapter: Chapter):
        source_url = chapter.source if hasattr(chapter, "source") else chapter
        html = ToonClash.client.get(source_url).text
        soup = BeautifulSoup(html, "html.parser")
        
        chapter_element = soup.find("li", class_="active")
        title = soup.find("meta", property="og:title")
        
        class MockChapter:
            def __init__(self, source):
                self.source = source
        
        chapter_obj = chapter if hasattr(chapter, "source") else MockChapter(source_url)

        return {
            "title": title.get("content") if title else "",
            "chapter": chapter_element.get_text().strip() if chapter_element else None,
            "pages": ToonClash.pages(chapter_obj, html),
        }
