from datetime import datetime
from types import SimpleNamespace

from collector.dedup import canonical_url, content_key, merge, title_fingerprint, url_key
from collector.items import build_news_item, build_waste_item
from collector.normalize import MSK

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=MSK)
SRC_A = SimpleNamespace(id="a", name="Источник A")
SRC_B = SimpleNamespace(id="b", name="Источник B")


def test_canonical_url():
    assert canonical_url("HTTP://WWW.Example.ru/news/1/?utm_source=x&b=2&a=1#top") == \
        "https://example.ru/news/1?a=1&b=2"
    assert canonical_url("https://example.ru/") == "https://example.ru/"


def test_title_fingerprint_ignores_case_punctuation_and_yo():
    assert title_fingerprint("Ёлки: «Переработка» \u2014 2026!") == title_fingerprint("елки переработка 2026")


def test_keys_are_stable():
    assert url_key("a", "https://x.ru/1?utm_medium=y") == url_key("a", "https://www.x.ru/1/")
    assert url_key("a", "https://x.ru/1") != url_key("b", "https://x.ru/1")
    assert content_key("Новость", "2026-10-16T10:00:00+03:00") == content_key("новость!", "2026-10-16")


def _news(src, title, url, date="2026-10-16"):
    return build_news_item({"title": title, "url": url, "published": date}, src, NOW)


def test_merge_counts_new_and_duplicates():
    first = [_news(SRC_A, "Новость 1", "https://a.ru/1"), _news(SRC_A, "Новость 2", "https://a.ru/2")]
    store, new, dup = merge([], first)
    assert (len(store), new, dup) == (2, 2, 0)

    # повторный запуск с теми же данными не создаёт дубликатов
    store, new, dup = merge(store, first)
    assert (len(store), new, dup) == (2, 0, 2)


def test_merge_detects_same_story_from_other_source():
    store, _, _ = merge([], [_news(SRC_A, "РЭО подвёл итоги года", "https://a.ru/1")])
    other = _news(SRC_B, "РЭО подвел итоги года.", "https://b.ru/77", date="2026-10-16T15:00:00+03:00")
    store, new, dup = merge(store, [other])
    assert (len(store), new, dup) == (1, 0, 1)


def test_merge_dedups_inside_one_batch_and_sorts_newest_first():
    batch = [
        _news(SRC_A, "Старая", "https://a.ru/old", "2026-01-01"),
        _news(SRC_A, "Новая", "https://a.ru/new", "2026-10-01"),
        _news(SRC_A, "Новая", "https://a.ru/new?utm_source=tg", "2026-10-01"),
    ]
    store, new, dup = merge([], batch)
    assert (new, dup) == (2, 1)
    assert [i["title"] for i in store] == ["Новая", "Старая"]


def test_build_news_item_cleans_and_limits_fields():
    raw = {
        "title": "<b>Мусоровозы</b> передал в Курскую область",
        "summary": "<p>" + "Текст " * 200 + "</p>",
        "url": "https://www.mnr.gov.ru/press/news/1/",
        "published": "Fri, 16 Oct 2026 16:22:40 +0300",
        "author": "Иванов И.И.",
    }
    item = build_news_item(raw, SRC_A, NOW)
    assert item["title"] == "Мусоровозы передал в Курскую область"
    assert len(item["summary"]) <= 300
    assert item["published"] == "2026-10-16T16:22:40+03:00"
    assert item["category"] == "Отходы и ТКО"
    assert "author" not in item


def test_build_news_item_rejects_missing_link():
    assert build_news_item({"title": "Без ссылки"}, SRC_A, NOW) is None
    assert build_news_item({"title": "", "url": "https://a.ru/1"}, SRC_A, NOW) is None


def test_build_waste_item_from_tender():
    raw = {
        "title": "Оказание услуг по сбору, транспортировке и утилизации отходов I-IV класса опасности",
        "url": "https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=1",
        "published": "Fri, 16 Oct 2026 14:13:16 GMT",
        "price": "2688317.22 Российский рубль",
        "organization": "КОМИТЕТ ПО ВОПРОСАМ ЗАКОННОСТИ",
        "region_code": "78",
    }
    item = build_waste_item(raw, SRC_A, NOW)
    assert item["offer_type"] == "утилизация"
    assert item["hazard_classes"] == [1, 2, 3, 4]
    assert (item["price"], item["currency"]) == (2688317.22, "RUB")
    assert (item["region_code"], item["region"]) == ("78", "Санкт-Петербург")
    assert item["organization"] == "КОМИТЕТ ПО ВОПРОСАМ ЗАКОННОСТИ"


def test_build_waste_item_drops_private_person_and_contacts():
    raw = {
        "title": "Куплю ПВД плёнку, тел. 89202534083",
        "url": "https://www.waste.ru/modules/adslight/viewads.php?lid=1",
        "published": "16.10.2026",
        "offer_hint": "Покупаю:",
        "price": "15 руб.",
        "region_text": "Рязань",
        "organization": "Петров Пётр",
    }
    item = build_waste_item(raw, SRC_A, NOW)
    assert "8920" not in item["title"]
    assert item["organization"] is None
    assert item["offer_type"] == "куплю"
    assert item["region"] == "Рязанская область"
    assert item["fkko"] is None
