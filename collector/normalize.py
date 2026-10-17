"""Очистка и нормализация полей: текст, даты, категории, цены, объёмы, ФККО, классы опасности."""

import html
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from . import config

MSK = timezone(timedelta(hours=3))

NEWS_CATEGORIES = ["Законодательство", "Мероприятия", "Переработка", "Отходы и ТКО", "Экология"]
WASTE_CATEGORIES = [
    "Пластик", "Макулатура", "Металл", "Стекло", "Шины и резина", "Нефтепродукты",
    "Жидкие отходы", "ТКО", "Опасные отходы", "Прочее",
]
OFFER_TYPES = ["куплю", "продам", "вывоз", "утилизация"]

# Порядок важен: первая подходящая категория побеждает.
_NEWS_RULES = [
    ("Законодательство", r"закон|постановлен|приказ|норматив|правительств|госдум|поправк|регулир|"
                         r"\bфз\b|минприроды разработал|проект акта|правил[аео] обращения|тариф"),
    ("Мероприятия", r"выставк|форум|конференц|семинар|фестивал|преми[яию]|вэйсттэк|wastetech|ecoxpo|"
                    r"акци[яию]|субботник|совет промышленных"),
    ("Переработка", r"переработ|вторичн|вторсыр|рециклинг|утилизац|сортиров|макулатур|"
                    r"раздельн|экономик[аи] замкнутого"),
    ("Отходы и ТКО", r"отход|\bтко\b|мусор|полигон|свалк|регоператор|контейнер|вывоз"),
]
_WASTE_RULES = [
    ("Опасные отходы", r"ртут|люминесцент|медицинск|\bi{1,2}\s*класс|батаре|аккумулятор"),
    ("Жидкие отходы", r"\bжбо\b|жидких|жидкие|сточн|ил[аов]?\b"),
    ("ТКО", r"\bтко\b|твердых (коммунальных|бытовых)|крупногабарит|мусор"),
    ("Нефтепродукты", r"нефт|мазут|отработанн\w* масл"),
    ("Шины и резина", r"шин\b|шины|покрыш|резин|\bрти\b"),
    ("Стекло", r"стекл"),
    ("Металл", r"\bлом\b|металл|алюмин|\bмед[ьи]\b|латун"),
    ("Макулатура", r"макулатур|картон|бумаг|архив"),
    ("Пластик", r"пластик|пластмасс|полимер|\bпэт\b|\bпнд\b|\bпвд\b|\bпп\b|полипроп|полиэтил|\bпвх\b|\bабс\b|"
                r"стре[йт]ч|пл[её]нк|полистир|полиамид|бэг|спанбонд|дробл[её]нк|гранул"),
]

_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}

# Неразрывный пробел и невидимые символы -> пробел; все виды тире -> короткий дефис.
_INVISIBLE = re.compile("[" + chr(0xA0) + chr(0x200B) + chr(0x2009) + chr(0x202F) + "]")
_DASHES = re.compile("[" + chr(0x2012) + "-" + chr(0x2015) + chr(0x2212) + "]")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+7|8)[\s(\-]*\d{3}[\s)\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def clean_text(value: str | None) -> str:
    """Убирает HTML-теги и сущности, лишние пробелы и невидимые символы."""
    if not value:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = _INVISIBLE.sub(" ", text)
    text = _DASHES.sub("-", text)
    return re.sub(r"\s+", " ", text).strip()


def scrub_pii(text: str) -> str:
    """Вырезает телефоны и e-mail из произвольного текста."""
    text = _PHONE_RE.sub("", text)
    text = _EMAIL_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" ,;:")


