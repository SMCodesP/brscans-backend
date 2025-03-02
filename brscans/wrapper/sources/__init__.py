from brscans.wrapper.sources.Generic import Generic
from brscans.wrapper.sources.KingOfShojo import KingOfShojo
from brscans.wrapper.sources.ManhuaRead import ManhuaRead
from brscans.wrapper.sources.Manhuaus import Manhuaus
from brscans.wrapper.sources.RizzFables import RizzFables


sources = {
    "kingofshojo.com": KingOfShojo,
    "manhuaread.com": ManhuaRead,
    "manhuaus.org": Manhuaus,
    "rizzfables.com": RizzFables,
    "other": Generic,
}


def get_source_by_link(link: str):
    hostname = link.split("/")[2]
    return sources.get(hostname, Generic)
