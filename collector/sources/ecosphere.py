from .base import RssSource


class Ecosphere(RssSource):
    """Общая лента издания шире темы проекта, поэтому берём только тематические теги."""

    id = "ecosphere"
    name = "Экосфера"
    homepage = "https://ecosphere.press/"
    urls = [
        "https://ecosphere.press/tag/musor/feed/",
        "https://ecosphere.press/tag/plastik/feed/",
        "https://ecosphere.press/tag/zakonodatelstvo/feed/",
    ]
