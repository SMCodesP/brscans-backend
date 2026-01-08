from copyreg import constructor
import re
from unidecode import unidecode
import httpx
import xmltodict
from bs4 import BeautifulSoup, ResultSet, Tag, NavigableString, Comment


class Nexo:
    def __init__(self, headers=None) -> None:
        self.headers = headers
        self.url = "https://nexoscans.net"
        self.name = "NexoScans"

    def homepage(self):
        response = httpx.get(self.url)
        # print(response)
        # return []
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        capes: ResultSet[Tag] = soup.find_all("div", class_="page-item-detail")
        manhwas = []

        for cape in capes:
            title = cape.find("h3").get_text().strip()
            image = cape.find("img").get("src")
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

    def all(self):
        response = httpx.get(self.url + "/wp-manga-sitemap.xml")
        urls = xmltodict.parse(response.content)["urlset"]["url"]
        return urls

    def search(self, query: str):
        response = httpx.get(self.url, params={"s": query, "post_type": "wp-manga"})
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find_all("div", class_="c-tabs-item__content")
        manhwas = []

        for cape in capes:
            title = cape.find("div", class_="post-title").get_text().strip()
            image = cape.find("img").get("src")
            image = f"{image.rsplit('-', 1)[0]}.{image.split('.')[-1]}"

            manhwa = {
                "id": cape.find("a").get("href").split("/")[-2],
                "title": unidecode(title),
                "url": cape.find("a").get("href"),
                "image": image,
                "upscaled_image": f"http://localhost:8000/wrapper/anime4k?image={image}",
            }
            manhwas.append(manhwa)

        return manhwas

    def info(self, id: str, capthers: bool = False, url: str = None):
        response = httpx.post(url or self.url + f"/manga/{id}/", follow_redirects=False)
        html = response.text

        if response.status_code == 301:
            return None

        soup = BeautifulSoup(html, "html.parser")

        manga_extra = soup.find(id="wp-manga-js-extra").get_text()
        madara_extra = soup.find(id="madara-js-js-extra").get_text()

        id = re.search(r'"manga_id":"(\d+)"', manga_extra).group(1)
        slug = re.search(r'"manga-core":"([^"]+)"', madara_extra).group(1)

        title = soup.find("div", class_="post-title").find("h1").get_text().strip()
        content: Tag = soup.find("div", class_="manga-excerpt").get_text().strip()
        image = soup.find("div", class_="summary_image").find("img").get("src")

        status = (
            self.get_content_item(soup.find(class_="post-status"), "Status")
            .get_text()
            .strip()
        )

        genres = soup.find("div", class_="genres-content")
        genres = genres.find_all("a") if genres else []
        genres = [genre.get_text().strip() for genre in genres]

        manhwa = {
            "id": id,
            "title": unidecode(title),
            "summary": content,
            "image": image,
            "status": status,
            "genres": genres,
            "slug": slug,
        }

        if capthers:
            manhwa["chapters"] = self.chapters(id)

        return manhwa

    def get_content_item(self, content: Tag, searchable: str) -> str:
        if content:
            items = content.find_all("div", class_="post-content_item") or []
            for item in items:
                title = item.find(class_="summary-heading").get_text().strip()
                if title == searchable:
                    return item.find("div", class_="summary-content")

    def chapters(self, id: str):
        response = httpx.post(
            self.url + f"/wp-admin/admin-ajax.php",
            data={
                "action": "manga_get_reading_nav",
                "manga": id,
                "style": "list",
                "type": "manga",
                "volume_id": 0,
            },
        )
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find_all("option")

        chapters = []

        for cape in capes:
            chapter = {
                "id": cape.get("value"),
                "title": cape.get_text().strip(),
            }
            chapters.append(chapter)

        return chapters

    def pages(self, manhwa: str, chapter: str):
        print(f"{self.url}/manga/{manhwa}/{chapter}")
        response = httpx.get(f"{self.url}/manga/{manhwa}/{chapter}/")
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find_all("img", class_="wp-manga-chapter-img")

        pages = []

        for cape in capes:
            url = cape.get("src").strip()
            pages.append(url)

        return pages
