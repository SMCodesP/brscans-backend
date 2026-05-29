import httpx
from bs4 import BeautifulSoup, ResultSet, Tag
from unidecode import unidecode

from brscans.wrapper.sources.Generic import Generic


class Mangayy(Generic):
    def __init__(self, url, headers=None) -> None:
        self.headers = headers
        self.url = url
        self.client = httpx.Client(timeout=None)
        self.name = "Mangayy"

    def homepage(self):
        response = self.client.get(self.url, headers={"Referer": self.url})
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        capes: ResultSet[Tag] = soup.find_all("div", class_="page-item-detail")
        manhwas = []

        for cape in capes:
            title = cape.find("h3").get_text().strip()
            img = cape.find("img")
            image = img.get("data-src") or img.get("src")
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
