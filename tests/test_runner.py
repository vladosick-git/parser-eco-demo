"""Запуск целиком на подставных источниках: журнал, повторный запуск, падение одного источника."""

import json

import httpx
import pytest

from collector import audit, config, notify, runner
from collector.http import PoliteClient
from collector.sources.base import RssSource

RSS = """<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel>
<item><title>РЭО подвёл итоги переработки</title><link>https://good.ru/1</link>
<description>Короткий анонс</description><pubDate>{date}</pubDate></item>
<item><title>Закон об отходах принят</title><link>https://good.ru/2</link>
<pubDate>{date}</pubDate></item>
</channel></rss>"""


class GoodSource(RssSource):
    id, name, urls = "good", "Рабочий источник", ["https://good.ru/rss"]


class BrokenSource(RssSource):
    id, name, urls = "broken", "Сломанный источник", ["https://broken.ru/rss"]


class CopySource(RssSource):
    """Перепечатывает ту же новость: должна отсечься дедупликацией между источниками."""
    id, name, urls = "copy", "Перепечатка", ["https://copy.ru/rss"]


@pytest.fixture
def client():
    from datetime import datetime
    date = datetime.now().strftime("%a, %d %b %Y 10:00:00 +0300")

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "broken.ru":
            return httpx.Response(500)
        body = RSS.format(date=date)
        if request.url.host == "copy.ru":
            body = body.replace("https://good.ru/", "https://copy.ru/news/")
        return httpx.Response(200, text=body)

    return PoliteClient({}, transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_run_isolates_failures_and_dedups(tmp_path, client, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send_failure", lambda record: sent.append(record))
    sources = [GoodSource(), BrokenSource(), CopySource()]

    record = runner.run(data_dir=tmp_path, http=client, sources=sources)
    by_id = {r["source_id"]: r for r in record["sources"]}
    assert record["status"] == "partial"
    assert by_id["good"]["new"] == 2
    assert by_id["broken"]["status"] == "error" and "500" in by_id["broken"]["error"]
    assert by_id["copy"]["new"] == 0 and by_id["copy"]["duplicates"] == 2
    assert len(sent) == 1

    news = json.loads((tmp_path / "news.json").read_text(encoding="utf-8"))
    assert len(news) == 2
    assert (tmp_path / "news.csv").read_text(encoding="utf-8-sig").startswith("published;")

    # повторный запуск: новых записей нет, журнал растёт
    record2 = runner.run(data_dir=tmp_path, http=client, sources=sources)
    assert record2["totals"]["new"] == 0
    runs = json.loads((tmp_path / "runs.json").read_text(encoding="utf-8"))
    assert [r["run_id"] for r in runs] == [record2["run_id"], record["run_id"]]
    assert len(json.loads((tmp_path / "news.json").read_text(encoding="utf-8"))) == 2


def test_failed_source_does_not_keep_etag(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "send_failure", lambda record: None)

    class Exploding(RssSource):
        id, name, urls = "boom", "Падает при разборе", ["https://boom.ru/rss"]

        def parse(self, content, url):
            raise ValueError("битая разметка")

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="<rss/>", headers={"ETag": '"x"'})

    client = PoliteClient({}, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    record = runner.run(data_dir=tmp_path, http=client, sources=[Exploding()])
    assert record["status"] == "failed"
    assert json.loads((tmp_path / "http_cache.json").read_text(encoding="utf-8")) == {}


def test_notify_skips_without_secrets(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert notify.send_failure({"run_id": "x", "status": "failed", "sources": []}) is False


def test_notify_message_lists_failed_sources():
    text = notify.format_failure({"run_id": "r1", "status": "partial", "sources": [
        {"status": "ok", "source_name": "A", "error": None},
        {"status": "error", "source_name": "B", "error": "HTTPStatusError: 500"},
    ]})
    assert "B: HTTPStatusError: 500" in text and "A" not in text.split("\n", 1)[1]


def test_audit_tables_are_exported():
    data = audit.parse(config.AUDIT_PATH.read_text(encoding="utf-8"))
    assert data["checked"] == "2026-10-17"
    titles = [t["title"] for t in data["tables"]]
    assert titles == ["Раздел A. Новости", "Раздел B. Объявления и заказы по отходам"]
    decisions = {row["#"]: row["Решение"] for t in data["tables"] for row in t["rows"]}
    assert decisions["A1"] == "используем"
    assert decisions["B4"] == "нет"
