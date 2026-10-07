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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response as RawResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from core import ai_scanner  # noqa: E402
from core.ai_scanner import (  # noqa: E402
    GEMINI_MODEL, LLM_FALLBACK, LLM_PROVIDER, OLLAMA_CHAT_MODEL, OLLAMA_MODEL, PROGRAMS, UNIVERSITIES,
    ask_gemini_consultant, ask_consultant_stream, ollama_status, recheck_links, scan_and_save_grants, warm_up_llm,
)
from core.database import (  # noqa: E402
    DB_NAME, DEGREES, LOGS_DIR, REQUIREMENTS, add_favorite, add_open_alert, add_synonym, add_user,
    SORTS, backup_database, cleanup_expired_grants, get_open_alert_ids, get_opened_alerts, remove_open_alert,
    delete_synonym, get_active_countries, get_active_users_count, get_all_users, get_data_version,
    get_events_summary, get_favorites_with_deadlines, get_grant_by_id, get_grants_page, get_monitor_summary,
    get_review_queue, get_scan_runs, get_synonyms, get_user_favorites,
    get_user_profile, init_db, is_favorite, log_event, remove_favorite, review_grant,
    get_recent_grants, get_all_active_grants,
    save_ai_answer, search_grants, set_answer_rating, set_grant_active, set_user_profile,
    create_link_code, consume_link_code, get_link_code, get_account_by_id, is_linked, get_audience_stats,
    get_public_usage, get_audience_rows,
)
from core.geo import normalize_country  # noqa: E402
from core.matching import has_profile, match_grants  # noqa: E402

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
    RateLimit, SESSION_COOKIE, account_from_request, client_ip, read_session, read_uid_cookie, router as auth_router,
    set_login_cookies, set_uid_cookie,
)

# Привязка Telegram: имя бота для ссылки t.me/<бот>?start=link_<код>; токен — чтобы сообщить в Telegram о привязке с сайта
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
link_limit = RateLimit(10, 600)   # попыток ввести код с одного IP за 10 минут — коды короткие

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
async def landing(request: Request, response: Response, uid: int = Depends(current_user)):
    """Лендинг (hero-экран). Приложение живёт на /app. Заход считается событием: откуда пришёл — в payload."""
    await log_event(uid, "web_visit", {"page": "landing", "from": request.query_params.get("from") or None})
    page = FileResponse(STATIC_DIR / "landing" / "index.html")
    page.raw_headers.extend(response.raw_headers)   # cookie нового посетителя
    return page


@app.get("/app")
async def index(request: Request, response: Response, uid: int = Depends(current_user)):
    await log_event(uid, "web_visit", {"page": "app", "from": request.query_params.get("from") or None})
    page = FileResponse(STATIC_DIR / "index.html")
    page.raw_headers.extend(response.raw_headers)
    return page


PUBLIC_URL = (os.getenv("PUBLIC_URL") or os.getenv("SITE_URL") or "").strip().rstrip("/")


def _html(s) -> str:
    import html as _h
    return _h.escape(str(s or ""), quote=True)


@app.get("/grant/{grant_id}", response_class=HTMLResponse)
async def grant_page(grant_id: int):
    """Отдельная страница гранта: ей можно делиться, её индексируют поисковики."""
    g = await get_grant_by_id(grant_id)
    if not g or g.get("record_status") != "active":
        raise HTTPException(404, "Грант не найден")
    p = _grant_public(g)
    from core.geo import flag_emoji
    region = "Казахстан" if p["category"] == "kz" else "За рубежом"
    degree = {"bachelor": "Бакалавриат", "master": "Магистратура", "phd": "PhD", "language": "Языковые курсы"}.get(p["degree"], "Все уровни")
    status = {"open": "приём открыт", "upcoming": "скоро откроется"}.get(p["status"], "")
    deadline = "круглый год" if p["is_ongoing"] else (p["deadline_date"] or p["deadline"])
    desc = _html(f"{p['coverage']}. Требования: {p['requirements']}. Дедлайн: {deadline}.")[:300]
    canonical = f"{PUBLIC_URL}/grant/{grant_id}" if PUBLIC_URL else f"/grant/{grant_id}"
    rows = "".join(f"<div class=\"g-row\"><div><b>{k}:</b> {_html(v)}</div></div>" for k, v in (
        ("Покрытие", p["coverage"]), ("Требования", p["requirements"]), ("Дедлайн", deadline),
        ("Уровень", degree), ("Регион", f"{region} {flag_emoji(p['country_code']) or '🌍'}"), ("Источник", p["source"] or "—")) if v)
    tags = "".join(f"<span class=\"tag\">{_html(x)}</span>" for x in (status, {"full": "полный грант", "partial": "частичный грант"}.get(p["funding"], "")) if x)
    return f"""<!doctype html><html lang="ru" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html(p['name'])} — GrantHub</title>
<meta name="description" content="{desc}"><link rel="canonical" href="{_html(canonical)}">
<meta property="og:title" content="{_html(p['name'])}"><meta property="og:description" content="{desc}"><meta property="og:type" content="article">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/app.css?v=9">
<script>if (/Windows/.test(navigator.userAgent) && !/Firefox/.test(navigator.userAgent)) document.documentElement.classList.add('flag-font');</script></head>
<body><main class="container" style="max-width:820px;margin:0 auto;padding:40px 16px">
<p class="eyebrow">{_html(region)} · {_html(degree)}</p>
<h1 class="vtitle">{_html(p['name'])}</h1>
<div class="g-tags" style="margin:14px 0">{tags}</div>
<article class="gcard" style="margin-top:20px">{rows}
<div class="g-foot"><a class="g-apply" href="{_html(p['link'])}" target="_blank" rel="noopener nofollow">Подать заявку ↗</a>
<a class="btn btn-ghost btn-sm" href="/app#search">Все гранты</a></div></article>
<p class="muted small" style="margin-top:24px">GrantHub — каталог грантов и стипендий для студентов из Казахстана.</p>
</main></body></html>"""


