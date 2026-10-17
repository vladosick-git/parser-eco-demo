from .base import RssSource


class WasteRuNews(RssSource):
    id = "wasteru_news"
    name = "Отходы.Ру"
    homepage = "https://www.waste.ru/"
    urls = ["https://www.waste.ru/backend.php"]
