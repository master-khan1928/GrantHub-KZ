"""
Подбор грантов под профиль пользователя (IELTS, GPA, направление). Эвристика без ИИ,
общая для сайта («Мне подходит», главная) и бота (/match).

score_grant(g, profile) -> (баллы, причины, пробелы)
  причины: field | ielts_ok | gpa_ok | open
  пробелы: {"ielts": сколько не хватает, "gpa": сколько не хватает}
match_grants(grants, profile) -> {"matches": [...], "near": [...]}
  matches — подходят по всем известным требованиям, near — не хватает одного показателя.
"""
from __future__ import annotations

import datetime
import re

_IELTS_RE = re.compile(r"ielts[^0-9]{0,12}(\d(?:[.,]\d)?)", re.I)
_GPA_RE = re.compile(r"gpa[^0-9]{0,12}(\d(?:[.,]\d{1,2})?)", re.I)
_STOP = {"and", "или", "the", "для", "and"}

PROFILE_KEYS = ("ielts", "gpa", "field_of_interest")


def has_profile(profile: dict) -> bool:
    return any(profile.get(k) for k in PROFILE_KEYS)


def days_left(deadline_date) -> int | None:
    if not deadline_date:
        return None
    try:
        return (datetime.date.fromisoformat(deadline_date) - datetime.date.today()).days
    except (ValueError, TypeError):
        return None


def required_ielts(requirements: str) -> float | None:
    m = _IELTS_RE.search(requirements or "")
    return float(m.group(1).replace(",", ".")) if m else None


def required_gpa(requirements: str) -> float | None:
    m = _GPA_RE.search(requirements or "")
    return float(m.group(1).replace(",", ".")) if m else None


def score_grant(g: dict, profile: dict) -> tuple:
    """-> (баллы, причины, пробелы). Отрицательный вклад — требование выше показателя пользователя."""
    score, why, gaps = 0.0, [], {}
    text = f"{g.get('name', '')} {g.get('coverage', '')} {g.get('requirements', '')}".lower()
    field = (profile.get("field_of_interest") or "").strip().lower()
    if field:
        words = [w for w in re.findall(r"[a-zа-яёәіңғүұқөһ]{2,}", field) if w not in _STOP]
        if any(w in text for w in words):
            score += 3
            why.append("field")
    ielts, need = profile.get("ielts"), required_ielts(g.get("requirements"))
    if ielts and need:
        if ielts >= need:
            score += 2
            why.append("ielts_ok")
        else:
            score -= 3
            gaps["ielts"] = round(need - ielts, 1)
    gpa, need = profile.get("gpa"), required_gpa(g.get("requirements"))
    if gpa and need:
        if gpa >= need:
            score += 1.5
            why.append("gpa_ok")
        else:
            score -= 2
            gaps["gpa"] = round(need - gpa, 2)
    if g.get("status") == "open":
        score += 1
        why.append("open")
    dl = days_left(g.get("deadline_date"))
    if dl is not None and 0 <= dl <= 30:
        score += 0.5
    return score, why, gaps


def match_grants(grants: list, profile: dict) -> dict:
    """Делит активные гранты на подходящие и «почти подходящие» (не хватает одного показателя).

    Каждый элемент — dict(grant=..., score=..., why=[...], gaps={...}). Списки отсортированы:
    сначала выше балл, затем ближе дедлайн.
    """
    matches, near = [], []
    for g in grants:
        sc, why, gaps = score_grant(g, profile)
        item = {"grant": g, "score": sc, "why": why, "gaps": gaps}
        if not gaps:
            matches.append(item)
        elif len(gaps) == 1:
            near.append(item)
    key = lambda x: (-x["score"], x["grant"].get("deadline_date") or "9999")  # noqa: E731
    matches.sort(key=key)
    near.sort(key=key)
    return {"matches": matches, "near": near}