@app.get("/sitemap.xml")
async def sitemap():
    base = PUBLIC_URL or ""
    urls = [f"{base}/", f"{base}/app"] + [f"{base}/grant/{g['id']}" for g in await get_all_active_grants()]
    body = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">" + \
        "".join(f"<url><loc>{_html(u)}</loc></url>" for u in urls) + "</urlset>"
    return RawResponse(body, media_type="application/xml")


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return f"User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: {PUBLIC_URL}/sitemap.xml\n"


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
        "telegram_linked": await is_linked(uid),
        "bot_username": BOT_USERNAME or None,
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
    offset: int = Query(default=0, ge=0, le=5000),
    sort: Literal[tuple(SORTS)] = "new",
    limit: int = Query(default=12, ge=1, le=50),
    uid: int = Depends(current_user),
):
    """Каталог. category — раздел (Казахстан / зарубеж / все), остальные параметры — фильтры.

    Следующая страница запрашивается по next_cursor (id последней записи), а не по смещению.
    """
    country = country.upper() if country else None
    if cursor is None and offset == 0:
        await log_event(uid, "browse_catalog", {"region": category, "degree": degree})

    async def load():
        return await get_grants_page(category, degree, country=country, funding=funding, deadline=deadline,
                                     req=req, limit=limit, cursor=cursor, offset=offset, sort=sort)

    items, total = await cached(("grants", category, degree, country, funding, deadline, req, cursor, offset, sort, limit),
                                CACHE_TTL_PAGES, load)
    favs = await _favorite_ids(uid)
    has_more = len(items) == limit and offset + len(items) < total
    return {"items": [_grant_public(g, g["id"] in favs) for g in items], "total": total, "limit": limit,
            "next_cursor": items[-1]["id"] if has_more and sort == "new" else None,
            "next_offset": offset + len(items) if has_more else None}


