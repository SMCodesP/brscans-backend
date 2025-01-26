from brscans.wrapper.sources.Generic import Generic
from brscans.wrapper.sources.KingOfShojo import KingOfShojo


sources = {"kingofshojo.com": KingOfShojo, "other": Generic}


def get_source_by_link(link: str):
    hostname = link.split("/")[2]
    return sources.get(hostname, Generic)
