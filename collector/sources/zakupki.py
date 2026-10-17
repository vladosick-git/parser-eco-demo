import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from ..regions import region_from_kpp
from ..rss import iter_items
from .base import Source

_SEARCH = "https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?"
_QUERIES = ["утилизация отходов", "вывоз отходов"]
# Поиск ЕИС с морфологией находит и ремонт дорог, поэтому оставляем только закупки про отходы.
_RELEVANT = re.compile(r"отход|мусор|\bтко\b|\bжбо\b|\bжко\b", re.I)


def _search_url(query: str) -> str:
    params = {
        "searchString": query, "morphology": "on", "fz44": "on", "fz223": "on",
        "af": "on",  # только этап «подача заявок»
        "sortBy": "UPDATE_DATE", "sortDirection": "false", "recordsPerPage": "_10",
    }
    return _SEARCH + urlencode(params)


class Zakupki(Source):
    """ЕИС «Госзакупки»: открытые закупки услуг по вывозу и утилизации отходов.

    Заказчики по 44-ФЗ и 223-ФЗ всегда организации. Пауза 60 с берётся из Crawl-delay в robots.txt.
    """

    id = "zakupki"
    name = "ЕИС «Госзакупки»"
    kind = "waste"
    homepage = "https://zakupki.gov.ru/"
    urls = [_search_url(q) for q in _QUERIES]

    @staticmethod
    def _fields(description_html: str) -> dict[str, str]:
        """«<strong>Название: </strong>значение<br/>» -> {"Название": "значение"}."""
        soup = BeautifulSoup(description_html, "html.parser")
        fields = {}
        for label in soup.find_all("strong"):
            key = label.get_text(strip=True).rstrip(":").strip()
            value = []
            for sib in label.next_siblings:
                if getattr(sib, "name", None) in ("strong", "br"):
                    break
                value.append(sib.get_text() if hasattr(sib, "get_text") else str(sib))
            if key and key not in fields:
                fields[key] = "".join(value).strip()
        return fields

    def parse(self, content: bytes, url: str) -> list[dict]:
        items = []
        for entry in iter_items(content):
            f = self._fields(entry["summary"])
            title = f.get("Наименование объекта закупки") or entry["title"]
            if not _RELEVANT.search(title):
                continue
            ikz = re.sub(r"\D", "", f.get("Идентификационный код закупки (ИКЗ)", ""))
            # ИКЗ: 2 цифры года, затем код заказчика (1 + ИНН 10 + КПП 9)
            kpp = ikz[13:22] if len(ikz) >= 22 else None
            price = f.get("Начальная цена контракта") or f.get("Начальная (максимальная) цена договора")
            currency = f.get("Валюта", "")
            items.append({
                "title": title,
                "url": entry["url"],
                "published": entry["published"] or f.get("Размещено"),
                "price": f"{price} {currency}" if price else None,
                "organization": f.get("Наименование Заказчика") or entry["author"],
                "region_code": region_from_kpp(kpp),
                # у закупок по 223-ФЗ нет ИКЗ, регион пробуем найти в названии заказчика
                "region_text": f.get("Наименование Заказчика"),
            })
        return items