@app.get("/api/meta")
async def api_meta():
    """Справочники для фильтров каталога."""
    countries = await cached(("countries",), CACHE_TTL_REFERENCE, get_active_countries)
    return {"countries": countries, "degrees": DEGREES, "funding": ["full", "partial"], "sorts": list(SORTS),
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
def _match_item(item: dict, favs: set) -> dict:
    g = item["grant"]
    return dict(_grant_public(g, g["id"] in favs), why=item["why"], score=item["score"], gaps=item["gaps"])


@app.get("/api/match")
async def api_match(uid: int = Depends(current_user), limit: int = Query(default=30, ge=1, le=100)):
    """«Мне подходит»: гранты под профиль. near — не хватает одного показателя (IELTS или GPA)."""
    profile = await get_user_profile(uid)
    favs = await _favorite_ids(uid)
    filled = has_profile(profile)
    if not filled:
        return {"has_profile": False, "profile": profile, "items": [], "near": [], "total": 0, "strong": 0}
    result = match_grants(await get_all_active_grants(), profile)
    await log_event(uid, "match_view")
    return {
        "has_profile": True, "profile": profile,
        "items": [_match_item(i, favs) for i in result["matches"][:limit]],
        "near": [_match_item(i, favs) for i in result["near"][:10]],
        "total": len(result["matches"]), "strong": sum(1 for i in result["matches"] if i["score"] >= 3),
    }


@app.get("/api/home")
async def api_home(request: Request, uid: int = Depends(current_user)):
    """Персональная главная: подходящие гранты, ближайшие дедлайны, заполненность профиля, совет."""
    profile = await get_user_profile(uid)
    favs = await _favorite_ids(uid)
    grants = await get_all_active_grants()
    filled = has_profile(profile)
    if filled:
        ranked = match_grants(grants, profile)["matches"]
    else:
        ranked = [{"grant": g, "score": 0, "why": [], "gaps": {}} for g in grants]
    matches = [_match_item(i, favs) for i in ranked[:6]]
    strong = sum(1 for i in ranked if i["score"] >= 3)
    has_profile_flag = filled
    upcoming = sorted([g for g in grants if g.get("deadline_date") and (_days_left(g["deadline_date"]) or -1) >= 0],
                      key=lambda g: g["deadline_date"])[:5]
    fav_upcoming = [g for g in upcoming if g["id"] in favs]
    completeness = round(100 * sum(1 for k in ("ielts", "gpa", "field_of_interest") if profile.get(k)) / 3)
    if not has_profile_flag:
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
        "matches": matches, "strong_matches": strong if has_profile_flag else None, "total_active": len(grants),
        "upcoming": [_grant_public(g, g["id"] in favs) for g in (fav_upcoming or upcoming)[:4]],
        "upcoming_is_favorites": bool(fav_upcoming), "favorites_count": len(favs), "tip": tip,
        "scan": {**ai_scanner.scan_progress, "last": ai_scanner.last_scan_stats.get("finished_at")},
    }


# ---------------------------------------------------------------------------
# Привязка Telegram и сайта: один аккаунт, общее избранное и профиль
# ---------------------------------------------------------------------------
class LinkCodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)


_LINK_ERRORS = {
    "bad_code": (400, "Код не найден или уже использован. Запроси новый в боте командой /link."),
    "expired": (400, "Код устарел — он живёт 10 минут. Запроси новый."),
    "same": (400, "Это уже один и тот же аккаунт."),
    "web_linked": (409, "К этому аккаунту сайта уже привязан Telegram."),
    "tg_taken": (409, "К этому Telegram уже привязан другой аккаунт сайта. Войди в него или напиши администратору."),
}


async def _apply_linked_cookies(request: Request, response: Response, new_uid: int):
    """После привязки посетитель продолжает работать уже под Telegram id.

    У вошедшего пользователя uid аккаунта только что сменился, поэтому старая сессия уже не проходит
    проверку account_from_request — берём id аккаунта прямо из подписанной cookie и выдаём новую сессию.
    """
    sess = read_session(request.cookies.get(SESSION_COOKIE, ""))
    if sess:
        fresh = await get_account_by_id(sess[0])
        if fresh and fresh["uid"] == new_uid:
            set_login_cookies(response, fresh)
            return
    set_uid_cookie(response, new_uid, UID_MAX_AGE)


async def _notify_telegram(chat_id: int, text: str):
    """Сообщение в Telegram от имени бота (сайт и бот делят один BOT_TOKEN). Ошибки не критичны."""
    if not BOT_TOKEN:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            await session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                               json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except Exception as e:  # noqa: BLE001
        logging.warning(f"Не удалось сообщить в Telegram о привязке: {e}")


@app.post("/api/link/code")
async def api_link_code(request: Request, uid: int = Depends(current_user)):
    """Код для ввода в боте (/link КОД) или ссылка t.me/бот?start=link_КОД."""
    if await is_linked(uid):
        raise HTTPException(409, "Telegram уже привязан.")
    if not link_limit.hit(client_ip(request)):
        raise HTTPException(429, "Слишком много запросов. Подожди немного.")
    info = await create_link_code("web", uid)
    return {**info, "bot_username": BOT_USERNAME or None,
            "bot_url": f"https://t.me/{BOT_USERNAME}?start=link_{info['code']}" if BOT_USERNAME else None}


@app.get("/api/link/status")
async def api_link_status(request: Request, response: Response, code: str = Query(min_length=4, max_length=12),
                          uid: int = Depends(current_user)):
    """Сайт опрашивает: бот уже принял код? Если да — cookie переезжают на Telegram id."""
    row = await get_link_code(code)
    if not row or row["kind"] != "web" or uid not in (row["uid"], row["linked_uid"]):
        return {"linked": False, "expired": True}
    if not row["used_at"]:
        return {"linked": False, "expired": row["expires_at"] < datetime.datetime.utcnow().isoformat(timespec="seconds")}
    await _apply_linked_cookies(request, response, row["linked_uid"])
    return {"linked": True, "expired": False}


