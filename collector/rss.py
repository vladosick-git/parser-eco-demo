"""Потоковый разбор RSS 2.0 и Atom без сторонних библиотек (лента РЭО весит 21 МБ)."""

import io
import xml.etree.ElementTree as ET


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def iter_items(content: bytes):
    """Отдаёт словари {title, url, summary, published, category} по одному на элемент ленты."""
    for _, elem in ET.iterparse(io.BytesIO(content), events=("end",)):
        name = _local(elem.tag)
        if name not in ("item", "entry"):
            continue
        fields: dict[str, str] = {}
        categories = []
        for child in elem:
            key = _local(child.tag)
            text = (child.text or "").strip()
            if key == "link" and not text:
                text = child.get("href", "")  # Atom: <link href="..."/>
            if key == "category":
                categories.append(text or child.get("term", ""))
            elif key not in fields:
                fields[key] = text
        yield {
            "title": fields.get("title", ""),
            "url": fields.get("link") or fields.get("guid", ""),
            "summary": fields.get("description") or fields.get("summary") or fields.get("content", ""),
            "published": fields.get("pubdate") or fields.get("published") or fields.get("updated")
                         or fields.get("date"),
            "category_hint": " ".join(c for c in categories if c),
            "author": fields.get("author") or fields.get("creator"),
        }
        elem.clear()
