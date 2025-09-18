from brscans.wrapper.sources.FlowerManga import FlowerManga
from brscans.wrapper.sources.Generic import Generic
from brscans.wrapper.sources.KingOfShojo import KingOfShojo
from brscans.wrapper.sources.KunManga import KunManga
from brscans.wrapper.sources.MangaBuddy import MangaBuddy
from brscans.wrapper.sources.MangaHub import MangaHub
from brscans.wrapper.sources.Mangadass import Mangadass
from brscans.wrapper.sources.ManhuaRead import ManhuaRead
from brscans.wrapper.sources.Manhuaus import Manhuaus
from brscans.wrapper.sources.Manhwahub import Manhwahub
from brscans.wrapper.sources.Neroxus import Neroxus
from brscans.wrapper.sources.RizzFables import RizzFables

sources = {
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
    "other": Generic,
}


def get_source_by_link(link: str):
    hostname = link.split("/")[2]
    return sources.get(hostname, Generic)