def truncate(text: str, limit: int = config.SUMMARY_MAX) -> str:
    """Обрезает по границе слова так, чтобы вместе с многоточием было не больше limit символов."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut[limit // 2:]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,.;:-") + "…"


def parse_date(value, now: datetime | None = None) -> str | None:
    """Любая дата из источника -> ISO 8601. С временем: «2026-10-16T17:13:16+03:00», без времени: «2026-10-16».

    Время приводится к московскому. Дата без года («15 октября») берётся в текущем году,
    а если она получилась в будущем, то в прошлом.
    """
    if value is None or value == "":
        return None
    now = now or datetime.now(MSK)
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=MSK)
        return dt.astimezone(MSK).isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    text = clean_text(value).lower()

    try:  # RFC 822 из RSS: «Fri, 16 Oct 2026 14:13:16 GMT»
        return parse_date(parsedate_to_datetime(text.title()), now)
    except (TypeError, ValueError, IndexError):
        pass
    try:  # ISO 8601
        dt = datetime.fromisoformat(text.upper().replace("Z", "+00:00"))
        return parse_date(dt, now) if ("t" in text or ":" in text) else dt.date().isoformat()
    except ValueError:
        pass

    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if m.group(4):
            return parse_date(datetime(y, mo, d, int(m.group(4)), int(m.group(5)), tzinfo=MSK), now)
        return date(y, mo, d).isoformat()

    m = re.search(r"(\d{1,2})\s+([а-я]+)(?:\s+(\d{4}))?", text)
    if m:
        month = next((n for stem, n in _MONTHS.items() if m.group(2).startswith(stem)), None)
        if month:
            day = int(m.group(1))
            if m.group(3):
                return date(int(m.group(3)), month, day).isoformat()
            guess = date(now.year, month, day)
            if guess > now.date():
                guess = date(now.year - 1, month, day)
            return guess.isoformat()
    return None


def _classify(text: str, rules: list[tuple[str, str]], default: str) -> str:
    t = text.lower().replace("ё", "е")
    for category, pattern in rules:
        if re.search(pattern, t):
            return category
    return default


def news_category(*texts: str) -> str:
    return _classify(" ".join(texts), _NEWS_RULES, "Экология")


def waste_category(*texts: str) -> str:
    return _classify(" ".join(texts), _WASTE_RULES, "Прочее")


def offer_type(text: str, hint: str | None = None) -> str | None:
    """Тип предложения: подсказка источника («Продаю», «Покупаю») важнее текста."""
    hint_l = (hint or "").lower()
    if hint_l.startswith(("прода", "продам")):
        return "продам"
    if hint_l.startswith(("покупа", "куплю")):
        return "куплю"
    t = text.lower().replace("ё", "е")
    if re.search(r"утилиз|обезвреж|переработк|размещени\w* отход", t):
        return "утилизация"
    if re.search(r"вывоз|транспортир|сбор\w* и транспорт", t):
        return "вывоз"
    if re.search(r"\b(куплю|купим|покупаем|покупаю|закупаем|закупаю|приму|примем)\b", t):
        return "куплю"
    if re.search(r"\b(продам|продаю|продаем|продается|отдам|отдадим|реализуем)\b", t):
        return "продам"
    return None


_CURRENCIES = [
    (r"руб|₽|rub|российский рубль", "RUB"),
    (r"\$|usd|доллар", "USD"),
    (r"€|eur|евро", "EUR"),
]


def parse_price(text: str | None) -> tuple[float | None, str | None]:
    """«5 500,00 руб.» -> (5500.0, "RUB"). Ноль и «договорная» -> (None, None)."""
    if not text:
        return None, None
    t = clean_text(text).lower()
    m = re.search(r"(\d[\d\s]*(?:[.,]\d+)?)\s*(млн|тыс)?", t)
    if not m:
        return None, None
    amount = float(re.sub(r"\s", "", m.group(1)).replace(",", "."))
    if m.group(2) == "млн":
        amount *= 1_000_000
    elif m.group(2) == "тыс":
        amount *= 1_000
    if amount <= 0:
        return None, None
    currency = next((code for pattern, code in _CURRENCIES if re.search(pattern, t)), "RUB")
    return round(amount, 2), currency


def parse_volume(text: str | None) -> tuple[float | None, str | None]:
    """Объём к единицам «т», «м3», «шт»: «20000 кг» -> (20.0, "т")."""
    if not text:
        return None, None
    t = clean_text(text).lower().replace("ё", "е")
    m = re.search(r"(\d[\d\s]*(?:[.,]\d+)?)\s*(тонн\w*|т\b|кг|килограм\w*|м3|м³|куб\w*|шт)", t)
    if not m:
        return None, None
    value = float(re.sub(r"\s", "", m.group(1)).replace(",", "."))
    unit = m.group(2)
    if unit.startswith(("кг", "килограм")):
        return round(value / 1000, 3), "т"
    if unit.startswith(("т",)):
        return value, "т"
    if unit.startswith(("м", "куб")):
        return value, "м3"
    return value, "шт"


_FKKO_SPACED = re.compile(r"(?<!\d)\d\s\d{2}\s\d{3}\s\d{2}\s\d{2}\s\d(?!\d)")


def normalize_fkko(text: str | None) -> str | None:
    """Код ФККО -> 11 цифр без пробелов.

    Берём либо код в каноническом виде «4 34 110 02 29 5», либо любые 11 цифр сразу после слова «ФККО»,
    чтобы не принять за код номер телефона.
    """
    if not text:
        return None
    t = clean_text(text)
    m = _FKKO_SPACED.search(t)
    if m:
        return re.sub(r"\D", "", m.group(0))
    m = re.search(r"фкко\W{0,5}((?:\d[\s-]?){11})(?!\d)", t, flags=re.I)
    if m:
        return re.sub(r"\D", "", m.group(1))
    return None


def hazard_from_fkko(fkko: str | None) -> int | None:
    """Последняя цифра кода ФККО это класс опасности (0 - класс не установлен)."""
    if fkko and len(fkko) == 11 and fkko[-1] in "12345":
        return int(fkko[-1])
    return None


_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}
_CLASS_TOKEN = r"(?:iv|v|i{1,3}|[1-5])"


def parse_hazard_classes(text: str | None) -> list[int]:
    """«отходов I-IV класса опасности» -> [1, 2, 3, 4]; «4 и 5 классов» -> [4, 5]."""
    if not text:
        return []
    t = clean_text(text).lower()
    found: set[int] = set()
    pattern = rf"(?<![a-zа-я0-9])((?:{_CLASS_TOKEN}\s*(?:-|,|и|по)\s*)*{_CLASS_TOKEN})\s*класс"
    for m in re.finditer(pattern, t):
        group = m.group(1)
        tokens = re.findall(_CLASS_TOKEN, group)
        nums = [_ROMAN.get(tok, None) or int(tok) for tok in tokens]
        if re.search(r"-|по", group) and len(nums) == 2:
            found.update(range(min(nums), max(nums) + 1))
        else:
            found.update(nums)
    return sorted(n for n in found if 1 <= n <= 5)


_LEGAL_FORM = (
    r"ООО|АО|ПАО|ЗАО|ОАО|НАО|ГУП|МУП|ФГУП|ГБУ|МБУ|ФГБУ|ГКУ|МКУ|ГАУ|МАУ|АНО|НПП|ПК|ППК"
)
_ORG_WORDS = re.compile(
    r"комитет|министерств|администрац|управлени|департамент|учреждени|предприяти|общество|"
    r"агентств|служб|инспекц|фонд|государствен|муниципальн|федеральн|компани|корпорац|"
    r"оператор|школ|больниц|университет|институт|колледж|центр",
    flags=re.I,
)


def organization(name: str | None) -> str | None:
    """Название организации, только если это юрлицо. ИП и всё похожее на ФИО отбрасывается."""
    text = clean_text(name)
    if not text or re.match(r"(ИП|индивидуальный предприниматель)\b", text, flags=re.I):
        return None
    if re.search(rf"(?<![\w])({_LEGAL_FORM})(?![\w])", text) or _ORG_WORDS.search(text):
        return text
    return None


def organization_in_text(text: str | None) -> str | None:
    """Ищет в тексте «ООО «Ромашка»» или «ООО ТЕХНОПРОГРЕСС» и возвращает его."""
    if not text:
        return None
    m = re.search(
        rf"(?<![\w])({_LEGAL_FORM})\s+(«[^»]{{2,80}}»|\"[^\"]{{2,80}}\"|[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9-]+(?:\s+[A-ZА-ЯЁ0-9-]{{2,}})*)",
        clean_text(text),
    )
    return f"{m.group(1)} {m.group(2)}" if m else None
