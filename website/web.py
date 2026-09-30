"""
Веб-версия бота: те же функции (каталог, поиск, избранное, профиль, ИИ-консультант,
напоминания о дедлайнах, админ-панель со сканером и мониторингом), та же база grants.db
и та же локальная Ollama.

Запуск:  python run_web.py        (или: uvicorn website.web:app --reload)
Адрес:   http://localhost:8000
"""
import asyncio
import datetime
import logging
import os
import random
import secrets
import time
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from core import ai_scanner  # noqa: E402
from core.ai_scanner import (  # noqa: E402
    GEMINI_MODEL, LLM_FALLBACK, LLM_PROVIDER, OLLAMA_CHAT_MODEL, OLLAMA_MODEL, PROGRAMS, UNIVERSITIES,
    ask_gemini_consultant, ask_consultant_stream, ollama_status, scan_and_save_grants, warm_up_llm,
)
from core.database import (  # noqa: E402
    DB_NAME, DEGREES, LOGS_DIR, REQUIREMENTS, add_favorite, add_open_alert, add_synonym, add_user,
    cleanup_expired_grants, get_open_alert_ids, get_opened_alerts, remove_open_alert,
    delete_synonym, get_active_countries, get_active_users_count, get_all_users, get_data_version,
    get_events_summary, get_favorites_with_deadlines, get_grant_by_id, get_grants_page, get_monitor_summary,
    get_review_queue, get_scan_runs, get_synonyms, get_user_favorites,
    get_user_profile, init_db, is_favorite, log_event, remove_favorite, review_grant,
    get_recent_grants, get_all_active_grants,
    save_ai_answer, search_grants, set_answer_rating, set_grant_active, set_user_profile,
)
from core.geo import normalize_country  # noqa: E402

import aiosqlite  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("PORT") or os.getenv("WEB_PORT", "8000"))
WEB_ADMIN_TOKEN = os.getenv("WEB_ADMIN_TOKEN", "").strip()
WEB_RUN_SCHEDULER = os.getenv("WEB_RUN_SCHEDULER", "0").strip() == "1"
TIMEZONE = os.getenv("TIMEZONE", "Asia/Almaty")
SCAN_HOURS_RAW = os.getenv("SCAN_HOURS", "8,20").strip()
SCAN_HOURS = sorted({int(h) for h in SCAN_HOURS_RAW.split(",") if h.strip().isdigit() and 0 <= int(h) <= 23}) or [8]
QUESTION_COOLDOWN_SECONDS = 3
UID_COOKIE = "gh_uid"
UID_MAX_AGE = 3600 * 24 * 365

from website.auth import (  # noqa: E402
    RateLimit, account_from_request, client_ip, read_uid_cookie, router as auth_router, set_uid_cookie,
)

SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
if SENTRY_DSN:  # отслеживание ошибок включается только если задан DSN и установлен пакет sentry-sdk
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.0)
    except ImportError:
        logging.warning("SENTRY_DSN задан, но пакет sentry-sdk не установлен (pip install sentry-sdk).")

