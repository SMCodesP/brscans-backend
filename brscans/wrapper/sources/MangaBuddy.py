from brscans.wrapper.sources.Comizy import Comizy


class MangaBuddy(Comizy):
    """mangabuddy.com agora redireciona (301) para comizy.io.

    O slug se mantém, então a URL antiga do banco continua servindo.
    """

    def __init__(self, url, headers=None) -> None:
        super().__init__(url, headers)
        self.name = "MangaBuddy"
