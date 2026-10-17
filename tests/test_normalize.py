from datetime import datetime

import pytest

from collector import normalize as n
from collector.normalize import MSK
from collector.regions import match_region, region_from_kpp

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=MSK)


def test_clean_text_strips_html_entities_and_spaces():
    raw = "&lt;b&gt;Утилизация&lt;/b&gt;&nbsp; отходов <br/>\n  в   СПб"
    assert n.clean_text(raw) == "Утилизация отходов в СПб"


def test_truncate_respects_limit_and_word_boundary():
    text = "слово " * 100
    out = n.truncate(text.strip(), 50)
    assert len(out) <= 50
    assert out.endswith("…")
    assert not out[:-1].endswith(" ")
    assert n.truncate("коротко", 50) == "коротко"


def test_scrub_pii_removes_phones_and_emails():
    text = "Куплю ПНД, звоните +7 (977) 326-37-88 или 89202534083, пишите a.b@mail.ru"
    out = n.scrub_pii(text)
    assert "977" not in out and "8920" not in out and "@" not in out
    assert out.startswith("Куплю ПНД")


@pytest.mark.parametrize("value, expected", [
    ("Fri, 16 Oct 2026 14:13:16 GMT", "2026-10-16T17:13:16+03:00"),
    ("Tue, 29 Sep 2026 16:20:00 +0600", "2026-09-29T13:20:00+03:00"),
    ("2026-10-13T11:39:00+03:00", "2026-10-13T11:39:00+03:00"),
    ("2026-10-13", "2026-10-13"),
    ("16.10.2026", "2026-10-16"),
    ("Добавлено: 16.10.2026", "2026-10-16"),
    ("16.10.2026 09:30", "2026-10-16T09:30:00+03:00"),
    ("15 октября", "2026-10-15"),
    ("28 декабря", "2025-12-28"),          # в будущем -> прошлый год
    ("3 мая 2024", "2024-05-03"),
    ("", None),
    ("не дата", None),
])
def test_parse_date(value, expected):
    assert n.parse_date(value, NOW) == expected


def test_news_category_priority():
    assert n.news_category("Госдума приняла закон об отходах") == "Законодательство"
    assert n.news_category("ВэйстТэк 2026: от создания мощностей") == "Мероприятия"
    assert n.news_category("Сибстекло запустило переработку стеклобоя") == "Переработка"
    assert n.news_category("Регоператор закупил мусоровозы") == "Отходы и ТКО"
    assert n.news_category("В заповеднике выпустили ушастых ежей") == "Экология"


def test_waste_category():
    assert n.waste_category("Куплю отходы стретч пленки") == "Пластик"
    assert n.waste_category("Продаем архив МС 7Б1") == "Макулатура"
    assert n.waste_category("Купим лом алюминиевой банки") == "Металл"
    assert n.waste_category("Вывоз жидких бытовых отходов") == "Жидкие отходы"
    assert n.waste_category("Сбор отработанных ртутных ламп") == "Опасные отходы"
    assert n.waste_category("Ремонт кровли") == "Прочее"


@pytest.mark.parametrize("text, hint, expected", [
    ("Смесь битумно-полимерная", "Продаю:", "продам"),
    ("Куплю стретч пленку", "Покупаю:", "куплю"),
    ("Оказание услуг по сбору, транспортировке и утилизации ЖБО", None, "утилизация"),
    ("Оказание услуг по вывозу ТКО", None, "вывоз"),
    ("Закупаем макулатуру на постоянной основе", None, "куплю"),
    ("Продаем ящик ПП прессованный", None, "продам"),
    ("Линия грануляции", None, None),
])
def test_offer_type(text, hint, expected):
    assert n.offer_type(text, hint) == expected


@pytest.mark.parametrize("text, expected", [
    ("5500.00 руб. /за штуку", (5500.0, "RUB")),
    ("5 500,50 руб.", (5500.5, "RUB")),
    ("2688317.22 Валюта: Российский рубль", (2688317.22, "RUB")),
    ("1,5 млн руб", (1500000.0, "RUB")),
    ("100 EUR", (100.0, "EUR")),
    ("0 руб.", (None, None)),
    ("договорная", (None, None)),
    (None, (None, None)),
])
def test_parse_price(text, expected):
    assert n.parse_price(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("на складе 20000 кг", (20.0, "т")),
    ("объём 15 тонн в месяц", (15.0, "т")),
    ("100 м3", (100.0, "м3")),
    ("500 шт", (500.0, "шт")),
    ("без объёма", (None, None)),
])
def test_parse_volume(text, expected):
    assert n.parse_volume(text) == expected


def test_fkko_normalization_and_hazard():
    assert n.normalize_fkko("Отход 4 34 110 02 29 5, полиэтилен") == "43411002295"
    assert n.normalize_fkko("ФККО: 43411002295") == "43411002295"
    assert n.normalize_fkko("код ФККО 4-34-110-02-29-5") == "43411002295"
    assert n.normalize_fkko("звоните 89773263788") is None   # 11 цифр, но это телефон
    assert n.normalize_fkko("ФККО 1234") is None
    assert n.hazard_from_fkko("43411002295") == 5
    assert n.hazard_from_fkko("43411002290") is None


@pytest.mark.parametrize("text, expected", [
    ("Услуги по обращению с отходами I-IV класса опасности", [1, 2, 3, 4]),
    ("отходов III, IV классов опасности", [3, 4]),
    ("отходы 4 и 5 класса", [4, 5]),
    ("с I по III класс", [1, 2, 3]),
    ("отходы IV класса", [4]),
    ("Вывоз ТКО", []),
])
def test_hazard_classes(text, expected):
    assert n.parse_hazard_classes(text) == expected


def test_organization_keeps_legal_entities_only():
    assert n.organization("КОМИТЕТ ПО ВОПРОСАМ ЗАКОННОСТИ") == "КОМИТЕТ ПО ВОПРОСАМ ЗАКОННОСТИ"
    assert n.organization("ООО «Вторресурс»") == "ООО «Вторресурс»"
    assert n.organization("ИП Иванов Иван Иванович") is None
    assert n.organization("Иванов Иван") is None
    assert n.organization("rbkm") is None
    assert n.organization_in_text("ООО ТЕХНОПРОГРЕСС производство гранулы") == "ООО ТЕХНОПРОГРЕСС"
    assert n.organization_in_text("Куплю ПНД") is None


@pytest.mark.parametrize("text, code", [
    ("Брянская обл., Почепский р-н, с.Тубольцы", "32"),
    ("Россия, Московская обл", "50"),
    ("Москва", "77"),
    ("г. Санкт-Петербург", "78"),
    ("Татарстан Респ", "16"),
    ("Нижний Новгород", "52"),
    ("Набережные Челны", "16"),
    ("Южно-Сахалинск", "65"),
    ("Алтайский край, Бийск", "22"),
    ("Республика Алтай", "04"),
    ("Тубольцы, Почепский район", None),
    ("", None),
])
def test_match_region(text, code):
    assert match_region(text) == code


def test_region_from_kpp():
    assert region_from_kpp("784201001") == "78"
    assert region_from_kpp("990001001") is None
    assert region_from_kpp(None) is None
