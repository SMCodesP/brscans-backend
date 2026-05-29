from brscans.wrapper.sources.FlowerManga import FlowerManga
from brscans.wrapper.sources.Generic import Generic
from brscans.wrapper.sources.KingOfShojo import KingOfShojo
from brscans.wrapper.sources.KunManga import KunManga
from brscans.wrapper.sources.MadaraDex import MadaraDex
from brscans.wrapper.sources.MangaBuddy import MangaBuddy
from brscans.wrapper.sources.Mangadass import Mangadass
from brscans.wrapper.sources.MangaHub import MangaHub
from brscans.wrapper.sources.Mangayy import Mangayy
from brscans.wrapper.sources.ManhuaFast import ManhuaFast
from brscans.wrapper.sources.ManhuaRead import ManhuaRead
from brscans.wrapper.sources.Manhuaus import Manhuaus
from brscans.wrapper.sources.Manhwahub import Manhwahub
from brscans.wrapper.sources.Neroxus import Neroxus
from brscans.wrapper.sources.RizzFables import RizzFables
from brscans.wrapper.sources.ThreeHentai import ThreeHentai
from brscans.wrapper.sources.Webtoon import Webtoon
from brscans.wrapper.sources.ToonClash import ToonClash
from brscans.wrapper.sources.Mangatown import Mangatown

sources = {
    "webtoons.com": Webtoon,
    "www.webtoons.com": Webtoon,
    "m.webtoons.com": Webtoon,
    "kingofshojo.com": KingOfShojo,
    "manhuaread.com": ManhuaRead,
    "manhuaus.org": Manhuaus,
    "rizzfables.com": RizzFables,
    "manhwahub.net": Manhwahub,
    "mangadass.com": Mangadass,
    "flowermanga.net": FlowerManga,
    "neroxus.com.br": Neroxus,
    "kunmanga.com": KunManga,
    "mangabuddy.com": MangaBuddy,
    "mangahub.io": MangaHub,
    "mangayy.org": Mangayy,
    "manhuafast.net": ManhuaFast,
    "pt.3hentai.net": ThreeHentai,
    "3hentai.net": ThreeHentai,
    "toonclash.com": ToonClash,
    "www.toonclash.com": ToonClash,
    "madaradex.org": MadaraDex,
    "www.madaradex.org": MadaraDex,
    "sso.mangatown.com": Mangatown,
    "www.mangatown.com": Mangatown,
    "mangatown.com": Mangatown,
    "other": Generic,
}


def get_source_by_link(link: str):
    hostname = link.split("/")[2]
    return sources.get(hostname, Generic)
