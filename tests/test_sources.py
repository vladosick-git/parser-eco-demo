"""Разбор каждого адаптера на сохранённых образцах из fixtures/, без сети."""

from datetime import datetime
from pathlib import Path

import httpx

from collector.http import PoliteClient
from collector.items import build_news_item, build_waste_item
from collector.normalize import MSK
from collector.sources import discover
from collector.sources.ecosphere import Ecosphere
from collector.sources.mnr import Minprirody
from collector.sources.reo import Reo
from collector.sources.solidwaste import SolidWaste
from collector.sources.wasteru_board import WasteRuBoard
from collector.sources.wasteru_news import WasteRuNews
from collector.sources.zakupki import Zakupki

FIX = Path(__file__).resolve().parent.parent / "fixtures"
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=MSK)


def fixture(name: str) -> bytes:
    return (FIX / name).read_bytes()


def test_discover_finds_all_approved_sources():
    ids = {s.id for s in discover()}
    assert ids == {"mnr", "reo", "wasteru_news", "ecosphere", "solidwaste", "zakupki", "wasteru_board"}


def test_mnr_rss():
    src = Minprirody()
    raws = src.parse(fixture("mnr_rss.xml"), src.urls[0])
    assert len(raws) == 4
    item = build_news_item(raws[0], src, NOW)
    assert item["url"].startswith("http://www.mnr.gov.ru/press/news/")
    assert item["published"] == "2026-10-16T16:49:24+03:00"
    assert 0 < len(item["summary"]) <= 300
    assert "<" not in item["summary"]


def test_reo_rss_trimmed_fixture():
    src = Reo()
    raws = src.parse(fixture("reo_rss.xml"), src.urls[0])
    assert len(raws) == 7
    newest = max(raws, key=lambda r: build_news_item(r, src, NOW)["published"])
    assert build_news_item(newest, src, NOW)["published"].startswith("2026-10-13")


def test_wasteru_news_rss_converts_timezone():
    src = WasteRuNews()
    raws = src.parse(fixture("wasteru_rss.xml"), src.urls[0])
    assert len(raws) == 10
    item = build_news_item(raws[0], src, NOW)
    assert item["published"] == "2026-09-29T13:20:00+03:00"   # было +0600
    assert item["category"] == "Мероприятия"                   # ВэйстТэк 2026


def test_ecosphere_drops_author():
    src = Ecosphere()
    raws = src.parse(fixture("ecosphere_musor.xml"), src.urls[0])
    assert len(raws) == 20
    assert all("author" not in r for r in raws)
    assert all(len(build_news_item(r, src, NOW)["summary"]) <= 300 for r in raws)


def test_solidwaste_html_list():
    src = SolidWaste()
    raws = src.parse(fixture("solidwaste_news.html"), src.urls[0])
    assert len(raws) == 15
    first = build_news_item(raws[0], src, NOW)
    assert first["url"] == "https://www.solidwaste.ru/news/view/33319.html"
    assert first["published"] == "2026-10-15"
    assert first["summary"].startswith("Опубликовано Постановление")
    assert first["category"] == "Законодательство"


def test_zakupki_rss_keeps_only_waste_tenders():
    src = Zakupki()
    raws = src.parse(fixture("zakupki_rss.xml"), src.urls[0])
    titles = [r["title"] for r in raws]
    assert len(raws) == 6
    assert not any("благоустройству" in t or "ремонту" in t for t in titles)
    items = [build_waste_item(r, src, NOW) for r in raws]
    first = items[0]
    assert first["offer_type"] == "вывоз"
    assert first["category"] == "Опасные отходы"           # медицинские отходы
    assert (first["price"], first["currency"]) == (11926200.0, "RUB")
    assert first["region_code"] == "50"                     # из КПП в ИКЗ
    assert first["organization"].startswith("ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ УЧРЕЖДЕНИЕ")
    chelyabinsk = next(i for i in items if "№ 6 Г. ЧЕЛЯБИНСК" in i["organization"])
    assert chelyabinsk["region_code"] == "74"               # 223-ФЗ: регион из названия заказчика
    assert chelyabinsk["offer_type"] == "утилизация"        # «вывоз и обезвреживание»


def test_wasteru_board_index_and_category():
    categories = WasteRuBoard.parse_index(fixture("wasteru_board_index.html"))
    names = {name: count for name, _, count in categories}
    assert names["Вторичные пластмассы"] == 86
    assert names["Инструменты и оборудование"] == 9

    url = "https://www.waste.ru/modules/adslight/viewcats.php?cid=2"
    rows, pages = WasteRuBoard.parse_category(fixture("wasteru_board_cat2.html"), url)
    assert len(rows) == 30
    assert rows[0]["offer_hint"] == "Продаю:"
    assert rows[0]["url"] == "https://www.waste.ru/modules/adslight/viewads.php?lid=21502"
    assert len(pages) == 2 and all("min=" in p for p in pages)


def test_wasteru_board_ad_has_no_contacts():
    ad = WasteRuBoard.parse_ad(fixture("wasteru_board_ad.html"))
    assert ad["price"] == "5500.00 руб."
    assert ad["published"] == "16.10.2026"
    raw = {"title": "ВИР-технология Ремонт кровли ВИР-ПЛАСТ", "region_text": "Тубольцы, Почепский район",
           "url": "https://www.waste.ru/modules/adslight/viewads.php?lid=21513", "offer_hint": "Продаю:", **ad}
    item = build_waste_item(raw, WasteRuBoard(), NOW)
    dumped = str(item)
    assert "+7" not in dumped and "seller" not in dumped and "details" not in item
    assert item["price"] == 5500.0 and item["offer_type"] == "продам"


class _FakeBoardHttp:
    """Отдаёт образцы вместо сети и запоминает, какие адреса запрашивались."""

    def __init__(self):
        self.calls = []

    def get(self, url, conditional=True):
        self.calls.append(url)
        if "viewads.php" in url:
            body = fixture("wasteru_board_ad.html")
        elif "viewcats.php?cid=2" in url and "min=" in url:
            # все страницы раздела отдают одни и те же объявления: проверяем, что карточки не качаются дважды
            body = fixture("wasteru_board_cat2.html")
        elif "viewcats.php" in url:
            body = b"<html></html>"
        else:
            body = fixture("wasteru_board_index.html")
        return httpx.Response(200, content=body, request=httpx.Request("GET", url))


def test_wasteru_board_fetches_cards_only_for_new_ads():
    http = _FakeBoardHttp()
    items, _ = WasteRuBoard().collect(http, known_urls=set())
    cards = [u for u in http.calls if "viewads.php" in u]
    assert len(cards) == len(set(cards)) == 30
    assert len(items) == 90                                  # 3 страницы по 30 строк, дубли отсечёт merge
    assert any("min=0&orderby=dateD" in u for u in http.calls)
    assert not any("cid=11" in u for u in http.calls)       # оборудование пропускаем

    http2 = _FakeBoardHttp()
    WasteRuBoard().collect(http2, known_urls={i["url"] for i in items})
    assert sum("viewads.php" in u for u in http2.calls) == 0


def test_politeclient_works_with_fake_board(monkeypatch):
    # адаптер биржи совместим с настоящим клиентом: robots.txt проверяется и для неё
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: *print.php\n")
        return httpx.Response(200, content=fixture("wasteru_board_index.html"))

    client = PoliteClient({}, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    resp = client.get("https://www.waste.ru/modules/adslight/", conditional=False)
    assert resp.status_code == 200
