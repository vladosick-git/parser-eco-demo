"""Общий интерфейс адаптера источника."""

from ..rss import iter_items


class Source:
    """Адаптер одного источника.

    Чтобы добавить источник, создайте модуль в collector/sources/ с подклассом Source:
    задайте id, name, kind ("news" или "waste"), urls и реализуйте parse().
    Ядро найдёт его само. Если источнику нужно несколько шагов (список -> карточки),
    переопределите collect().
    """

    id: str = ""
    name: str = ""
    kind: str = "news"
    homepage: str = ""
    urls: list[str] = []
    enabled: bool = True

    def parse(self, content: bytes, url: str) -> list[dict]:
        """Ответ источника -> список сырых записей (словарей). Без сети, чтобы тестировать на fixtures/."""
        raise NotImplementedError

    def collect(self, http, known_urls: set[str]) -> tuple[list[dict], bool]:
        """Скачивает и разбирает все urls. Возвращает (сырые записи, «ничего не изменилось»)."""
        items: list[dict] = []
        changed = False
        for url in self.urls:
            resp = http.get(url)
            if resp is None:
                continue
            changed = True
            items.extend(self.parse(resp.content, url))
        return items, not changed


class RssSource(Source):
    """Источник с обычной RSS-лентой."""

    def parse(self, content: bytes, url: str) -> list[dict]:
        # author и прочие поля с возможными ФИО дальше не передаются
        return [
            {k: item[k] for k in ("title", "url", "summary", "published", "category_hint")}
            for item in iter_items(content)
        ]
