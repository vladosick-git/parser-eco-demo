from .base import RssSource


class Reo(RssSource):
    """Лента большая (21 МБ, все новости с 2020 года), сервер не отдаёт ETag и Last-Modified.
    Старые записи отсекает окно NEWS_MAX_AGE_DAYS в ядре."""

    id = "reo"
    name = "РЭО"
    homepage = "https://reo.ru/news"
    urls = ["https://reo.ru/rss-feed-975076876151.xml"]
