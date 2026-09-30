"""Поиск по каталогу: понимает словоформы, направления, страны, уровни и опечатки.

Запрос разбирается на слова. Каждое слово — это либо признак (страна, уровень, финансирование,
раздел), либо тема (IT, медицина, право...), либо просто текст. Страна и раздел ищутся только по
полям базы, а не по тексту описания. Оценка — сколько слов запроса подтвердилось в записи.
"""
import difflib
import re

from core.geo import COUNTRY_BY_NAME

_WORD_RE = re.compile(r"[a-zа-яёіїқғңөұүһәЁ0-9.+#]+", re.I)
STOPWORDS = {"в", "на", "для", "по", "и", "с", "из", "к", "о", "об", "от", "до", "за", "не", "или", "the", "for", "in",
             "of", "to", "a", "an", "and", "or", "at", "by", "with", "мне", "хочу", "нужен", "нужна", "ищу", "найти",
             "какие", "есть", "где", "что", "как"}
# Слова, которые есть почти в каждой записи — сами по себе ничего не сужают
GENERIC = {"грант", "гранты", "грантов", "стипенд", "scholarship", "scholarships", "программ", "program", "programme",
           "учеб", "обучен", "study", "студент", "student", "students", "универ", "university", "вуз", "вузы", "fund"}

# Темы: любое слово группы находит записи с любым другим словом группы. Короткие слова ищутся целиком.
TOPICS = [
    {"it", "айти", "информатик", "информационн", "компьютер", "computer", "программирован", "software", "технолог",
     "technolog", "data", "ai", "ии", "кибер", "cyber", "digital", "цифров"},
    {"медиц", "medic", "health", "здравоохран", "врач", "nursing", "pharma", "фармац", "стоматолог", "dental", "биомед"},
    {"бизнес", "business", "менеджмент", "management", "mba", "экономик", "econom", "финанс", "financ", "маркетинг",
     "marketing", "предпринимат", "entrepreneur", "accounting", "бухгалтер"},
    {"право", "прав", "юрид", "юрист", "law", "legal", "юриспруденц"},
    {"инженер", "engineer", "технич", "technical", "политех", "polytech", "mechanic", "механик", "электро", "electric",
     "нефт", "petroleum", "энергет", "energy", "строит", "civil"},
    {"педагог", "учител", "teacher", "teaching", "education science"},
    {"искусств", "art", "arts", "дизайн", "design", "творч", "creative", "архитект", "architect", "музык", "music",
     "кино", "film", "театр", "theatre"},
    {"наук", "science", "sciences", "research", "исследован", "scientific", "лаборатор"},
    {"гуманитар", "humanit", "социальн", "social", "психолог", "psycholog", "социолог", "sociolog", "истори",
     "history", "философ", "philosoph", "политолог", "political", "международн отношен", "international relations"},
    {"язык", "language", "лингвист", "linguist", "english", "английск", "перевод", "translat", "филолог", "philolog"},
    {"математ", "math", "физик", "physic", "хими", "chemist", "биолог", "biolog", "естествен", "natural"},
    {"аграр", "agricult", "сельск", "ветеринар", "veterinar", "экологи", "ecolog", "environment", "окружающ"},
    {"журналист", "journalis", "media", "медиа", "коммуникац", "communication", "pr"},
    {"спорт", "sport", "физкультур", "physical education"},
    {"туризм", "tourism", "гостинич", "hospitality", "hotel"},
    {"евросоюз", "европ", "europe", "european", "eu", "ес", "erasmus", "эразмус"},
]
DEGREE_WORDS = {
    "bachelor": {"бакалавр", "bachelor", "undergraduate", "бакалавриат", "первое высшее", "после школы", "школьник",
                 "абитуриент", "11 класс", "выпускник"},
    "master": {"магистр", "master", "masters", "магистратур", "mba", "graduate", "второе высшее"},
    "phd": {"phd", "докторант", "докторантур", "аспирант", "doctoral", "doctorate", "postdoc", "postgraduate"},
    "language": {"языков", "language course", "курсы", "courses", "летн", "summer", "short"},
}
FUNDING_WORDS = {"full": {"полн", "full", "fully", "бесплатн", "free", "100"}, "partial": {"частич", "partial", "скидк", "discount"}}
STATUS_WORDS = {"open": {"открыт", "open", "сейчас", "now"}, "upcoming": {"скоро", "upcoming", "будущ", "soon"}}
SCOPE_WORDS = {"abroad": {"зарубеж", "рубеж", "abroad", "заграниц", "международн", "international", "мир", "world"},
               "kz": {"казахстан", "kazakhstan", "қазақстан", "рк", "отечествен", "местн", "domestic"}}
