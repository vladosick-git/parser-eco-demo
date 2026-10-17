from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Source


class SolidWaste(Source):
    """Журнал «Твёрдые бытовые отходы». RSS нет, разбираем HTML-список новостей.
    Дата в списке без года («15 октября»), год восстанавливает normalize.parse_date."""

    id = "solidwaste"
    name = "Журнал «Твёрдые бытовые отходы»"
    homepage = "https://www.solidwaste.ru/news.html"
    urls = ["https://www.solidwaste.ru/news.html"]

    def parse(self, content: bytes, url: str) -> list[dict]:
        soup = BeautifulSoup(content, "html.parser")
        items = []
        date = None
        for row in soup.select("td.newsDate, tr.row > td"):
            if "newsDate" in (row.get("class") or []):
                date = row.get_text(" ", strip=True)
                continue
            link = row.find("a", href=lambda h: h and "/news/view/" in h)
            if not link:
                continue
            for junk in row.select("div.allRatingList, link"):
                junk.decompose()
            title = link.get_text(" ", strip=True)
            link.extract()
            items.append({
                "title": title,
                "url": urljoin(url, link["href"]),
                "summary": row.get_text(" ", strip=True),
                "published": date,
            })
        return items
