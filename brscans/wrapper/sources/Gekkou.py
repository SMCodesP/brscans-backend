from copyreg import constructor
from unidecode import unidecode
from bs4 import BeautifulSoup, ResultSet, Tag, NavigableString, Comment
import cloudscraper


class Gekkou:
    def __init__(self, headers=None) -> None:
        self.headers = headers
        self.url = "https://gekkou.site"
        self.client = cloudscraper.create_scraper()

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

    def search(self, query: str):
        response = self.client.get(
            self.url, params={"s": query, "post_type": "wp-manga"}
        )
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find_all("div", class_="c-tabs-item__content")
        manhwas = []

        for cape in capes:
            title = cape.find("div", class_="post-title").get_text().strip()
            image = cape.find("img").get("data-src")
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

    def info(self, id: str, capthers: bool = False):
        response = self.client.post(self.url + f"/manga/{id}/")
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        title = soup.find("div", id="manga-title").get_text().strip()
        content: Tag = soup.find_all("div", class_="post-content_item")[-1]
        image = soup.find("div", class_="summary_image").find("img").get("data-src")

        manhwa = {
            "id": id,
            "title": unidecode(title),
            "summary": next(content.find("div").stripped_strings),
            "image": image,
        }

        if capthers:
            manhwa["chapters"] = self.chapters(id)

        return manhwa

    def chapters(self, id: str):
        response = self.client.post(self.url + f"/manga/{id}/ajax/chapters")
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
                "thumbnail": None,
            }
            chapters.append(chapter)

        return chapters

    def pages(self, manhwa: str, chapter: str, upscale: bool = False):
        print(f"{self.url}/manga/{manhwa}/{chapter}")
        response = self.client.get(f"{self.url}/manga/{manhwa}/{chapter}/")
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        capes: ResultSet[Tag] = soup.find_all("img", class_="wp-manga-chapter-img")

        pages = []

        for cape in capes:
            url = cape.get("data-src").strip()
            if upscale:
                url = f"http://localhost:8000/wrapper/anime4k?image={url}"
            pages.append(url)

        return pages
