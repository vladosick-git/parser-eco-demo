"""Сборка нормализованных записей из сырых данных адаптеров. Схема описана в docs/SCHEMA.md."""

from datetime import datetime

from . import normalize as n
from .dedup import content_key, url_key
from .regions import match_region, region_name


def _base(raw: dict, source, now: datetime) -> dict | None:
    title = n.truncate(n.scrub_pii(n.clean_text(raw.get("title"))), 200)
    url = (raw.get("url") or "").strip()
    if not title or not url.startswith(("http://", "https://")):
        return None
    published = n.parse_date(raw.get("published"), now)
    return {
        "id": url_key(source.id, url),
        "content_key": content_key(title, published),
        "source_id": source.id,
        "source_name": source.name,
        "title": title,
        "published": published,
        "url": url,
        "collected_at": now.astimezone(n.MSK).isoformat(timespec="seconds"),
    }


def build_news_item(raw: dict, source, now: datetime) -> dict | None:
    """Сырая новость -> запись. Возвращает None, если нет заголовка или ссылки."""
    item = _base(raw, source, now)
    if item is None:
        return None
    summary = n.scrub_pii(n.clean_text(raw.get("summary")))
    # некоторые ленты начинают описание с повтора заголовка
    if summary.lower().startswith(item["title"].lower()):
        summary = summary[len(item["title"]):].lstrip(" .:-")
    summary = n.truncate(summary)
    item["summary"] = summary
    item["category"] = n.news_category(item["title"], summary, raw.get("category_hint") or "")
    return item


def build_waste_item(raw: dict, source, now: datetime) -> dict | None:
    """Сырое объявление или закупка -> запись. Контакты и описания физлиц сюда не попадают."""
    item = _base(raw, source, now)
    if item is None:
        return None
    text = " ".join(filter(None, [item["title"], n.clean_text(raw.get("details"))]))
    fkko = n.normalize_fkko(raw.get("fkko") or text)
    hazard = n.parse_hazard_classes(text)
    if not hazard and n.hazard_from_fkko(fkko):
        hazard = [n.hazard_from_fkko(fkko)]
    price, currency = n.parse_price(raw.get("price"))
    volume, volume_unit = n.parse_volume(raw.get("volume") or text)
    region = raw.get("region_code") or match_region(raw.get("region_text"))
    org = n.organization(raw.get("organization")) or n.organization_in_text(item["title"])
    item.update({
        "offer_type": n.offer_type(text, raw.get("offer_hint")),
        "category": n.waste_category(text, raw.get("category_hint") or ""),
        "fkko": fkko,
        "hazard_classes": hazard,
        "volume": volume,
        "volume_unit": volume_unit,
        "price": price,
        "currency": currency,
        "region_code": region,
        "region": region_name(region),
        "organization": org,
    })
    return item