@app.post("/api/link/confirm")
async def api_link_confirm(data: LinkCodeIn, request: Request, response: Response, uid: int = Depends(current_user)):
    """Пользователь ввёл на сайте код, который выдал бот (/link)."""
    if not link_limit.hit(client_ip(request)):
        raise HTTPException(429, "Слишком много попыток. Подожди 10 минут.")
    result = await consume_link_code(data.code, "tg", uid)
    if not result["ok"]:
        status, text = _LINK_ERRORS.get(result["error"], (400, "Не удалось привязать."))
        raise HTTPException(status, text)
    await _apply_linked_cookies(request, response, result["uid"])
    await log_event(result["uid"], "telegram_linked", {"from": "web"})
    await _notify_telegram(result["uid"], "✅ <b>Сайт GrantHub привязан к этому Telegram.</b>\n"
                                          "Избранное, профиль и напоминания теперь общие — и здесь, и в браузере.")
    return {"linked": True}


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
        usage = await get_public_usage()   # реальные цифры: сколько людей уже пользуются, обновляется раз в день
        return {
            "active_total": sum(by_scope.values()), "abroad": by_scope.get(0, 0), "kz": by_scope.get(1, 0),
            "open_now": open_now, "universities": len(UNIVERSITIES), "programs": len(PROGRAMS),
            "last_checked": last_checked, "scan_hours": SCAN_HOURS, "timezone": TIMEZONE,
            "people": usage["people"], "users": usage,
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


@app.get("/api/admin/users.csv")
async def api_admin_users_csv(_: bool = Depends(require_admin)):
    """Выгрузка аудитории: кто, откуда, когда пришёл, последняя активность. Только администратору."""
    import csv
    import io as _io
    buf = _io.StringIO()
    buf.write("\ufeff")   # BOM — чтобы Excel открыл кириллицу
    w = csv.writer(buf, delimiter=";")
    w.writerow(["user_id", "source", "email", "name", "joined_at", "last_seen", "actions", "favorites", "linked", "subscribed", "ielts", "gpa", "field"])
    for r in await get_audience_rows():
        w.writerow([r["user_id"], r["source"], r["email"] or "", r["name"] or "", r["joined_at"] or "", r["last_seen"] or "",
                    r["actions"], r["favorites"], "yes" if r["linked_at"] else "", "yes" if r["subscribed"] else "",
                    r["ielts"] or "", r["gpa"] or "", r["field_of_interest"] or ""])
    name = f"granthub-audience-{datetime.date.today().isoformat()}.csv"
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/admin/stats")
async def api_admin_stats(_: bool = Depends(require_admin)):
    return {"events": await get_events_summary(days=7), "active_users": await get_active_users_count(days=7),
            "users_total": len(await get_all_users()), "audience": await get_audience_stats()}


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
    deadline_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class SynonymIn(BaseModel):
    canonical: str = Field(min_length=2, max_length=120)
    alias: str = Field(min_length=2, max_length=120)


def _review_public(g: dict) -> dict:
    return {**_grant_public(g), "record_status": g.get("record_status"), "review_note": g.get("review_note"),
            "first_seen": g.get("first_seen"), "deadline_confirmed": bool(g.get("deadline_confirmed"))}


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
    if data.deadline_date:
        try:
            datetime.date.fromisoformat(data.deadline_date)
        except ValueError:
            raise HTTPException(400, "Дата дедлайна — в формате ГГГГ-ММ-ДД")
    if not await review_grant(grant_id, data.approve, country, set_country, data.deadline_date):
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
            path = await backup_database()   # копия до удаления — на случай ошибки в датах
            logging.info(f"Резервная копия базы: {path}")
        except Exception as e:
            logging.error(f"Ошибка резервной копии: {e}", exc_info=True)
        try:
            deleted = await cleanup_expired_grants()
            cache_invalidate()
            if deleted:
                logging.info(f"Ежедневная очистка: удалено грантов с прошедшим дедлайном: {deleted}")
        except Exception as e:
            logging.error(f"Ошибка ежедневной очистки: {e}", exc_info=True)
        if datetime.datetime.now(datetime.timezone.utc).weekday() == 0 and WEB_RUN_SCHEDULER:   # иначе ссылки проверяет бот
            try:
                await recheck_links()
                cache_invalidate()
            except Exception as e:
                logging.error(f"Ошибка проверки ссылок: {e}", exc_info=True)
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
