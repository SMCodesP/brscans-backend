import httpx
from bs4 import BeautifulSoup
import re
from unidecode import unidecode

from brscans.manhwa.models import Chapter, Manhwa
from brscans.wrapper.sources.Generic import Generic

class Mangatown(Generic):
    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "Mangatown"

    @staticmethod
    def info(url, capthers: bool = False):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = httpx.get(url, headers=headers, follow_redirects=True)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Get ID
        og_url = soup.find("meta", property="og:url")
        if og_url:
            manga_id = og_url.get("content").rstrip("/").split("/")[-1]
        else:
            manga_id = url.rstrip("/").split("/")[-1]

        # Title
        title_tag = soup.find("h1", class_="title-top")
        title = title_tag.get_text().strip() if title_tag else "Manga"

        # Summary
        summary_span = soup.find("span", id="hide") or soup.find("span", id="show")
        summary = summary_span.get_text().strip() if summary_span else "Resumo não encontrado"

        # Image/Cover
        detail_info = soup.find("div", class_="detail_info")
        image = None
        if detail_info:
            img = detail_info.find("img")
            if img:
                image = img.get("src")
        
        if not image:
            og_img = soup.find("meta", property="og:image")
            if og_img:
                image = og_img.get("content")

        manhwa = {
            "id": manga_id,
            "url": url,
            "title": unidecode(title),
            "summary": summary,
            "image": image,
        }

        if capthers:
            manhwa["chapters"] = Mangatown.chapters(url)

        return manhwa

    @staticmethod
    def chapters(manhwa: Manhwa):
        url = manhwa if isinstance(manhwa, str) else manhwa.source
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = httpx.get(url, headers=headers, follow_redirects=True)
        soup = BeautifulSoup(r.text, "html.parser")

        chapter_ul = soup.find("ul", class_="chapter_list")
        chapters = []
        if chapter_ul:
            lis = chapter_ul.find_all("li")
            for li in lis:
                a_tag = li.find("a")
                if a_tag:
                    href = a_tag.get("href")
                    title = a_tag.get_text().strip()
                    span = li.find("span", class_="time") or li.find("span")
                    date = span.get_text().strip().capitalize() if span else ""
                    
                    full_url = href
                    if href.startswith("/"):
                        full_url = "https://sso.mangatown.com" + href
                    elif not href.startswith("http"):
                        full_url = "https://sso.mangatown.com/" + href

                    chapter_id = href.rstrip("/").split("/")[-1]

                    # Clean the title to keep only the chapter number
                    clean_title = unidecode(title)
                    match = re.search(r'c([0-9.]+)', chapter_id)
                    if match:
                        clean_title = match.group(1)
                    else:
                        num_match = re.search(r'([0-9.]+)', title)
                        if num_match:
                            clean_title = num_match.group(1)

                    chapters.append({
                        "id": chapter_id,
                        "title": clean_title,
                        "url": full_url,
                        "release_date": date,
                    })
        return chapters

    @staticmethod
    def pages(chapter: Chapter, content: str = None):
        if content:
            html = content
        else:
            url = chapter if isinstance(chapter, str) else chapter.source
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            response = httpx.get(url, headers=headers, follow_redirects=True)
            html = response.text

        soup = BeautifulSoup(html, "html.parser")
        imgs = soup.find_all("img", class_="image")
        pages = []
        for img in imgs:
            src = img.get("src")
            if src:
                src = src.strip()
                if src.startswith("//"):
                    src = "https:" + src
                pages.append(src)
        return pages

    @staticmethod
    def chapter(chapter: Chapter):
        url = chapter if isinstance(chapter, str) else chapter.source
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = httpx.get(url, headers=headers, follow_redirects=True)
        html = r.text
        soup = BeautifulSoup(html, "html.parser")

        # Get Title of chapter
        title_meta = soup.find("meta", property="og:title")
        title = title_meta.get("content") if title_meta else ""

        # Chapter identifier / element
        chapter_element = ""
        select_tag = soup.find("select", class_="chapter_select") or soup.find("select", id="top_chapter_list")
        if select_tag:
            opt = select_tag.find("option", selected=True)
            if opt:
                chapter_element = opt.get_text().strip()
        
        if not chapter_element:
            m = re.search(r'/c([0-9.]+)/?$', url)
            if m:
                chapter_element = f"Ch.{m.group(1)}"
            else:
                chapter_element = url.rstrip("/").split("/")[-1]

        return {
            "title": title,
            "chapter": chapter_element,
            "pages": Mangatown.pages(chapter, html),
        }
