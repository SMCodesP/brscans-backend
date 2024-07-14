import os
from pathlib import Path
import tempfile
import requests


from brscans import settings


class Anime4k:
    def __init__(self):
        self.parameters = ac.Parameters()
        self.parameters.HDN = True

    def upscale_image(self, image: Path, url: str):
        temp_up = os.path.join(settings.MEDIA_ROOT, "imagens", f"{hash(url)}.png")
        return temp_up

    def upscale_remote_image(self, image: str, suffix_input: str = ".webp"):
        if os.path.exists(
            os.path.join(settings.MEDIA_ROOT, "imagens", f"{hash(image)}.png")
        ):
            return os.path.join(settings.MEDIA_ROOT, "imagens", f"{hash(image)}.png")

        response = requests.get(image)
        temp = Path(tempfile.mkstemp(suffix=suffix_input)[1])
        temp.write_bytes(response.content)

        return self.upscale_image(temp, image)
        # return temp
