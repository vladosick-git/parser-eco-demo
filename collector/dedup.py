"""Дедупликация: ключ по ссылке внутри источника и ключ по содержанию между источниками."""

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING = re.compile(r"^(utm_\w+|ysclid|fbclid|gclid|yclid|from|_openstat)$", flags=re.I)


def canonical_url(url: str) -> str:
    """Схема и хост в нижнем регистре, без www, без трекинговых параметров, якоря и хвостового «/»."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)))
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https" if parts.scheme in ("http", "https") else parts.scheme, host, path, query, ""))


def title_fingerprint(title: str) -> str:
    t = title.lower().replace("ё", "е")
    t = re.sub(r"[^\w]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def url_key(source_id: str, url: str) -> str:
    return _hash(f"{source_id}|{canonical_url(url)}")


def content_key(title: str, published: str | None) -> str:
    return _hash(f"{title_fingerprint(title)}|{(published or '')[:10]}")


def merge(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], int, int]:
    """Добавляет новые записи к существующим. Возвращает (все записи, новых, дубликатов).

    Запись считается дубликатом, если совпал её id (источник + ссылка) или content_key
    (заголовок + дата) с уже известной записью, в том числе из другого источника.
    Уже сохранённые записи не перезаписываются: первая увиденная версия остаётся.
    """
    seen_ids = {item["id"] for item in existing}
    seen_content = {item["content_key"] for item in existing}
    merged = list(existing)
    new = dup = 0
    for item in incoming:
        if item["id"] in seen_ids or item["content_key"] in seen_content:
            dup += 1
            continue
        seen_ids.add(item["id"])
        seen_content.add(item["content_key"])
        merged.append(item)
        new += 1
    merged.sort(key=lambda i: (i.get("published") or "", i["id"]), reverse=True)
    return merged, new, dup
