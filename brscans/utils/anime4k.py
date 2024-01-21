from pathlib import Path
import tempfile
import requests

from pyanime4k import ac
import pyanime4k


class Anime4k:
    def __init__(self):
        self.parameters = ac.Parameters()
        self.parameters.HDN = True

    def upscale_image(self, image: Path):
        temp_up = tempfile.mkstemp(suffix=".png")[1]
        a = ac.AC(False, False, type=ac.ProcessorType.CPUCNN)

        a.load_image(str(image.resolve()))
        a.process()
        a.save_image(temp_up)

        return temp_up

    def upscale_remote_image(self, image: str, suffix_input: str = ".webp"):
        response = requests.get(image)
        temp = Path(tempfile.mkstemp(suffix=suffix_input)[1])
        temp.write_bytes(response.content)

        return self.upscale_image(temp)
