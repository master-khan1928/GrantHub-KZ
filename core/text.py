"""Подготовка текстов грантов к показу людям."""
import re
from typing import Optional
from urllib.parse import urlparse

# Слова поисковых запросов сканера: «scholarships for kazakhstan students deadline 2026»
_QUERY_HINTS = re.compile(
    r"\b(deadline|scholarships?|grants?|apply|application|students?|for|in|20\d\d|"
    r"стипенди\w*|грант\w*|для|студент\w*|подач\w*)\b", re.I)
# Признаки названия организации — такие строки оставляем как есть
_ORG_HINTS = re.compile(
    r"(universit|университет|institute|институт|college|колледж|academy|академи|school|школ|foundation|фонд|"
    r"ministry|министерств|government|council|agency|programme|program|программ|fund|центр|center|centre)", re.I)


def domain_of(link: Optional[str]) -> Optional[str]:
    host = urlparse(link or "").netloc.lower()
    return host[4:] if host.startswith("www.") else (host or None)


def looks_like_query(source: str) -> bool:
    s = source.strip()
    words = s.split()
    if len(s) > 80:
        return True
    if s == s.lower() and len(words) >= 3:          # запросы сканер пишет строчными
        return True
    return len(_QUERY_HINTS.findall(s)) >= 3 and not _ORG_HINTS.search(s)


def clean_source(source: Optional[str], link: Optional[str] = None) -> Optional[str]:
    """Источник для показа: название организации или, если это поисковый запрос, домен ссылки."""
    s = (source or "").strip()
    if not s:
        return None
    if looks_like_query(s):
        return domain_of(link)
    return s