REQ_WORDS = {"ent": {"ент", "unt", "ұбт"}, "ielts": {"ielts", "айлтс"}, "toefl": {"toefl", "тофл"}, "sat": {"sat"}, "gpa": {"gpa"}}


def stem(word: str) -> str:
    """Грубая основа слова: «медицинские» -> «медици», «германии» -> «герман». Короткие слова не трогаем."""
    word = word.lower().replace("ё", "е")
    if len(word) >= 6:
        return word[: len(word) - 2]
    return word


def tokenize(query: str) -> list:
    return [w.lower().replace("ё", "е") for w in _WORD_RE.findall(query) if len(w) >= 2 and w.lower() not in STOPWORDS]


def _country_stems() -> dict:
    return {stem(name): cc for name, cc in COUNTRY_BY_NAME.items()}


_COUNTRY_STEMS = _country_stems()


def _find(words: set, token: str) -> bool:
    """Слово запроса соответствует набору словарных основ (с учётом словоформ)."""
    st = stem(token)
    for w in words:
        w = w.replace("ё", "е")
        if len(w) <= 3 or len(st) <= 3:
            if token == w or st == w:
                return True
        elif w.startswith(st) or st.startswith(w) or (w.startswith(token[:5]) and len(token) >= 5 and len(w) >= 5):
            return True
    return False


def _match_dict(mapping: dict, token: str):
    for key, words in mapping.items():
        if _find(words, token):
            return key
    return None


def _country_for(token: str):
    if token in COUNTRY_BY_NAME:
        return COUNTRY_BY_NAME[token]
    st = stem(token)
    if len(st) < 4:
        return None
    for name_stem, cc in _COUNTRY_STEMS.items():
        if len(name_stem) >= 4 and (name_stem.startswith(st) or st.startswith(name_stem)):
            return cc
    return None


def _is_generic(token: str) -> bool:
    return any(token.startswith(g) or g.startswith(token) for g in GENERIC)


def interpret(token: str, synonyms: dict = None, country_as_text: bool = False) -> dict:
    """Что означает слово запроса: признаки базы и/или текстовые основы для поиска.

    synonyms — {слово: [полные названия]} из словаря админки: «nu» находит и «Nazarbayev University».
    country_as_text — запасной режим: страну искать и по тексту (когда по полю ничего не нашлось).
    """
    meaning = {"token": token, "stems": set(), "phrases": [], "generic": _is_generic(token)}
    cc = _country_for(token)
    if cc and not country_as_text:
        meaning["country"] = cc
        return meaning   # страна — только по полю базы, не по тексту
    for phrase in (synonyms or {}).get(token, []):   # полное название ищется целиком, всеми словами сразу
        words = [stem(w) for w in tokenize(phrase) if not _is_generic(w)]
        if words:
            meaning["phrases"].append(words)
    scope = _match_dict(SCOPE_WORDS, token)
    if scope:
        meaning["scope"] = scope
        return meaning
    degree = _match_dict(DEGREE_WORDS, token)
    if degree:
        meaning["degree"] = degree
    funding = _match_dict(FUNDING_WORDS, token)
    if funding:
        meaning["funding"] = funding
    status = _match_dict(STATUS_WORDS, token)
    if status:
        meaning["status"] = status
    req = _match_dict(REQ_WORDS, token)
    if req:
        meaning["req"] = req
    for group in TOPICS:
        if _find(group, token):
            meaning["stems"] |= {w.replace("ё", "е") for w in group}
    meaning["stems"].add(stem(token))
    return meaning


