import re
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from .base import Source

BASE = "https://www.waste.ru/modules/adslight/"

# Оборудование это не отходы; услуги берём, только если речь о вывозе или утилизации.
SKIP_CATEGORIES = {"Инструменты и оборудование"}
SERVICE_CATEGORIES = {"Услуги"}
SERVICE_RE = re.compile(r"вывоз|утилиз|переработ|обезвреж|демеркуриз", re.I)


class WasteRuBoard(Source):
    """Биржа отходов Отходы.Ру. Логин автора, телефон и текст объявления не сохраняются:
    из карточки берутся только цена, дата и город, текст нужен лишь для определения типа и ФККО."""

    id = "wasteru_board"
    name = "Биржа отходов Отходы.Ру"
    kind = "waste"
    homepage = BASE
    urls = [BASE]

    @staticmethod
    def parse_index(content: bytes) -> list[tuple[str, str, int]]:
        """Главная биржи -> [(название раздела, ссылка, число объявлений)]."""
        soup = BeautifulSoup(content, "html.parser")
        result = []
        for a in soup.find_all("a", href=re.compile(r"viewcats\.php\?cid=\d+$")):
            name = a.get_text(strip=True)
            tail = a.next_sibling if isinstance(a.next_sibling, str) else ""
            m = re.search(r"\[(\d+)\]", tail or "")
            if name and m:
                result.append((name, urljoin(BASE, a["href"]), int(m.group(1))))
        return result

    @staticmethod
    def parse_category(content: bytes, url: str) -> tuple[list[dict], list[str]]:
        """Страница раздела -> (строки объявлений, ссылки на следующие страницы)."""
        soup = BeautifulSoup(content, "html.parser")
        rows = []
        for tr in soup.find_all("tr", class_=("odd", "even")):
            link = tr.find("a", href=re.compile(r"^viewads\.php\?lid=\d+"))
            cells = tr.find_all("td", recursive=False)
            if not link or len(cells) < 3:
                continue
            body = cells[1].get_text(" ", strip=True)
            title = link.get_text(" ", strip=True)
            hint = body[len(title):].strip()
            rows.append({
                "title": title,
                "url": urljoin(url, link["href"]),
                "offer_hint": hint,
                "region_text": cells[2].get_text(" ", strip=True),
            })
        pages = []
        for a in soup.select("div.generic-pagination a[href]"):
            href = urljoin(url, a["href"])
            if href not in pages and parse_qs(urlsplit(href).query).get("min"):
                pages.append(href)
        return rows, pages

    @staticmethod
    def parse_ad(content: bytes) -> dict:
        """Карточка объявления -> цена, дата, текст для анализа. Контакты не извлекаются."""
        soup = BeautifulSoup(content, "html.parser")
        block = soup.find("h1")
        price_p = block.find_next("p") if block else None
        details = price_p.find_next("p") if price_p else None
        price_text = price_p.find("strong").get_text(" ", strip=True) if price_p and price_p.find("strong") else ""
        side = soup.find(string=re.compile("Добавлено"))
        published = side.parent.next_sibling if side else None
        return {
            "price": price_text,
            "published": str(published).strip() if published else None,
            "details": details.get_text(" ", strip=True) if details else "",
        }

    def collect(self, http, known_urls: set[str]) -> tuple[list[dict], bool]:
        index = http.get(BASE, conditional=False)
        items = []
        cards: dict[str, dict] = {}  # объявление может попасться на двух страницах, карточку берём один раз
        for name, cat_url, count in self.parse_index(index.content):
            if name in SKIP_CATEGORIES or count == 0:
                continue
            # первая страница по умолчанию сортируется иначе, чем следующие, поэтому сортировку задаём явно
            cat_url += "&min=0&orderby=dateD&show=30"
            queue, seen = [cat_url], {cat_url}
            while queue:
                page_url = queue.pop(0)
                rows, pages = self.parse_category(http.get(page_url, conditional=False).content, page_url)
                queue += [p for p in pages if p not in seen]
                seen.update(pages)
                for row in rows:
                    if name in SERVICE_CATEGORIES:
                        if not SERVICE_RE.search(row["title"]):
                            continue
                        row["offer_hint"] = None
                    row["category_hint"] = name
                    if row["url"] not in known_urls:
                        if row["url"] not in cards:
                            cards[row["url"]] = self.parse_ad(http.get(row["url"], conditional=False).content)
                        row.update(cards[row["url"]])
                    items.append(row)
        return items, False
