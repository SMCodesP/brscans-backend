import json
import os

import httpx
from unidecode import unidecode

from brscans.manhwa.models import Chapter, Manhwa


class MangaHub:
    API_URL = "https://api.mghcdn.com/graphql"
    # token = "8fd6c9b4407191fc0fc4b71fba011686"
    token = os.environ.get("MANGAHUB_TOKEN")

    def __init__(self):
        self.client = httpx.Client(
            timeout=None,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/138.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.7",
                "Origin": "https://mangahub.io",
                "Referer": "https://mangahub.io/",
                "Content-Type": "application/json",
                "x-mhub-access": MangaHub.token,  # 🔑 ESSENCIAL
            },
        )

    @staticmethod
    def _post(query: str, variables: dict = None):
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        r = MangaHub().client.post(MangaHub.API_URL, json=payload)
        r.raise_for_status()
        data = r.json()

        if "errors" in data:
            print("é deu erro")
            raise Exception(data["errors"])
        return data["data"]

    @staticmethod
    def info(url, capthers: bool = False):
        slug = url.split("/")[-1]
        query = """
        query ($slug: String!) {
          manga(x: m01, slug: $slug) {
            id
            title
            slug
            image
            description
            chapters {
              id
              number
              title
              slug
              date
            }
          }
        }
        """
        data = MangaHub._post(query, {"slug": slug})
        print(data.get("manga").get("id"))

        manhwa = {
            "id": int(data.get("manga").get("id")),
            "url": url,
            "title": unidecode(data.get("manga").get("title")),
            "summary": data.get("manga").get("description"),
            "image": f"https://thumb.mghcdn.com/{data.get('manga').get('image')}",
            "slug": data.get("manga").get("slug"),
        }

        if capthers:
            chapters = []
            for ch in data["manga"]["chapters"]:
                chapters.append(
                    {
                        "number": ch["number"],
                        "title": unidecode(ch["title"]),
                        "url": f"https://mangahub.io/chapter/{slug}/{ch['slug']}",
                    }
                )

        return manhwa

    @staticmethod
    def chapters(manhwa: Manhwa):
        query = """
        query ($slug: String!) {
          manga(x: m01, slug: $slug) {
            chapters {
              id
              number
              title
              slug
            }
          }
        }
        """
        print("manhwa.slug", manhwa.slug)
        data = MangaHub._post(query, {"slug": manhwa.slug})
        chapters = []

        for ch in data["manga"]["chapters"]:
            chapters.append(
                {
                    "id": ch["number"],
                    "title": unidecode(ch["title"]),
                    "url": f"https://mangahub.io/chapter/{manhwa.slug}/{ch['slug']}",
                }
            )

        return chapters

    @staticmethod
    def chapter(chapter: Chapter):
        slug = chapter.manhwa.slug
        query = """
        query ($slug: String!, $number: Float!) {
          chapter(x: m01, slug: $slug, number: $number) {
            id
            title
            mangaID
            number
            slug
            date
            pages
            manga {
              id
              title
              slug
            }
          }
        }
        """
        data = MangaHub._post(query, {"slug": slug, "number": chapter.slug})
        ch = data["chapter"]

        pages = json.loads(ch["pages"])
        page_urls = [f"https://imgx.mghcdn.com/{pages['p']}{img}" for img in pages["i"]]

        return {
            "id": ch["id"],
            "title": ch["title"],
            "number": ch["number"],
            "slug": ch["slug"],
            "date": ch["date"],
            "pages": page_urls,
            "manga": ch["manga"],
        }

    @staticmethod
    def pages(chapter: Chapter):
        chapter_data = MangaHub.chapter(chapter)
        return chapter_data["pages"]
