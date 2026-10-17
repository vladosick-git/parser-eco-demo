"""Один запуск сбора: все источники по очереди, ошибка одного не останавливает остальные."""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import audit, config, notify, storage
from .dedup import merge
from .http import PoliteClient
from .items import build_news_item, build_waste_item
from .normalize import MSK
from .sources import discover

log = logging.getLogger("collector")

BUILDERS = {"news": build_news_item, "waste": build_waste_item}


def _too_old(item: dict, now: datetime) -> bool:
    published = item.get("published")
    limit = (now - timedelta(days=config.NEWS_MAX_AGE_DAYS)).date().isoformat()
    return bool(published) and published[:10] < limit


def _collect_one(source, http: PoliteClient, store: list[dict], now: datetime):
    """Возвращает (обновлённое хранилище, отчёт по источнику)."""
    report = {
        "source_id": source.id, "source_name": source.name, "kind": source.kind,
        "status": "ok", "fetched": 0, "new": 0, "duplicates": 0, "skipped": 0, "errors": 0,
        "error": None, "duration_s": 0.0,
    }
    started = time.monotonic()
    cache_backup = dict(http.http_cache)
    try:
        known = {i["url"] for i in store if i["source_id"] == source.id}
        raws, not_modified = source.collect(http, known)
        items = []
        for raw in raws:
            item = BUILDERS[source.kind](raw, source, now)
            if item is None or (source.kind == "news" and _too_old(item, now)):
                report["skipped"] += 1
                continue
            items.append(item)
        store, report["new"], report["duplicates"] = merge(store, items)
        report["fetched"] = len(raws)
        if not_modified:
            report["status"] = "not_modified"
    except Exception as exc:  # noqa: BLE001 - любой сбой источника пишем в журнал и идём дальше
        # ответы неудачного источника не должны оставить ETag, иначе следующий запуск получит 304
        http.http_cache.clear()
        http.http_cache.update(cache_backup)
        report.update(status="error", errors=1, error=f"{type(exc).__name__}: {exc}"[:500])
        log.exception("Источник %s упал", source.id)
    report["duration_s"] = round(time.monotonic() - started, 1)
    log.info("%-14s %-12s получено %3d, новых %3d, дублей %3d, пропущено %3d",
             source.id, report["status"], report["fetched"], report["new"],
             report["duplicates"], report["skipped"])
    return store, report


def export(data_dir: Path = config.DATA_DIR) -> None:
    """CSV, таблица источников из docs/AUDIT.md и bundle.js для витрины. Сети не требует."""
    news = storage.load_json(data_dir / "news.json", [])
    waste = storage.load_json(data_dir / "waste.json", [])
    runs = storage.load_json(data_dir / "runs.json", [])
    sources = audit.parse(config.AUDIT_PATH.read_text(encoding="utf-8"))
    storage.save_csv(data_dir / "news.csv", news, storage.NEWS_CSV_FIELDS)
    storage.save_csv(data_dir / "waste.csv", waste, storage.WASTE_CSV_FIELDS)
    storage.save_json(data_dir / "sources.json", sources)
    # браузер не даёт fetch() читать файлы с диска, поэтому для file:// те же данные лежат и в JS
    storage.save_bundle(data_dir / "bundle.js", {"news": news, "waste": waste, "runs": runs, "sources": sources})


def run(only: set[str] | None = None, data_dir: Path = config.DATA_DIR, http: PoliteClient | None = None,
        sources=None) -> dict:
    now = datetime.now(MSK)
    started = time.monotonic()
    stores = {
        "news": storage.load_json(data_dir / "news.json", []),
        "waste": storage.load_json(data_dir / "waste.json", []),
    }
    http_cache = storage.load_json(data_dir / "http_cache.json", {})
    own_client = http is None
    http = http or PoliteClient(http_cache)

    reports = []
    try:
        for source in sources if sources is not None else discover():
            if only and source.id not in only:
                continue
            stores[source.kind], report = _collect_one(source, http, stores[source.kind], now)
            reports.append(report)
    finally:
        if own_client:
            http.close()

    errors = sum(r["errors"] for r in reports)
    record = {
        "run_id": now.isoformat(timespec="seconds"),
        "started_at": now.isoformat(timespec="seconds"),
        "finished_at": datetime.now(MSK).isoformat(timespec="seconds"),
        "duration_s": round(time.monotonic() - started, 1),
        "status": "ok" if not errors else ("failed" if errors == len(reports) else "partial"),
        "totals": {key: sum(r[key] for r in reports) for key in ("fetched", "new", "duplicates", "skipped", "errors")},
        "sources": reports,
    }

    storage.save_json(data_dir / "news.json", stores["news"])
    storage.save_json(data_dir / "waste.json", stores["waste"])
    storage.save_json(data_dir / "http_cache.json", http.http_cache)
    runs = storage.load_json(data_dir / "runs.json", [])
    storage.save_json(data_dir / "runs.json", ([record] + runs)[: config.RUNS_KEEP])
    export(data_dir)

    if errors:
        notify.send_failure(record)
    return record
