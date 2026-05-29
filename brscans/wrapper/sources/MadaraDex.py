from brscans.wrapper.sources.Generic import Generic


class MadaraDex(Generic):
    def __init__(self, url, headers=None) -> None:
        super().__init__(url, headers)
        self.name = "MadaraDex"
