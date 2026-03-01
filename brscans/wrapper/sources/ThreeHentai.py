import re

from bs4 import BeautifulSoup
from unidecode import unidecode

from brscans.manhwa.models import Chapter, Manhwa
from brscans.wrapper.sources.Generic import Generic


class ThreeHentai(Generic):
    def __init__(self, url, headers=None) -> None:
        super().__init__(url, headers)
        self.name = "ThreeHentai"

    @staticmethod
    def info(url, capthers: bool = False):
        response = Generic.scraper.get(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        # ID extraction: https://pt.3hentai.net/d/669632 -> 669632
        id = url.rstrip("/").split("/")[-1]

        # Title extraction
        title_tag = soup.find("h1")
        if title_tag:
            title = title_tag.get_text().strip()
        else:
            # Fallback to meta title
            meta_title = soup.find("meta", property="og:title")
            title = meta_title.get("content") if meta_title else "Unknown Title"

        # Image extraction
        # Try to find the cover image
        image = ""
        cover_img = soup.find("img", attrs={"src": re.compile(r"cover\.jpg")})
        if cover_img:
            image = cover_img.get("src")

        if not image:
            # Fallback: check other images
            first_img = soup.find("img", attrs={"src": re.compile(r"\/d\d+\/")})
            if first_img:
                image = first_img.get("data-src") or first_img.get("src")

        manhwa = {
            "id": id,
            "url": url,
            "title": unidecode(title),
            "summary": "Hentai Gallery",
            "image": image,
        }

        if capthers:
            manhwa["chapters"] = ThreeHentai.chapters(manhwa)

        return manhwa

    @staticmethod
    def chapters(manhwa: Manhwa):
        # Return a single chapter representing the whole gallery
        # If manhwa is a dict (from info calls), handle it
        source_url = (
            manhwa.source if hasattr(manhwa, "source") else manhwa.get("url")
        )

        return [
            {
                "id": "gallery",
                "title": "Full Gallery",
                "url": source_url,
                "release_date": "Recently",
            }
        ]

    @staticmethod
    def pages(chapter: Chapter, content: str = None):
        if content:
            html = content
        else:
            if isinstance(chapter, dict):
                url = chapter.get("url")
            else:
                url = chapter.source
            response = ThreeHentai.scraper.get(url)
            html = response.text

        soup = BeautifulSoup(html, "html.parser")

        # Find all thumbnail images
        # They seem to be standard <img> tags with src containing /d.../ and ending in t.jpg
        # Example: https://s9.3hentai.net/d1131110/1t.jpg

        pages = []

        # Look for all likely gallery images.
        # Strategy: Find images that have 't.jpg' or similar pattern.
        imgs = soup.find_all("img")

        for img in imgs:
            src = img.get("data-src") or img.get("src")
            if not src:
                continue

            # Check if it looks like a gallery thumbnail (contains numeric path and ends with t.jpg)
            # We want to enable high res, so we strip the 't' before the extension
            # e.g. 1t.jpg -> 1.jpg

            # Simple check: ends with t.jpg
            if src.endswith("t.jpg"):
                full_res = src[:-5] + ".jpg"
                pages.append(full_res)
            elif src.endswith("cover.jpg"):
                # Skip the cover if it appears in the list
                pass
            elif "/d" in src and "t." in src:
                # More generic replacement if extension varies
                full_res = re.sub(r"t(\.[a-z]{3,4})$", r"\1", src)
                pages.append(full_res)

        # Allow duplicates? Usually pages are unique. But list order matters.
        # Ensure we don't have duplicates and preserve order if possible
        # Set is unordered, but we can do a quick unique list
        seen = set()
        unique_pages = []
        for p in pages:
            if p not in seen:
                unique_pages.append(p)
                seen.add(p)

        return unique_pages

    @staticmethod
    def chapter(chapter: Chapter):
        return {
            "title": chapter.title,
            "chapter": "Gallery",
            "pages": ThreeHentai.pages(chapter),
        }