def _text_hit(hay: str, term: str) -> bool:
    if len(term) <= 3:
        return re.search(rf"(?<![a-zа-я0-9]){re.escape(term)}(?![a-zа-я0-9])", hay) is not None
    return term in hay


def score_row(row: dict, meanings: list, strict: bool = True):
    """-> (баллы, сколько слов подтвердилось). strict — все неслужебные слова должны совпасть."""
    name = (row.get("name") or "").lower().replace("ё", "е")
    hay = " ".join(str(row.get(k) or "") for k in ("name", "coverage", "requirements", "source", "deadline")).lower().replace("ё", "е")
    score, matched, required = 0.0, 0, 0
    for m in meanings:
        hit = 0.0
        if "country" in m:
            hit = 3 if (row.get("country_code") == m["country"] or (m["country"] == "KZ" and row.get("is_domestic"))) else 0
        elif "scope" in m:
            domestic = bool(row.get("is_domestic"))
            hit = 2 if (m["scope"] == "kz") == domestic else 0
        else:
            if m.get("degree") and row.get("degree") in (m["degree"], "all"):
                hit = max(hit, 2 if row.get("degree") == m["degree"] else 1)
            if m.get("funding") and row.get("funding") == m["funding"]:
                hit = max(hit, 2)
            if m.get("status") and row.get("status") == m["status"]:
                hit = max(hit, 2)
            if m.get("req") and any(_text_hit(hay, w) for w in REQ_WORDS[m["req"]]):
                hit = max(hit, 2)
            if any(_text_hit(name, s) for s in m["stems"]) or any(all(_text_hit(name, w) for w in ph) for ph in m["phrases"]):
                hit = max(hit, 2.5)
            elif any(_text_hit(hay, s) for s in m["stems"]) or any(all(_text_hit(hay, w) for w in ph) for ph in m["phrases"]):
                hit = max(hit, 1)
        if hit:
            matched += 1
            score += hit
        if not m["generic"]:
            required += 1
            if strict and not hit:
                return 0.0, 0
    if row.get("status") == "open":
        score += 0.3
    return score, matched


def rank(rows: list, query: str, limit: int, synonyms: dict = None) -> list:
    """Лучшие записи по запросу: строго (все слова), с поправкой опечаток, страна по тексту, затем любое слово."""
    tokens = tokenize(query)
    if not tokens:
        return []
    meanings = [interpret(t, synonyms) for t in tokens]

    def _run(ms, strict):
        scored = []
        for row in rows:
            sc, matched = score_row(row, ms, strict)
            if matched:
                scored.append((sc, row))
        scored.sort(key=lambda x: (-x[0], -x[1]["id"]))
        return [r for _, r in scored[:limit]]

    result = _run(meanings, True)
    if result:
        return result
    # опечатки: подбираем похожие слова из самих записей («германя» -> «германия», «стипндия» -> «стипендия»)
    vocab = set()
    for row in rows:
        vocab |= set(_WORD_RE.findall(" ".join(str(row.get(k) or "") for k in ("name", "coverage", "requirements", "source")).lower()))
    vocab |= set(COUNTRY_BY_NAME)
    fixed = []
    for m in meanings:
        if len(m["token"]) >= 5 and not any(k in m for k in ("country", "scope")):
            close = difflib.get_close_matches(m["token"], vocab, n=1, cutoff=0.78)
            if close and close[0] != m["token"]:
                fixed.append(interpret(close[0], synonyms))
                continue
        fixed.append(m)
    result = _run(fixed, True)
    if result:
        return result
    # по полю страны пусто — ищем её упоминание в тексте («Германия» -> программы двойного диплома с Германией)
    if any("country" in m for m in fixed):
        as_text = [interpret(m["token"], synonyms, country_as_text=True) if "country" in m else m for m in fixed]
        result = _run(as_text, True) or _run(as_text, False)
        if result:
            return result
    return _run(fixed, False)
