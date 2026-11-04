from brscans.wrapper.sources.Comizy import Comizy
from brscans.wrapper.sources.Generic import Generic
from brscans.wrapper.sources.KingOfShojo import KingOfShojo
from brscans.wrapper.sources.MadaraClone import MadaraClone
from brscans.wrapper.sources.MadaraDex import MadaraDex
from brscans.wrapper.sources.MangaBuddy import MangaBuddy
from brscans.wrapper.sources.Mangadass import Mangadass
from brscans.wrapper.sources.MangaThemesia import MangaThemesia
from brscans.wrapper.sources.RizzFables import RizzFables
from brscans.wrapper.sources.Webtoon import Webtoon
from brscans.wrapper.sources.ThreeHentai import ThreeHentai
from brscans.wrapper.sources.Mangatown import Mangatown

sources = {
    "webtoons.com": Webtoon,
    "m.webtoons.com": Webtoon,
    "kingofshojo.com": KingOfShojo,
    "rizzfables.com": RizzFables,
    "mangadass.com": Mangadass,
    "arenascan.com": MangaThemesia,
    "asterscans.com": MangaThemesia,
    "akazascans.org": MangaThemesia,
    "rokaricomics.com": MangaThemesia,
    "rackusreads.com": MangaThemesia,
    "mangabuddy.com": MangaBuddy,
    "comizy.io": Comizy,
    "pt.3hentai.net": ThreeHentai,
    "3hentai.net": ThreeHentai,
    "madaradex.org": MadaraDex,
    "sso.mangatown.com": Mangatown,
    "mangatown.com": Mangatown,
    # Madara conferidos de dentro da Lambda dev (2026-11-02): busca, ficha,
    # capítulos, capítulo e imagem. mangatop.org só publica os 30 capítulos
    # não à migração automática (que exige capítulos >= os nossos).
    "aquareader.org": Generic,
    "www.mangaread.org": Generic,
    "www.zazamanga.com": Generic,
    "mangatop.org": Generic,
    "manhwanex.com": Generic,
    "manhuanext.com": Generic,
    # NSFW (clones do Madara, um parser só).
    "manga18fx.com": MadaraClone,
    "manhwa18.cc": MadaraClone,
    "mangadna.com": MadaraClone,
    "other": Generic,
}


def get_source_by_link(link: str):
    hostname = link.split("/")[2].removeprefix("www.")
    return sources.get(hostname, Generic)


# Fontes cuja busca foi conferida de dentro da Lambda dev (Cloudflare bloqueia
# IP de datacenter): só elas aparecem na aba de migração.
searchable_sources = {
    host: sources[host]
    for host in (
        "mangadass.com",
        "rizzfables.com",
        "kingofshojo.com",
        "webtoons.com",
        "comizy.io",
        "arenascan.com",
        "asterscans.com",
        "akazascans.org",
        "rokaricomics.com",
        "rackusreads.com",
        "aquareader.org",
        "www.mangaread.org",
        "www.zazamanga.com",
        "mangatop.org",
        "manhwanex.com",
        "manhuanext.com",
        "3hentai.net",
        "manga18fx.com",
        "manhwa18.cc",
        "mangadna.com",
    )
}


# Fontes NSFW: a migração automática só leva manhwa `is_nsfw` para elas (e
# só tira de uma delas para outra NSFW).
nsfw_sources = {
    "3hentai.net",
    "pt.3hentai.net",
    "manga18fx.com",
    "manhwa18.cc",
    "mangadna.com",
}


def get_searchable_source(host: str):
    return searchable_sources.get(host) or searchable_sources.get(
        host.removeprefix("www.")
    )
