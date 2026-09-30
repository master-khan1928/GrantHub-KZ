"""Подтверждение даты дедлайна по тексту страницы гранта.

Модель оценивает дедлайн по сниппету, а удаление по нему необратимо. Поэтому дата считается
подтверждённой, только если она в каком-то из привычных написаний встречается на самой странице.
"""
import datetime
import re

_MONTHS = {
    1: ("january", "jan", "января", "январь", "қаңтар"), 2: ("february", "feb", "февраля", "февраль", "ақпан"),
    3: ("march", "mar", "марта", "март", "наурыз"), 4: ("april", "apr", "апреля", "апрель", "сәуір"),
    5: ("may", "мая", "май", "мамыр"), 6: ("june", "jun", "июня", "июнь", "маусым"),
    7: ("july", "jul", "июля", "июль", "шілде"), 8: ("august", "aug", "августа", "август", "тамыз"),
    9: ("september", "sep", "sept", "сентября", "сентябрь", "қыркүйек"),
    10: ("october", "oct", "октября", "октябрь", "қазан"), 11: ("november", "nov", "ноября", "ноябрь", "қараша"),
    12: ("december", "dec", "декабря", "декабрь", "желтоқсан"),
}
_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)
_WS_RE = re.compile(r"[\s ]+")


def page_text(html: str, limit: int = 300_000) -> str:
    """HTML -> текст в нижнем регистре без тегов и скриптов."""
    text = _TAG_RE.sub(" ", html[:limit])
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return _WS_RE.sub(" ", text).lower()


def date_patterns(iso_date: str) -> list:
    """Регулярные выражения для всех написаний даты: 2027-01-15, 15.01.2027, 15 January 2027, January 15, 2027, 15 января 2027."""
    d = datetime.date.fromisoformat(iso_date)
    day, month, year = d.day, d.month, d.year
    dd, mm = f"{day:02d}", f"{month:02d}"
    day_alt = rf"(?:{dd}|{day})"
    names = "|".join(re.escape(n) for n in _MONTHS[month])
    return [
        rf"\b{year}-{mm}-{dd}\b",
        rf"\b{day_alt}[./-]{mm}[./-]{year}\b",
        rf"\b{mm}[./-]{day_alt}[./-]{year}\b",
        rf"\b{day_alt}(?:st|nd|rd|th)?\.?\s+(?:{names})\.?,?\s+{year}\b",
        rf"\b(?:{names})\.?\s+{day_alt}(?:st|nd|rd|th)?,?\s+{year}\b",
    ]


def date_in_text(iso_date, text: str) -> bool:
    """Есть ли дата (в любом написании) в тексте страницы."""
    if not iso_date or not text:
        return False
    try:
        patterns = date_patterns(iso_date)
    except ValueError:
        return False
    return any(re.search(p, text) for p in patterns)
