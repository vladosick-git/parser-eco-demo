from .base import RssSource


class Minprirody(RssSource):
    id = "mnr"
    name = "Минприроды России"
    homepage = "https://www.mnr.gov.ru/press/news/"
    urls = ["https://www.mnr.gov.ru/upload/iblock_rss_3.xml"]