app = FastAPI(title="GrantHub", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(auth_router)

# CORS: по умолчанию чужим сайтам доступ к API закрыт (фронтенд живёт на том же домене).
# Отдельный фронтенд-домен добавляется явно: CORS_ORIGINS=https://granthub.kz,https://www.granthub.kz
CORS_ORIGINS = [o.strip().rstrip("/") for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
                       allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type", "X-Admin-Token"])

ask_limit_min = RateLimit(8, 60)        # вопросов к ИИ с одного IP в минуту
ask_limit_day = RateLimit(150, 86400)   # ... и в сутки — защита квоты Groq от ботов
API_RATE_LIMIT = int(os.getenv("API_RATE_LIMIT", "100"))
api_limit = RateLimit(API_RATE_LIMIT, 60)   # все запросы к API с одного IP в минуту — от выкачивания каталога
STATIC_MAX_AGE = int(os.getenv("STATIC_MAX_AGE", "3600"))


# ---------------------------------------------------------------------------
# Кэш в памяти процесса: справочники и популярные страницы каталога.
# Сбрасывается сам, когда сканер (на сайте или в боте) завершил запуск.
# ---------------------------------------------------------------------------
_cache: dict = {}
_cache_version = {"value": None, "checked": 0.0}
CACHE_TTL_REFERENCE = 24 * 3600   # список стран и фильтров
CACHE_TTL_PAGES = 3600            # страницы каталога, счётчики, лента


async def cached(key: tuple, ttl: int, producer):
    now = time.time()
    if now - _cache_version["checked"] > 30:
        _cache_version["checked"] = now
        version = await get_data_version()
        if version != _cache_version["value"]:
            _cache_version["value"] = version
            _cache.clear()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = await producer()
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (now + ttl, value)
    return value


def cache_invalidate():
    _cache.clear()
    _cache_version["checked"] = 0.0


@app.middleware("http")
async def security_headers(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and request.method != "OPTIONS" and not api_limit.hit(client_ip(request)):
        return JSONResponse({"detail": "Слишком много запросов. Подождите минуту."}, status_code=429,
                            headers={"Retry-After": "60"})
    response = await call_next(request)
    if path.startswith("/static/") and response.status_code == 200:
        response.headers["Cache-Control"] = f"public, max-age={STATIC_MAX_AGE}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.headers.get("x-forwarded-proto", request.url.scheme) == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _check_ask_limits(request: Request, uid: int):
    ip = client_ip(request)
    now = time.time()
    if now - _last_question_time.get(uid, 0) < QUESTION_COOLDOWN_SECONDS:
        raise HTTPException(429, "Не так быстро — подожди пару секунд перед следующим вопросом.")
    if not ask_limit_min.hit(ip) or not ask_limit_day.hit(ip):
        raise HTTPException(429, "Слишком много вопросов. Сделай паузу и попробуй позже.")
    _last_question_time[uid] = now

_last_question_time: dict = {}
_scan_state: dict = {"running": False, "started_at": None, "finished_at": None, "result": None, "error": None}
_scan_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Пользователь сайта: анонимный числовой id в cookie (не пересекается с Telegram id)
# ---------------------------------------------------------------------------
async def current_user(request: Request, response: Response) -> int:
    # Вошедший пользователь: uid из подписанной сессии
    account = await account_from_request(request)
    if account:
        return account["uid"]
    uid = read_uid_cookie(request.cookies.get(UID_COOKIE, ""))
    if uid:
        return uid
    uid = random.randint(10**12, 10**13 - 1)
    await add_user(uid)
    set_uid_cookie(response, uid, UID_MAX_AGE)
    return uid


admin_fail_limit = RateLimit(10, 60)    # неверных токенов администратора с одного IP в минуту — от перебора


def require_admin(request: Request, x_admin_token: str = Header(default="")):
    if not WEB_ADMIN_TOKEN:
        raise HTTPException(503, "Админ-панель выключена: задайте WEB_ADMIN_TOKEN в .env")
    ip = client_ip(request)
    if admin_fail_limit.blocked(ip):
        raise HTTPException(429, "Слишком много попыток. Подождите минуту.")
    if not secrets.compare_digest(x_admin_token.encode(), WEB_ADMIN_TOKEN.encode()):
        admin_fail_limit.hit(ip)
        raise HTTPException(401, "Неверный токен администратора")
    return True


def _grant_public(g: dict, fav: bool = False) -> dict:
    country = g.get("country_code")
    return {
        "id": g["id"], "name": g["name"], "category": "kz" if country == "KZ" else "abroad", "degree": g["degree"],
        "country_code": country, "provider_country": g.get("provider_country"), "funding": g.get("funding") or "unknown",
        "coverage": g["coverage"], "requirements": g["requirements"], "deadline": g["deadline"],
        "deadline_date": g.get("deadline_date"), "link": g["link"], "source": g.get("source"),
        "status": g.get("status") or "unknown", "is_favorite": fav,
        "application_start_date": g.get("application_start_date"), "is_ongoing": bool(g.get("is_ongoing")),
        "recurrence_period": g.get("recurrence_period"),
        "days_left": _days_left(g.get("deadline_date")),
    }


def _days_left(deadline_date: Optional[str]) -> Optional[int]:
    if not deadline_date:
        return None
    try:
        return (datetime.date.fromisoformat(deadline_date) - datetime.date.today()).days
    except ValueError:
        return None


async def _favorite_ids(uid: int) -> set:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT grant_id FROM favorites WHERE user_id = ?", (uid,)) as cur:
            return {r[0] for r in await cur.fetchall()}


# ---------------------------------------------------------------------------
# Страницы
# ---------------------------------------------------------------------------
@app.get("/")
async def landing():
    """Лендинг (hero-экран). Приложение живёт на /app."""
    return FileResponse(STATIC_DIR / "landing" / "index.html")


@app.get("/app")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


# ---------------------------------------------------------------------------
# Пользователь, профиль, напоминания
# ---------------------------------------------------------------------------
class ProfileIn(BaseModel):
    ielts: Optional[float] = Field(default=None, ge=0, le=9)
    gpa: Optional[float] = Field(default=None, ge=0, le=5)
    field_of_interest: Optional[str] = Field(default=None, max_length=120)


@app.get("/api/me")
async def api_me(request: Request, uid: int = Depends(current_user)):
    profile = await get_user_profile(uid)
    favs = await _favorite_ids(uid)
    account = await account_from_request(request)
    return {
        "user_id": uid,
        "account": {"id": account["id"], "email": account.get("email"), "name": account.get("name") or (account.get("email") or "").split("@")[0],
                    "avatar": account.get("avatar"), "provider": account["provider"]} if account else None,
        "profile": {k: profile.get(k) for k in ("ielts", "gpa", "field_of_interest")},
        "favorites_count": len(favs),
        "alerts": sorted(await get_open_alert_ids(uid)),
        "reminders": await _reminders_for(uid),
        "admin_enabled": bool(WEB_ADMIN_TOKEN),
    }


@app.post("/api/profile")
async def api_profile_save(data: ProfileIn, uid: int = Depends(current_user)):
    field = (data.field_of_interest or "").strip() or None
    await set_user_profile(uid, ielts=data.ielts, gpa=data.gpa, field_of_interest=field)
    await log_event(uid, "profile_saved")
    profile = await get_user_profile(uid)
    return {"profile": {k: profile.get(k) for k in ("ielts", "gpa", "field_of_interest")}}


async def _reminders_for(uid: int) -> list:
    """Избранные гранты с дедлайном в ближайшие 7 дней — аналог напоминаний бота."""
    rows = await get_favorites_with_deadlines()
    out = []
    for r in rows:
        if r["user_id"] != uid:
            continue
        days = _days_left(r["deadline_date"])
        if days is None or days < 0 or days > 7:
            continue
        out.append({"grant_id": r["grant_id"], "name": r["name"], "link": r["link"],
                    "deadline_date": r["deadline_date"], "days_left": days})
    out.sort(key=lambda x: x["days_left"])
    # «Уведомить об открытии»: приём по подписке уже открылся — показываем первым
    opened = [{"grant_id": r["grant_id"], "name": r["name"], "link": r["link"], "deadline_date": r["deadline_date"],
               "days_left": _days_left(r["deadline_date"]), "kind": "opened"} for r in await get_opened_alerts(uid)]
    return opened + out


@app.get("/api/reminders")
async def api_reminders(uid: int = Depends(current_user)):
    return {"items": await _reminders_for(uid)}


# ---------------------------------------------------------------------------
# Каталог, поиск, избранное
# ---------------------------------------------------------------------------
Scope = Literal["kz", "abroad", "all"]


@app.get("/api/grants")
async def api_grants(
    category: Scope = "abroad",
    degree: Literal[DEGREES] = "all",
    country: Optional[str] = Query(default=None, pattern=r"^[A-Za-z]{2}$"),
    funding: Optional[Literal["full", "partial"]] = None,
    deadline: Optional[Literal["open", "upcoming"]] = None,
    req: Optional[Literal[REQUIREMENTS]] = None,
    cursor: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=12, ge=1, le=50),
    uid: int = Depends(current_user),
):
    """Каталог. category — раздел (Казахстан / зарубеж / все), остальные параметры — фильтры.

    Следующая страница запрашивается по next_cursor (id последней записи), а не по смещению.
    """
    country = country.upper() if country else None
    if cursor is None:
        await log_event(uid, "browse_catalog", {"region": category, "degree": degree})

    async def load():
        return await get_grants_page(category, degree, country=country, funding=funding, deadline=deadline,
                                     req=req, limit=limit, cursor=cursor)

    items, total = await cached(("grants", category, degree, country, funding, deadline, req, cursor, limit),
                                CACHE_TTL_PAGES, load)
    favs = await _favorite_ids(uid)
    return {"items": [_grant_public(g, g["id"] in favs) for g in items], "total": total, "limit": limit,
            "next_cursor": items[-1]["id"] if len(items) == limit else None}


@app.get("/api/meta")
async def api_meta():
    """Справочники для фильтров каталога."""
    countries = await cached(("countries",), CACHE_TTL_REFERENCE, get_active_countries)
    return {"countries": countries, "degrees": DEGREES, "funding": ["full", "partial"],
            "deadline": ["open", "upcoming"], "requirements": REQUIREMENTS}


@app.get("/api/grants/search")
async def api_search(q: str = Query(default="", max_length=100), scope: Scope = "all",
                     uid: int = Depends(current_user)):
    q = " ".join(q.split())
    if len(q) < 2:
        return {"items": [], "query": q}
    await log_event(uid, "search", {"query": q, "scope": scope})
    results = await search_grants(q, limit=20, scope=scope)
    favs = await _favorite_ids(uid)
    return {"items": [_grant_public(g, g["id"] in favs) for g in results], "query": q}


@app.get("/api/grants/{grant_id}")
async def api_grant(grant_id: int, uid: int = Depends(current_user)):
    g = await get_grant_by_id(grant_id)
    if not g or g.get("record_status") in ("flagged_review", "draft"):   # не прошедшие проверку не показываем
        raise HTTPException(404, "Грант не найден")
    return _grant_public(g, await is_favorite(uid, grant_id))


@app.get("/api/favorites")
async def api_favorites(uid: int = Depends(current_user)):
    favs = await get_user_favorites(uid)
    return {"items": [_grant_public(g, True) for g in favs]}


@app.post("/api/favorites/{grant_id}")
async def api_fav_add(grant_id: int, uid: int = Depends(current_user)):
    if not await get_grant_by_id(grant_id):
        raise HTTPException(404, "Грант не найден")
    await add_favorite(uid, grant_id)
    await log_event(uid, "favorite_add", {"grant_id": grant_id})
    return {"ok": True, "is_favorite": True}


@app.delete("/api/favorites/{grant_id}")
async def api_fav_remove(grant_id: int, uid: int = Depends(current_user)):
    await remove_favorite(uid, grant_id)
    await log_event(uid, "favorite_remove", {"grant_id": grant_id})
    return {"ok": True, "is_favorite": False}


@app.post("/api/alerts/{grant_id}")
async def api_alert_add(grant_id: int, uid: int = Depends(current_user)):
    """«Уведомить об открытии» — для грантов, приём на которые ещё не начался."""
    g = await get_grant_by_id(grant_id)
    if not g or g.get("record_status") != "active":
        raise HTTPException(404, "Грант не найден")
    if g.get("status") != "upcoming":
        raise HTTPException(400, "Уведомление можно включить только для грантов, приём на которые ещё не открыт")
    await add_open_alert(uid, grant_id)
    await log_event(uid, "alert_add", {"grant_id": grant_id})
    return {"ok": True, "alert": True}


@app.delete("/api/alerts/{grant_id}")
async def api_alert_remove(grant_id: int, uid: int = Depends(current_user)):
    await remove_open_alert(uid, grant_id)
    return {"ok": True, "alert": False}


# ---------------------------------------------------------------------------
# ИИ-консультант
# ---------------------------------------------------------------------------
class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    lang: Optional[str] = Field(default='ru', max_length=2)


class FeedbackIn(BaseModel):
    answer_id: int
    rating: int = Field(ge=-1, le=1)


@app.post("/api/ask")
async def api_ask(data: AskIn, request: Request, uid: int = Depends(current_user)):
    _check_ask_limits(request, uid)
    await log_event(uid, "ai_question")
    answer = await ask_gemini_consultant(data.question.strip(), user_id=uid, lang=data.lang)
    answer_id = await save_ai_answer(uid, data.question.strip(), answer)
    return {"answer_id": answer_id, "answer": answer}


@app.post("/api/ask/stream")
async def api_ask_stream(data: AskIn, request: Request, uid: int = Depends(current_user)):
    """Потоковый ответ: NDJSON — {"delta": "..."} по мере генерации, в конце {"done": true, "answer_id": N}."""
    _check_ask_limits(request, uid)
    await log_event(uid, "ai_question")
    question = data.question.strip()

    async def gen():
        parts = []
        try:
            async for piece in ask_consultant_stream(question, user_id=uid, lang=data.lang):
                parts.append(piece)
                yield json.dumps({"delta": piece}, ensure_ascii=False) + "\n"
            answer = "".join(parts).strip() or "⚠️ Пустой ответ модели. Попробуй переформулировать вопрос."
        except Exception as e:
            logging.error(f"Ошибка потокового ответа ИИ: {e}")
            answer = "⚠️ ИИ-консультант временно недоступен. Попробуй через минуту."
            yield json.dumps({"delta": answer}, ensure_ascii=False) + "\n"
        answer_id = await save_ai_answer(uid, question, answer)
        yield json.dumps({"done": True, "answer_id": answer_id}, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/feedback")
async def api_feedback(data: FeedbackIn, uid: int = Depends(current_user)):
    await set_answer_rating(data.answer_id, data.rating)
    await log_event(uid, "ai_feedback", {"answer_id": data.answer_id, "rating": data.rating})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Публичная статистика для главной
# ---------------------------------------------------------------------------
import re as _re  # noqa: E402

_IELTS_RE = _re.compile(r"ielts[^0-9]{0,12}(\d(?:[.,]\d)?)", _re.I)
_GPA_RE = _re.compile(r"gpa[^0-9]{0,12}(\d(?:[.,]\d{1,2})?)", _re.I)


def _match_score(g: dict, profile: dict) -> tuple:
    """Насколько грант подходит профилю: (баллы, причины). Простая эвристика без ИИ."""
    score, why = 0.0, []
    text = f"{g['name']} {g['coverage']} {g['requirements']}".lower()
    field = (profile.get("field_of_interest") or "").strip().lower()
    if field:
        words = [w for w in _re.findall(r"[a-zа-яё]{3,}", field) if w not in ("and", "или", "the")]
        hits = [w for w in words if w in text]
        if hits:
            score += 3; why.append("field")
    ielts = profile.get("ielts")
    m = _IELTS_RE.search(g["requirements"])
    if ielts and m:
        need = float(m.group(1).replace(",", "."))
        if ielts >= need:
            score += 2; why.append("ielts_ok")
        else:
            score -= 3; why.append("ielts_low")
    gpa = profile.get("gpa")
    m = _GPA_RE.search(g["requirements"])
    if gpa and m:
        need = float(m.group(1).replace(",", "."))
        if gpa >= need:
            score += 1.5; why.append("gpa_ok")
        else:
            score -= 2; why.append("gpa_low")
    if g.get("status") == "open":
        score += 1; why.append("open")
    dl = _days_left(g.get("deadline_date"))
    if dl is not None and 0 <= dl <= 30:
        score += 0.5
    return score, why


@app.get("/api/home")
async def api_home(request: Request, uid: int = Depends(current_user)):
    """Персональная главная: подходящие гранты, ближайшие дедлайны, заполненность профиля, совет."""
    profile = await get_user_profile(uid)
    favs = await _favorite_ids(uid)
    grants = await get_all_active_grants()
    has_profile = any(profile.get(k) for k in ("ielts", "gpa", "field_of_interest"))
    scored = []
    for g in grants:
        sc, why = _match_score(g, profile) if has_profile else (0, [])
        if "ielts_low" in why or "gpa_low" in why:
            continue
        scored.append((sc, g, why))
    scored.sort(key=lambda x: (-x[0], x[1].get("deadline_date") or "9999"))
    matches = [dict(_grant_public(g, g["id"] in favs), why=why, score=sc) for sc, g, why in scored[:6]]
    strong = sum(1 for sc, _, _ in scored if sc >= 3)
    upcoming = sorted([g for g in grants if g.get("deadline_date") and (_days_left(g["deadline_date"]) or -1) >= 0],
                      key=lambda g: g["deadline_date"])[:5]
    fav_upcoming = [g for g in upcoming if g["id"] in favs]
    completeness = round(100 * sum(1 for k in ("ielts", "gpa", "field_of_interest") if profile.get(k)) / 3)
    if not has_profile:
        tip = "profile"
    elif not favs:
        tip = "favorites"
    elif fav_upcoming and (_days_left(fav_upcoming[0]["deadline_date"]) or 99) <= 14:
        tip = "deadline"
    else:
        tip = "chat"
    account = await account_from_request(request)
    return {
        "account": {"name": account.get("name") or (account.get("email") or "").split("@")[0]} if account else None,
        "profile": {k: profile.get(k) for k in ("ielts", "gpa", "field_of_interest")}, "completeness": completeness,
        "matches": matches, "strong_matches": strong if has_profile else None, "total_active": len(grants),
        "upcoming": [_grant_public(g, g["id"] in favs) for g in (fav_upcoming or upcoming)[:4]],
        "upcoming_is_favorites": bool(fav_upcoming), "favorites_count": len(favs), "tip": tip,
        "scan": {**ai_scanner.scan_progress, "last": ai_scanner.last_scan_stats.get("finished_at")},
    }


@app.get("/api/recent-grants")
async def api_recent(limit: int = Query(default=10, ge=1, le=30)):
    async def load():
        return await get_recent_grants(limit)

    items = [dict(g, days_left=_days_left(g.get("deadline_date")))
             for g in await cached(("recent", limit), CACHE_TTL_PAGES, load)]
    return {"items": items}


@app.get("/api/scan/progress")
async def api_scan_progress():
    sp = ai_scanner.scan_progress
    return {**sp, "last_finished": ai_scanner.last_scan_stats.get("finished_at"),
            "last_new": ai_scanner.last_scan_stats.get("new"), "sources_total": len(UNIVERSITIES) + len(PROGRAMS) + len(ai_scanner.BROAD_QUERIES)}


@app.get("/api/stats/public")
async def api_public_stats():
    async def load():
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute(
                "SELECT is_domestic, COUNT(*) FROM grants WHERE record_status = 'active' GROUP BY is_domestic"
            ) as cur:
                by_scope = {r[0]: r[1] for r in await cur.fetchall()}
            async with db.execute("SELECT COUNT(*) FROM grants WHERE record_status = 'active' AND status = 'open'") as cur:
                open_now = (await cur.fetchone())[0]
            async with db.execute("SELECT MAX(last_checked) FROM monitor_sources") as cur:
                last_checked = (await cur.fetchone())[0]
        return {
            "active_total": sum(by_scope.values()), "abroad": by_scope.get(0, 0), "kz": by_scope.get(1, 0),
            "open_now": open_now, "universities": len(UNIVERSITIES), "programs": len(PROGRAMS),
            "last_checked": last_checked, "scan_hours": SCAN_HOURS, "timezone": TIMEZONE,
        }

    return await cached(("public_stats",), CACHE_TTL_PAGES, load)


@app.get("/healthz")
async def healthz():
    """Проверка живости для хостинга и мониторинга: отвечает ли база и не завис ли сканер."""
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("SELECT 1")
    except Exception as e:
        logging.error(f"healthz: база недоступна: {e}")
        return JSONResponse({"status": "error", "db": False}, status_code=503)
    return {"status": "ok", "db": True, "scan": ai_scanner.scan_progress.get("phase"),
            "last_scan": ai_scanner.last_scan_stats.get("finished_at")}


# ---------------------------------------------------------------------------
# Админ: сканер, мониторинг, статистика, снятие с публикации
# ---------------------------------------------------------------------------
async def _run_scan_cycle():
    if _scan_lock.locked():
        return
    async with _scan_lock:
        _scan_state.update({"running": True, "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
                            "finished_at": None, "result": None, "error": None})
        try:
            expired = await cleanup_expired_grants()
            new_grants = await scan_and_save_grants()
            _scan_state["result"] = {"new": len(new_grants), "expired": expired,
                                     "grants": [_grant_public(g) for g in new_grants[:30]]}
        except Exception as e:
            logging.error(f"Ошибка сканирования (web): {e}", exc_info=True)
            _scan_state["error"] = str(e)
        finally:
            _scan_state["running"] = False
            _scan_state["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            cache_invalidate()   # каталог изменился — кэш страниц и счётчиков больше не годится


@app.post("/api/admin/scan")
async def api_admin_scan(_: bool = Depends(require_admin)):
    if _scan_state["running"]:
        return JSONResponse({"ok": False, "message": "Сканирование уже идёт"}, status_code=409)
    asyncio.create_task(_run_scan_cycle())
    return {"ok": True, "message": "ИИ-сканер запущен в фоне"}


@app.get("/api/admin/scan/status")
async def api_admin_scan_status(_: bool = Depends(require_admin)):
    return {**_scan_state, "stats": ai_scanner.last_scan_stats}


@app.get("/api/admin/monitor")
async def api_admin_monitor(_: bool = Depends(require_admin)):
    summary = await get_monitor_summary()
    return {**summary, "last_scan": ai_scanner.last_scan_stats, "scan_hours": SCAN_HOURS, "timezone": TIMEZONE}


@app.get("/api/admin/stats")
async def api_admin_stats(_: bool = Depends(require_admin)):
    return {"events": await get_events_summary(days=7), "active_users": await get_active_users_count(days=7),
            "users_total": len(await get_all_users())}


@app.get("/api/admin/llm")
async def api_admin_llm(_: bool = Depends(require_admin)):
    return {"provider": LLM_PROVIDER, "fallback": LLM_FALLBACK or None,
            "groq_models": {"chat": ai_scanner.GROQ_CHAT_MODEL, "scan": ai_scanner.GROQ_SCAN_MODEL} if LLM_PROVIDER == "groq" else None,
            "gemini_model": GEMINI_MODEL if "gemini" in (LLM_PROVIDER, LLM_FALLBACK) else None,
            "ollama_model": OLLAMA_MODEL, "ollama_chat_model": OLLAMA_CHAT_MODEL, "ollama_status": await ollama_status()}


@app.post("/api/admin/deactivate/{grant_id}")
async def api_admin_deactivate(grant_id: int, _: bool = Depends(require_admin)):
    if not await get_grant_by_id(grant_id):
        raise HTTPException(404, "Грант не найден")
    await set_grant_active(grant_id, False)
    cache_invalidate()
    return {"ok": True}


# --- Модерация: очередь на проверку, синонимы, журнал запусков ---
class ReviewIn(BaseModel):
    approve: bool
    # при одобрении страну можно исправить: код ISO-2 или "" (несколько стран); None — оставить как есть
    country_code: Optional[str] = Field(default=None, max_length=2)


class SynonymIn(BaseModel):
    canonical: str = Field(min_length=2, max_length=120)
    alias: str = Field(min_length=2, max_length=120)


def _review_public(g: dict) -> dict:
    return {**_grant_public(g), "record_status": g.get("record_status"), "review_note": g.get("review_note"),
            "first_seen": g.get("first_seen")}


@app.get("/api/admin/review")
async def api_admin_review(_: bool = Depends(require_admin)):
    return {"items": [_review_public(g) for g in await get_review_queue()]}


@app.post("/api/admin/review/{grant_id}")
async def api_admin_review_decide(grant_id: int, data: ReviewIn, _: bool = Depends(require_admin)):
    country, set_country = None, data.country_code is not None
    if data.country_code:
        country = normalize_country(data.country_code)
        if not country:
            raise HTTPException(400, "Код страны — две латинские буквы (ISO-2), например KZ или DE")
    if not await review_grant(grant_id, data.approve, country, set_country):
        raise HTTPException(404, "Запись не найдена в очереди")
    cache_invalidate()
    return {"ok": True}


@app.get("/api/admin/synonyms")
async def api_admin_synonyms(_: bool = Depends(require_admin)):
    return {"items": await get_synonyms()}


@app.post("/api/admin/synonyms")
async def api_admin_synonym_add(data: SynonymIn, _: bool = Depends(require_admin)):
    if not await add_synonym(" ".join(data.canonical.split()), " ".join(data.alias.split())):
        raise HTTPException(409, "Такой синоним уже есть")
    return {"ok": True}


@app.delete("/api/admin/synonyms/{synonym_id}")
async def api_admin_synonym_delete(synonym_id: int, _: bool = Depends(require_admin)):
    await delete_synonym(synonym_id)
    return {"ok": True}


@app.get("/api/admin/runs")
async def api_admin_runs(_: bool = Depends(require_admin)):
    return {"items": await get_scan_runs(20)}


@app.post("/api/admin/login")
async def api_admin_login(_: bool = Depends(require_admin)):
    return {"ok": True}


# ---------------------------------------------------------------------------
# Старт
# ---------------------------------------------------------------------------
async def _daily_cleanup_loop():
    """Очистка истёкших грантов и пересчёт статусов: при старте и затем ежедневно в 00:01 UTC."""
    while True:
        try:
            deleted = await cleanup_expired_grants()
            cache_invalidate()
            if deleted:
                logging.info(f"Ежедневная очистка: удалено грантов с прошедшим дедлайном: {deleted}")
        except Exception as e:
            logging.error(f"Ошибка ежедневной очистки: {e}", exc_info=True)
        now = datetime.datetime.now(datetime.timezone.utc)
        next_run = (now + datetime.timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
        await asyncio.sleep((next_run - now).total_seconds())


@app.on_event("startup")
async def _startup():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=[logging.FileHandler(LOGS_DIR / "web.log", encoding="utf-8"), logging.StreamHandler()])
    for noisy in ("httpx", "httpcore", "ddgs", "primp", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    await init_db()
    asyncio.create_task(_daily_cleanup_loop())
    asyncio.create_task(warm_up_llm())  # модель грузится в память заранее, первый ответ быстрее
    if not WEB_ADMIN_TOKEN:
        logging.warning("WEB_ADMIN_TOKEN не задан — админ-панель сайта отключена.")
    if WEB_RUN_SCHEDULER:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler(timezone=TIMEZONE,
                                     job_defaults={"misfire_grace_time": 12 * 3600, "coalesce": True, "max_instances": 1})
        for h in SCAN_HOURS:
            scheduler.add_job(_run_scan_cycle, "cron", hour=h, minute=0, id=f"web_scan_{h:02d}", replace_existing=True)
        scheduler.start()
        logging.info(f"Плановый сканер сайта включён: {SCAN_HOURS_RAW} ({TIMEZONE})")
    else:
        logging.info("Плановый сканер сайта выключен (WEB_RUN_SCHEDULER=0) — сканирует Telegram-бот.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("website.web:app", host=WEB_HOST, port=WEB_PORT, reload=False)
