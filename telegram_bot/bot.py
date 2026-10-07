import asyncio
import html
import logging
import re
import time
import datetime
from typing import Optional
from functools import wraps
import os
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core import ai_scanner
from core.ai_scanner import ask_gemini_consultant, recheck_links, scan_and_save_grants, ollama_status, warm_up_llm, LLM_PROVIDER, LLM_FALLBACK, GEMINI_MODEL, OLLAMA_MODEL, OLLAMA_CHAT_MODEL
from core.database import (
    LOGS_DIR, get_user_lang, set_user_lang,
    get_monitor_summary,
    add_user,
    unsubscribe_user,
    get_all_users,
    get_grants_filtered,
    count_grants_filtered,
    get_grant_by_id,
    set_grant_active,
    add_favorite,
    remove_favorite,
    is_favorite,
    get_user_favorites,
    get_favorites_with_deadlines,
    mark_reminder_sent,
    set_user_profile,
    get_user_profile,
    search_grants,
    init_db,
    log_event,
    count_events_today,
    get_events_summary,
    get_active_users_count,
    save_ai_answer,
    set_answer_rating,
    cleanup_expired_grants,
    add_open_alert,
    remove_open_alert,
    get_open_alert_ids,
    get_opened_alerts,
    mark_alert_notified,
    backup_database,
    get_all_active_grants,
    get_audience_stats,
    get_public_usage,
    refresh_usage_snapshot,
    create_link_code,
    consume_link_code,
    is_linked,
)
from core.geo import flag_emoji
from core.matching import has_profile, match_grants

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Almaty")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").strip().rstrip("/")
# Telegram не принимает кнопки-ссылки на localhost — тогда даём ссылку текстом
SITE_URL_IS_PUBLIC = not any(h in SITE_URL for h in ("localhost", "127.0.0.1", "0.0.0.0"))
PAGE_SIZE = 3

QUESTION_COOLDOWN_SECONDS = 4
QUESTION_DAILY_LIMIT = 40
_last_question_time: dict = {}

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Проверь .env файл.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Задачи пересоздаются при каждом старте, поэтому постоянное хранилище не нужно.
# misfire_grace_time: если бот был выключен в 8:00, задача выполнится при старте в течение 12 часов.
scheduler = AsyncIOScheduler(
    timezone=TIMEZONE,
    job_defaults={"misfire_grace_time": 12 * 3600, "coalesce": True, "max_instances": 1},
)
_scan_lock = asyncio.Lock()

# Часы плановых запусков мониторинга (по TIMEZONE), через запятую. По умолчанию утром и вечером.
SCAN_HOURS_RAW = os.getenv("SCAN_HOURS", "8,20").strip()
SCAN_HOURS = sorted({int(h) for h in SCAN_HOURS_RAW.split(",") if h.strip().isdigit() and 0 <= int(h) <= 23}) or [8]


# --- FSM состояния для профиля ---

class ProfileStates(StatesGroup):
    waiting_ielts = State()
    waiting_gpa = State()
    waiting_field = State()


# --- Утилиты ---

def esc(text) -> str:
    """Экранирование для parse_mode=HTML. None превращается в пустую строку."""
    return html.escape(str(text)) if text is not None else ""


_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
_MD_CODE_RE = re.compile(r"`([^`\n]+)`")
_MD_HEADER_RE = re.compile(r"^#{1,6}\s+(.+)$", re.M)
_MD_BULLET_RE = re.compile(r"^(\s*)[\*\-]\s+", re.M)


def md_to_html(text: str) -> str:
    """Переводит простой Markdown из ответа Gemini в HTML, понятный Telegram."""
    text = esc(text)
    text = _MD_HEADER_RE.sub(r"<b>\1</b>", text)
    text = _MD_BOLD_RE.sub(r"<b>\1</b>", text)
    text = _MD_CODE_RE.sub(r"<code>\1</code>", text)
    text = _MD_BULLET_RE.sub(r"\1• ", text)
    return text


def admin_only(handler):
    @wraps(handler)
    async def wrapper(message: types.Message, *args, **kwargs):
        if message.from_user.id != ADMIN_ID:
            return
        return await handler(message, *args, **kwargs)
    return wrapper


def split_message(text: str, limit: int = 4000) -> list:
    parts = text.split("\n---\n\n")
    chunks = []
    current = ""
    for part in parts:
        piece = (part + "\n---\n\n")
        if len(current) + len(piece) > limit and current:
            chunks.append(current.strip())
            current = piece
        else:
            current += piece
    if current.strip():
        chunks.append(current.strip())
    return chunks


# ---------------------------------------------------------------------------
# Языки бота: ru / kz / en. /lang — выбор, хранится в users.lang
# ---------------------------------------------------------------------------
T = {
    "ru": {
        "start": ("🚀 <b>Твой персональный ИИ-агент по грантам и стипендиям!</b>\n\n"
                  "Каждое утро я сканирую сотни университетов и стипендиальных программ — от Болашака до Erasmus Mundus — "
                  "и приношу тебе только свежие возможности, пока другие их ещё не нашли.\n\n"
                  "🎯 Выбери направление кнопками ниже — и я покажу актуальный каталог.\n"
                  "🌐 Или открой сайт GrantHub — там всё то же самое в браузере (/site).\n"
                  "💬 Или просто напиши мне вопрос, как другу.\n"
                  "🧑‍🎓 Заполни /profile — я буду учитывать твои баллы при советах.\n"
                  "🌍 Язык: /lang\n\nШаг 1 из 2: выбери регион обучения 👇"),
        "people_line": "👥 Нас уже <b>{n}</b> — бот и сайт вместе{delta}.", "people_delta": ", +{d} за неделю",
        "kz_btn": "🇰🇿 Гранты в Казахстане", "abroad_btn": "🌍 Зарубежные гранты", "site_btn": "🌐 Открыть сайт GrantHub",
        "bachelor": "🎓 Бакалавриат", "master": "🏛 Магистратура", "all": "🔎 Показать все уровни", "back_regions": "« Назад к выбору региона",
        "status": "Статус", "source": "Источник", "coverage": "Покрытие", "requirements": "Требования", "deadline": "Дедлайн", "site": "Официальный сайт",
        "open": "🟢 приём открыт", "upcoming": "🟡 скоро откроется",
        "lang_pick": "🌍 Выбери язык / Тілді таңда / Choose a language:", "lang_set": "✅ Язык: Русский",
        "region_step": "Шаг 2 из 2: выбери уровень обучения 👇",
        "match_btn": "🎯 Мне подходит", "match_more": "➡️ Ещё", "match_menu": "🏠 В главное меню",
        "match_title": "🎯 <b>Подходит под твой профиль</b> (показано {shown} из {total}):\n\n",
        "match_near": "\n\n🟡 <b>Почти подходят</b> — не хватает одного показателя:\n\n",
        "match_none": "😔 Пока ни один грант не подходит под профиль целиком. Загляни в каталог: /start",
        "match_no_profile": "🧑‍🎓 Сначала заполни профиль командой /profile — укажи IELTS, GPA или направление, и я подберу гранты под тебя.",
        "why_field": "по направлению", "why_ielts_ok": "IELTS подходит", "why_gpa_ok": "GPA подходит", "why_open": "приём открыт",
        "gap_ielts": "не хватает {n} IELTS", "gap_gpa": "не хватает {n} GPA",
    },
    "kz": {
        "start": ("🚀 <b>Гранттар мен шәкіртақылар бойынша жеке ЖИ-агентің!</b>\n\n"
                  "Әр таң сайын мен жүздеген университет пен шәкіртақы бағдарламасын — Болашақтан Erasmus Mundus-қа дейін — "
                  "сканерлеп, басқалар таппай тұрғанда саған тек жаңа мүмкіндіктерді әкелемін.\n\n"
                  "🎯 Төмендегі батырмалармен бағытты таңда — өзекті каталогты көрсетемін.\n"
                  "🌐 Немесе GrantHub сайтын аш — сол мүмкіндіктер браузерде (/site).\n"
                  "💬 Немесе досыңа жазғандай сұрағыңды жаз.\n"
                  "🧑‍🎓 /profile толтыр — кеңес бергенде балдарыңды ескеремін.\n"
                  "🌍 Тіл: /lang\n\n1-қадам / 2: оқу аймағын таңда 👇"),
        "people_line": "👥 Бізбен бірге <b>{n}</b> адам — бот пен сайт{delta}.", "people_delta": ", аптасына +{d}",
        "kz_btn": "🇰🇿 Қазақстандағы гранттар", "abroad_btn": "🌍 Шетелдік гранттар", "site_btn": "🌐 GrantHub сайтын ашу",
        "bachelor": "🎓 Бакалавриат", "master": "🏛 Магистратура", "all": "🔎 Барлық деңгейді көрсету", "back_regions": "« Аймақ таңдауға оралу",
        "status": "Мәртебе", "source": "Дереккөз", "coverage": "Жабуы", "requirements": "Талаптар", "deadline": "Дедлайн", "site": "Ресми сайт",
        "open": "🟢 қабылдау ашық", "upcoming": "🟡 жақында ашылады",
        "lang_pick": "🌍 Выбери язык / Тілді таңда / Choose a language:", "lang_set": "✅ Тіл: Қазақша",
        "region_step": "2-қадам / 2: оқу деңгейін таңда 👇",
        "match_btn": "🎯 Маған сай", "match_more": "➡️ Тағы", "match_menu": "🏠 Басты мәзір",
        "match_title": "🎯 <b>Профиліңе сай келеді</b> ({total} ішінен {shown} көрсетілді):\n\n",
        "match_near": "\n\n🟡 <b>Сай келуге жақын</b> — бір көрсеткіш жетпейді:\n\n",
        "match_none": "😔 Әзірге профильге толық сай грант жоқ. Каталогты қара: /start",
        "match_no_profile": "🧑‍🎓 Алдымен /profile командасымен профильді толтыр — IELTS, GPA немесе бағытты көрсет, мен гранттарды саған сай іріктеймін.",
        "why_field": "бағыт бойынша", "why_ielts_ok": "IELTS сай", "why_gpa_ok": "GPA сай", "why_open": "қабылдау ашық",
        "gap_ielts": "IELTS {n} жетпейді", "gap_gpa": "GPA {n} жетпейді",
    },
    "en": {
        "start": ("🚀 <b>Your personal AI agent for grants and scholarships!</b>\n\n"
                  "Every morning I scan hundreds of universities and scholarship programs — from Bolashak to Erasmus Mundus — "
                  "and bring you only fresh opportunities before others find them.\n\n"
                  "🎯 Pick a direction with the buttons below and I’ll show the current catalog.\n"
                  "🌐 Or open the GrantHub website — the same features in a browser (/site).\n"
                  "💬 Or just ask me a question like a friend.\n"
                  "🧑‍🎓 Fill in /profile — I’ll consider your scores in my advice.\n"
                  "🌍 Language: /lang\n\nStep 1 of 2: choose where to study 👇"),
        "people_line": "👥 <b>{n}</b> people already use the bot and the site{delta}.", "people_delta": ", +{d} this week",
        "kz_btn": "🇰🇿 Grants in Kazakhstan", "abroad_btn": "🌍 Grants abroad", "site_btn": "🌐 Open the GrantHub website",
        "bachelor": "🎓 Bachelor's", "master": "🏛 Master's", "all": "🔎 Show all levels", "back_regions": "« Back to regions",
        "status": "Status", "source": "Source", "coverage": "Coverage", "requirements": "Requirements", "deadline": "Deadline", "site": "Official website",
        "open": "🟢 applications open", "upcoming": "🟡 opening soon",
        "lang_pick": "🌍 Выбери язык / Тілді таңда / Choose a language:", "lang_set": "✅ Language: English",
        "region_step": "Step 2 of 2: choose the degree level 👇",
        "match_btn": "🎯 For me", "match_more": "➡️ More", "match_menu": "🏠 Main menu",
        "match_title": "🎯 <b>Matched to your profile</b> (showing {shown} of {total}):\n\n",
        "match_near": "\n\n🟡 <b>Almost there</b> — one score short:\n\n",
        "match_none": "😔 No grant fully fits your profile yet. Browse the catalog: /start",
        "match_no_profile": "🧑‍🎓 Fill in your profile first with /profile — IELTS, GPA or field — and I will pick grants for you.",
        "why_field": "field matches", "why_ielts_ok": "IELTS fits", "why_gpa_ok": "GPA fits", "why_open": "applications open",
        "gap_ielts": "{n} IELTS short", "gap_gpa": "{n} GPA short",
    },
}
LANG_NAMES = {"ru": "🇷🇺 Русский", "kz": "🇰🇿 Қазақша", "en": "🇬🇧 English"}


def tr(lang: str, key: str) -> str:
    return T.get(lang, T["ru"]).get(key) or T["ru"].get(key, key)


def lang_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=n, callback_data=f"lang:{code}") for code, n in LANG_NAMES.items()]])


def grant_card_text(g: dict, lang: str = "ru") -> str:
    st = g.get("status") or ""
    status = tr(lang, st) if st in ("open", "upcoming") else None
    source = g.get("source")
    extra = ""
    if status:
        extra += f"📌 <b>{tr(lang, 'status')}:</b> {status}\n"
    if source:
        extra += f"🏛 <b>{tr(lang, 'source')}:</b> {esc(source)}\n"
    return (
        f"🎓 <b>{esc(g['name'])}</b> {flag_emoji(g.get('country_code')) or '🌍'}\n"
        f"{extra}"
        f"💰 <b>{tr(lang, 'coverage')}:</b> {esc(g['coverage'])}\n"
        f"📋 <b>{tr(lang, 'requirements')}:</b> {esc(g['requirements'])}\n"
        f"⏳ <b>{tr(lang, 'deadline')}:</b> {esc(g['deadline'])}\n"
        f"🔗 <a href=\"{html.escape(str(g['link']), quote=True)}\">{tr(lang, 'site')}</a>\n"
    )


async def check_rate_limit(user_id: int) -> Optional[str]:
    now = time.time()
    last = _last_question_time.get(user_id, 0)
    if now - last < QUESTION_COOLDOWN_SECONDS:
        return "⏳ Не так быстро — подожди пару секунд перед следующим вопросом."

    daily_count = await count_events_today(user_id, "ai_question")
    if daily_count >= QUESTION_DAILY_LIMIT:
        return "🚫 Ты достиг дневного лимита вопросов к ИИ-консультанту. Попробуй завтра."

    _last_question_time[user_id] = now
    return None


def skip_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить ⏭", callback_data=callback_data)]])


# --- Меню каталога ---

def site_button_row(lang: str = "ru") -> list:
    """Кнопка «Открыть сайт», если адрес публичный (Telegram не принимает localhost в URL-кнопках)."""
    if SITE_URL_IS_PUBLIC:
        return [InlineKeyboardButton(text=tr(lang, "site_btn"), url=f"{SITE_URL}/?from=bot")]
    return [InlineKeyboardButton(text=tr(lang, "site_btn"), callback_data="site:open")]


def get_region_menu(lang: str = "ru") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=tr(lang, "kz_btn"), callback_data="region:kz")],
        [InlineKeyboardButton(text=tr(lang, "abroad_btn"), callback_data="region:abroad")],
        [InlineKeyboardButton(text=tr(lang, "match_btn"), callback_data="match:0")],
        site_button_row(lang),
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def site_text() -> str:
    return (
        "🌐 <b>GrantHub — сайт с теми же функциями, что и у бота</b>\n\n"
        "Каталог грантов, поиск, избранное, профиль, ИИ-консультант и напоминания — всё в браузере, "
        "с крупными карточками и быстрым поиском.\n\n"
        f"👉 {esc(SITE_URL)}/?from=bot\n\n"
        f"Каталог: {esc(SITE_URL)}/app?from=bot#catalog\n"
        f"ИИ-консультант: {esc(SITE_URL)}/app?from=bot#chat"
    )


def get_degree_menu(region: str, lang: str = "ru") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=tr(lang, "bachelor"), callback_data=f"degree:{region}:bachelor")],
        [InlineKeyboardButton(text=tr(lang, "master"), callback_data=f"degree:{region}:master")],
        [InlineKeyboardButton(text=tr(lang, "all"), callback_data=f"degree:{region}:all")],
        [InlineKeyboardButton(text=tr(lang, "back_regions"), callback_data="menu:regions")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_page_keyboard(user_id: int, region: str, degree: str, grants: list, offset: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    alerts = await get_open_alert_ids(user_id)
    for g in grants:
        fav = await is_favorite(user_id, g["id"])
        label = ("✅ В избранном: " if fav else "⭐ В избранное: ") + g["name"][:24]
        action = "fav:remove" if fav else "fav:add"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"{action}:{g['id']}:{region}:{degree}:{offset}")])
        if g.get("status") == "upcoming":   # приём ещё не открыт — можно попросить сообщить об открытии
            on = g["id"] in alerts
            label = ("🔕 Не уведомлять: " if on else "🔔 Уведомить об открытии: ") + g["name"][:18]
            rows.append([InlineKeyboardButton(
                text=label, callback_data=f"alert:{'off' if on else 'on'}:{g['id']}:{region}:{degree}:{offset}")])

    if offset + len(grants) < total:
        rows.append([InlineKeyboardButton(text="➡️ Показать ещё", callback_data=f"page:{region}:{degree}:{offset + PAGE_SIZE}")])

    rows.append([InlineKeyboardButton(text="« Назад к выбору степени", callback_data=f"region:{region}")])
    rows.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:regions")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_grants_page(user_id: int, region: str, degree: str, offset: int):
    grants = await get_grants_filtered(category=region, degree=degree, limit=PAGE_SIZE, offset=offset)
    total = await count_grants_filtered(region, degree)

    lang = await get_user_lang(user_id)
    degree_label = tr(lang, degree).split(" ", 1)[-1] if degree in ("bachelor", "master", "all") else ""
    region_label = tr(lang, "kz_btn" if region == "kz" else "abroad_btn").split(" ", 1)[-1]

    if not grants:
        text = f"😔 Активных программ по фильтру <b>{region_label} / {degree_label}</b> пока нет."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="« Назад к выбору степени", callback_data=f"region:{region}")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:regions")],
        ])
        return text, keyboard

    shown_to = min(offset + len(grants), total)
    header = f"🎯 <b>Гранты ({region_label} • {degree_label}), показано {shown_to} из {total}:</b>\n\n"
    body = "\n---\n\n".join(grant_card_text(g, lang) for g in grants)
    keyboard = await build_page_keyboard(user_id, region, degree, grants, offset, total)
    return header + body, keyboard


# --- Базовые команды ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await add_user(message.from_user.id)
    await log_event(message.from_user.id, "start")
    lang = await get_user_lang(message.from_user.id)
    payload = (message.text or "").partition(" ")[2].strip()
    if payload.lower().startswith("link_"):          # ссылка с сайта: t.me/бот?start=link_КОД
        await _do_link(message, payload[5:])
        return
    await message.answer(tr(lang, "start") + "\n\n" + await people_line(lang), parse_mode="HTML", reply_markup=get_region_menu(lang))


async def people_line(lang: str) -> str:
    """«Нас уже N» — реальные цифры из базы, снимок обновляется раз в день."""
    try:
        u = await get_public_usage()
    except Exception as e:  # счётчик не должен ломать /start
        logging.warning(f"Счётчик пользователей недоступен: {e}")
        return ""
    delta = tr(lang, "people_delta").replace("{d}", str(u["week_delta"])) if u.get("week_delta") else ""
    return tr(lang, "people_line").replace("{n}", str(u["people"])).replace("{delta}", delta)


# --- Привязка сайта ---

_LINK_ERRORS = {
    "bad_code": "❌ Код не найден или уже использован. Получи новый на сайте в разделе «Профиль».",
    "expired": "⌛ Код устарел — он живёт 10 минут. Получи новый на сайте.",
    "same": "Это уже один и тот же аккаунт.",
    "web_linked": "К этому аккаунту сайта уже привязан другой Telegram.",
    "tg_taken": "К твоему Telegram уже привязан другой аккаунт сайта.",
}


async def _do_link(message: types.Message, code: str):
    result = await consume_link_code(code, "web", message.from_user.id)
    if not result["ok"]:
        await message.answer(_LINK_ERRORS.get(result["error"], "Не удалось привязать."))
        return
    await log_event(message.from_user.id, "telegram_linked", {"from": "bot"})
    await message.answer(
        "✅ <b>Сайт привязан!</b>\n\nИзбранное, профиль и подписки объединены. Напоминания о дедлайнах "
        "будут приходить сюда, а на сайте всё то же самое в браузере.\n\n/favorites — избранное, /match — подбор под профиль.",
        parse_mode="HTML",
    )


@dp.message(Command("link"))
async def cmd_link(message: types.Message):
    code = message.text.partition(" ")[2].strip()
    if code:
        await _do_link(message, code)
        return
    if await is_linked(message.from_user.id):
        await message.answer("✅ Сайт уже привязан к этому Telegram. Избранное и профиль общие.")
        return
    info = await create_link_code("tg", message.from_user.id)
    await message.answer(
        "🔗 <b>Привязка сайта GrantHub</b>\n\n"
        f"Открой на сайте раздел «Профиль» → «Telegram» и введи код:\n\n<code>{info['code']}</code>\n\n"
        f"Код действует 10 минут.\n👉 {esc(SITE_URL)}/app#profile\n\n"
        "Или наоборот: получи код на сайте и отправь мне <code>/link КОД</code>.",
        parse_mode="HTML", disable_web_page_preview=True,
    )


# --- Подбор под профиль ---

MATCH_PAGE = 3


def _match_card(item: dict, lang: str) -> str:
    g = item["grant"]
    good = [tr(lang, "why_" + w) for w in item["why"]]
    gaps = [tr(lang, "gap_" + k).replace("{n}", str(n)) for k, n in item["gaps"].items()]
    line = ""
    if good:
        line += "✅ " + " · ".join(good) + "\n"
    if gaps:
        line += "⚠️ " + " · ".join(gaps) + "\n"
    return line + grant_card_text(g, lang)


async def render_match_page(user_id: int, offset: int):
    lang = await get_user_lang(user_id)
    profile = await get_user_profile(user_id)
    if not has_profile(profile):
        return tr(lang, "match_no_profile"), None
    result = match_grants(await get_all_active_grants(), profile)
    matches, near = result["matches"], result["near"]
    if not matches and not near:
        return tr(lang, "match_none"), None
    page = matches[offset:offset + MATCH_PAGE]
    text = ""
    if page:
        text = tr(lang, "match_title").replace("{shown}", str(offset + len(page))).replace("{total}", str(len(matches)))
        text += "\n---\n\n".join(_match_card(i, lang) for i in page)
    if offset + MATCH_PAGE >= len(matches) and near:   # последняя страница — добавляем «почти подходят»
        text += tr(lang, "match_near") + "\n---\n\n".join(_match_card(i, lang) for i in near[:3])
    text = text.strip()
    rows = []
    for i in page:
        g = i["grant"]
        fav = await is_favorite(user_id, g["id"])
        label = ("✅ В избранном: " if fav else "⭐ В избранное: ") + g["name"][:24]
        rows.append([InlineKeyboardButton(text=label, callback_data=f"{'fav:remove' if fav else 'fav:add'}:{g['id']}:match:match:{offset}")])
    if offset + MATCH_PAGE < len(matches):
        rows.append([InlineKeyboardButton(text=tr(lang, "match_more"), callback_data=f"match:{offset + MATCH_PAGE}")])
    rows.append([InlineKeyboardButton(text=tr(lang, "match_menu"), callback_data="menu:regions")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(Command("match"))
async def cmd_match(message: types.Message):
    await log_event(message.from_user.id, "match_view")
    text, keyboard = await render_match_page(message.from_user.id, 0)
    chunks = split_message(text)
    for n, chunk in enumerate(chunks):
        await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True,
                             reply_markup=keyboard if n == len(chunks) - 1 else None)


@dp.callback_query(F.data.startswith("match:"))
async def cb_match(call: types.CallbackQuery):
    offset = int(call.data.split(":")[1])
    await log_event(call.from_user.id, "match_view")
    text, keyboard = await render_match_page(call.from_user.id, offset)
    try:
        await call.message.edit_text(text[:4000], parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    except Exception:
        await call.message.answer(text[:4000], parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    await call.answer()


@dp.message(Command("lang"))
async def cmd_lang(message: types.Message):
    await message.answer(tr("ru", "lang_pick"), reply_markup=lang_menu())


@dp.callback_query(F.data.startswith("lang:"))
async def cb_lang(call: types.CallbackQuery):
    lang = call.data.split(":")[1]
    if lang not in T:
        lang = "ru"
    await set_user_lang(call.from_user.id, lang)
    await call.answer()
    await call.message.edit_text(tr(lang, "lang_set"))
    await call.message.answer(tr(lang, "start"), parse_mode="HTML", reply_markup=get_region_menu(lang))


@dp.message(Command("site"))
async def cmd_site(message: types.Message):
    await log_event(message.from_user.id, "site_open")
    kb = InlineKeyboardMarkup(inline_keyboard=[site_button_row()]) if SITE_URL_IS_PUBLIC else None
    await message.answer(site_text(), parse_mode="HTML", disable_web_page_preview=False, reply_markup=kb)


@dp.callback_query(F.data == "site:open")
async def cb_site_open(call: types.CallbackQuery):
    await log_event(call.from_user.id, "site_open")
    await call.answer()
    await call.message.answer(site_text(), parse_mode="HTML")


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "ℹ️ <b>Что я умею:</b>\n\n"
        "/start — открыть меню поиска грантов\n"
        "/site — открыть сайт GrantHub (те же функции в браузере)\n"
        "/favorites — показать сохранённые гранты\n"
        "/profile — заполнить профиль (IELTS, GPA, направление) для персонализации\n"
        "/match — гранты, которые подходят под твой профиль\n"
        "/link — привязать сайт GrantHub: общее избранное и профиль\n"
        "/find &lt;слово&gt; — поиск грантов по ключевому слову\n"
        "/stop — отписаться от ежедневной рассылки новых грантов\n\n"
        "Также можешь просто написать мне вопрос текстом — я отвечу как консультант."
    )
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    await unsubscribe_user(message.from_user.id)
    await log_event(message.from_user.id, "unsubscribe")
    await message.answer(
        "Ты отписался от ежедневной рассылки новых грантов. "
        "Чтобы снова получать уведомления, просто отправь /start."
    )


# --- Профиль (FSM) ---

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message, state: FSMContext):
    await state.set_state(ProfileStates.waiting_ielts)
    await message.answer(
        "Давай настроим профиль — я буду учитывать это при рекомендациях.\n\n"
        "1️⃣ Укажи свой балл IELTS (например, 6.5):",
        reply_markup=skip_keyboard("profile_skip:ielts"),
    )


@dp.message(ProfileStates.waiting_ielts, F.text)
async def profile_ielts_input(message: types.Message, state: FSMContext):
    try:
        ielts = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Не похоже на число. Введи балл IELTS, например 6.5, или нажми «Пропустить».")
        return
    await state.update_data(ielts=ielts)
    await state.set_state(ProfileStates.waiting_gpa)
    await message.answer("2️⃣ Укажи свой GPA (например, 3.4):", reply_markup=skip_keyboard("profile_skip:gpa"))


@dp.callback_query(ProfileStates.waiting_ielts, F.data == "profile_skip:ielts")
async def profile_ielts_skip(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(ielts=None)
    await state.set_state(ProfileStates.waiting_gpa)
    await call.message.edit_text("2️⃣ Укажи свой GPA (например, 3.4):", reply_markup=skip_keyboard("profile_skip:gpa"))
    await call.answer()


@dp.message(ProfileStates.waiting_gpa, F.text)
async def profile_gpa_input(message: types.Message, state: FSMContext):
    try:
        gpa = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Не похоже на число. Введи GPA, например 3.4, или нажми «Пропустить».")
        return
    await state.update_data(gpa=gpa)
    await state.set_state(ProfileStates.waiting_field)
    await message.answer(
        "3️⃣ Какое направление тебя интересует? (например, IT, медицина, бизнес)",
        reply_markup=skip_keyboard("profile_skip:field"),
    )


@dp.callback_query(ProfileStates.waiting_gpa, F.data == "profile_skip:gpa")
async def profile_gpa_skip(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(gpa=None)
    await state.set_state(ProfileStates.waiting_field)
    await call.message.edit_text(
        "3️⃣ Какое направление тебя интересует? (например, IT, медицина, бизнес)",
        reply_markup=skip_keyboard("profile_skip:field"),
    )
    await call.answer()


async def _finish_profile(user_id: int, data: dict, answer_func):
    field = data.get("field_of_interest")
    await set_user_profile(user_id, ielts=data.get("ielts"), gpa=data.get("gpa"), field_of_interest=field)
    summary_lines = ["✅ Профиль сохранён!"]
    summary_lines.append(f"IELTS: {data.get('ielts') if data.get('ielts') else 'не указан'}")
    summary_lines.append(f"GPA: {data.get('gpa') if data.get('gpa') else 'не указан'}")
    summary_lines.append(f"Направление: {field if field else 'не указано'}")
    summary_lines.append("\nТеперь я буду учитывать это, когда буду отвечать на твои вопросы.\n🎯 /match — гранты, которые подходят под твой профиль.")
    await answer_func("\n".join(summary_lines))


@dp.message(ProfileStates.waiting_field, F.text)
async def profile_field_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data["field_of_interest"] = message.text.strip()[:120]
    await state.clear()
    await _finish_profile(message.from_user.id, data, message.answer)


@dp.callback_query(ProfileStates.waiting_field, F.data == "profile_skip:field")
async def profile_field_skip(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    data["field_of_interest"] = None
    await state.clear()
    await _finish_profile(call.from_user.id, data, call.message.answer)
    await call.answer()


# --- Поиск по ключевому слову ---

@dp.message(Command("find"))
async def cmd_find(message: types.Message):
    query = message.text.partition(" ")[2].strip()
    if not query:
        await message.answer("Использование: /find <ключевое слово>\nНапример: /find IT")
        return

    await log_event(message.from_user.id, "search", {"query": query})
    results = await search_grants(query, limit=5)
    if not results:
        await message.answer(f"По запросу «{esc(query)}» ничего не найдено.")
        return

    header = f"🔎 <b>Результаты по запросу «{esc(query)}»:</b>\n\n"
    lang = await get_user_lang(message.from_user.id)
    body = "\n---\n\n".join(grant_card_text(g, lang) for g in results)
    await message.answer(header + body, parse_mode="HTML", disable_web_page_preview=True)


# --- Каталог, избранное (как в предыдущих волнах) ---

@dp.message(Command("favorites"))
async def cmd_favorites(message: types.Message):
    favorites = await get_user_favorites(message.from_user.id)
    if not favorites:
        await message.answer("У тебя пока нет сохранённых грантов. Добавляй их кнопкой ⭐ в каталоге.")
        return

    lang = await get_user_lang(message.from_user.id)
    header = "⭐ <b>Твои сохранённые гранты:</b>\n\n"
    body = "\n---\n\n".join(grant_card_text(g, lang) for g in favorites)
    rows = [
        [InlineKeyboardButton(text=f"❌ Убрать: {g['name'][:24]}", callback_data=f"fav:remove:{g['id']}:menu:menu:0")]
        for g in favorites
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(header + body, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)


@dp.callback_query(F.data == "menu:regions")
async def back_to_regions(call: types.CallbackQuery):
    lang = await get_user_lang(call.from_user.id)
    await call.message.edit_text(tr(lang, "start"), parse_mode="HTML", reply_markup=get_region_menu(lang))
    await call.answer()


@dp.callback_query(F.data.startswith("region:"))
async def select_degree(call: types.CallbackQuery):
    region = call.data.split(":")[1]
    lang = await get_user_lang(call.from_user.id)
    region_title = tr(lang, "kz_btn") if region == "kz" else tr(lang, "abroad_btn")
    text = f"<b>{region_title}</b>\n\n{tr(lang, 'region_step')}"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_degree_menu(region, lang))
    await call.answer()


@dp.callback_query(F.data.startswith("degree:"))
async def show_filtered_grants(call: types.CallbackQuery):
    _, region, degree = call.data.split(":")
    await log_event(call.from_user.id, "browse_catalog", {"region": region, "degree": degree})
    text, keyboard = await render_grants_page(call.from_user.id, region, degree, offset=0)
    await call.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    await call.answer()


@dp.callback_query(F.data.startswith("page:"))
async def show_next_page(call: types.CallbackQuery):
    _, region, degree, offset = call.data.split(":")
    text, keyboard = await render_grants_page(call.from_user.id, region, degree, offset=int(offset))
    await call.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    await call.answer()


@dp.callback_query(F.data.startswith("fav:add:"))
async def handle_fav_add(call: types.CallbackQuery):
    _, _, grant_id, region, degree, offset = call.data.split(":")
    grant_id = int(grant_id)
    await add_favorite(call.from_user.id, grant_id)
    await log_event(call.from_user.id, "favorite_add", {"grant_id": grant_id})
    await call.answer("Добавлено в избранное ⭐")
    if region == "match":
        text, keyboard = await render_match_page(call.from_user.id, int(offset))
        await call.message.edit_text(text[:4000], parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    elif region != "menu":
        text, keyboard = await render_grants_page(call.from_user.id, region, degree, offset=int(offset))
        await call.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("fav:remove:"))
async def handle_fav_remove(call: types.CallbackQuery):
    _, _, grant_id, region, degree, offset = call.data.split(":")
    grant_id = int(grant_id)
    await remove_favorite(call.from_user.id, grant_id)
    await log_event(call.from_user.id, "favorite_remove", {"grant_id": grant_id})
    await call.answer("Убрано из избранного")
    if region == "menu":
        favorites = await get_user_favorites(call.from_user.id)
        if not favorites:
            await call.message.edit_text("У тебя больше нет сохранённых грантов.")
            return
        header = "⭐ <b>Твои сохранённые гранты:</b>\n\n"
        body = "\n---\n\n".join(grant_card_text(g) for g in favorites)
        rows = [
            [InlineKeyboardButton(text=f"❌ Убрать: {g['name'][:24]}", callback_data=f"fav:remove:{g['id']}:menu:menu:0")]
            for g in favorites
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        await call.message.edit_text(header + body, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    elif region == "match":
        text, keyboard = await render_match_page(call.from_user.id, int(offset))
        await call.message.edit_text(text[:4000], parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    else:
        text, keyboard = await render_grants_page(call.from_user.id, region, degree, offset=int(offset))
        await call.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("alert:"))
async def handle_open_alert(call: types.CallbackQuery):
    _, mode, grant_id, region, degree, offset = call.data.split(":")
    if mode == "on":
        await add_open_alert(call.from_user.id, int(grant_id))
        await call.answer("🔔 Напишу, когда откроется приём заявок")
    else:
        await remove_open_alert(call.from_user.id, int(grant_id))
        await call.answer("Уведомление отключено")
    text, keyboard = await render_grants_page(call.from_user.id, region, degree, offset=int(offset))
    await call.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)


# --- Фидбек на ответы ИИ ---

def get_feedback_keyboard(answer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👍", callback_data=f"fb:up:{answer_id}"),
        InlineKeyboardButton(text="👎", callback_data=f"fb:down:{answer_id}"),
    ]])


@dp.callback_query(F.data.startswith("fb:"))
async def handle_feedback(call: types.CallbackQuery):
    _, direction, answer_id = call.data.split(":")
    rating = 1 if direction == "up" else -1
    await set_answer_rating(int(answer_id), rating)
    await log_event(call.from_user.id, "ai_feedback", {"answer_id": int(answer_id), "rating": rating})
    await call.answer("Спасибо за фидбек! 🙌")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# --- Админ-команды ---

async def run_scan_cycle() -> tuple:
    """Полный цикл: снять истёкшие -> сканировать -> разослать. Возвращает (новых, снятых).

    Защищён замком: одновременно идёт не больше одного сканирования.
    """
    if _scan_lock.locked():
        raise RuntimeError("Сканирование уже идёт")
    async with _scan_lock:
        expired = await cleanup_expired_grants()
        if expired:
            logging.info(f"Удалено грантов с прошедшим дедлайном: {expired}")
        new_grants = await scan_and_save_grants()
        if new_grants:
            await broadcast_new_grants(new_grants)
        await send_open_alerts()   # сканер мог обнаружить, что приём открылся
        return new_grants, expired


async def _manual_scan_task(message: types.Message, status_msg: types.Message):
    try:
        new_grants, expired = await run_scan_cycle()
        await log_event(message.from_user.id, "manual_scan", {"found": len(new_grants), "expired": expired})
        await status_msg.edit_text(
            f"✅ Сканирование завершено.\nНовых программ: <b>{len(new_grants)}</b>\n"
            f"Снято с публикации (дедлайн прошёл): <b>{expired}</b>",
            parse_mode="HTML",
        )
    except RuntimeError as e:
        await status_msg.edit_text(f"⚠️ {e}.")
    except Exception as e:
        logging.error(f"Ошибка ручного сканирования: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Сканирование упало: {esc(e)}", parse_mode="HTML")


@dp.message(Command("scan"))
@admin_only
async def manual_scan(message: types.Message):
    msg = await message.answer("🤖 ИИ-сканер запущен в фоне, бот продолжает отвечать. Пришлю итог сюда.")
    asyncio.create_task(_manual_scan_task(message, msg))


@dp.message(Command("llm"))
@admin_only
async def cmd_llm(message: types.Message):
    """Какой провайдер ИИ используется и жива ли Ollama."""
    lines = [
        f"🧠 Основной провайдер: <b>{LLM_PROVIDER}</b>",
        f"🛟 Запасной: <b>{LLM_FALLBACK or 'нет'}</b>",
        f"💻 Ollama: сканер {esc(OLLAMA_MODEL)}, чат {esc(OLLAMA_CHAT_MODEL)}",
        f"☁️ Gemini модель: {esc(GEMINI_MODEL)}" if "gemini" in (LLM_PROVIDER, LLM_FALLBACK) else "☁️ Gemini: отключён",
        "",
        esc(await ollama_status()),
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("monitor"))
@admin_only
async def cmd_monitor(message: types.Message):
    """Сводка мониторинга: какие источники проверены, что нашли."""
    summary = await get_monitor_summary()
    kinds = {"university": "🏛 Университеты", "program": "🌍 Международные конкурсы", "broad": "🔎 Общие запросы"}
    lines = ["📡 <b>Мониторинг грантов</b>", ""]
    if not summary["by_kind"]:
        lines.append("Ещё ни одного сканирования не было. Запустите /scan.")
    for kind, label in kinds.items():
        row = summary["by_kind"].get(kind)
        if not row:
            continue
        last = (row["last"] or "—").replace("T", " ")
        lines.append(
            f"{label}: <b>{row['n']}</b> источников, проверено {esc(last)}\n"
            f"   найдено в последний раз: {row['found'] or 0}, новых: {row['new'] or 0}, "
            f"всего новых: {row['total'] or 0}, ошибок поиска: {row['errors'] or 0}"
        )
    st = summary["by_status"]
    if st:
        lines.append("")
        lines.append(
            f"Активных грантов: 🟢 открыт {st.get('open', 0)} · 🟡 скоро {st.get('upcoming', 0)} "
            f"· ⚪ не определён {st.get('unknown', 0)}"
        )
    if summary["top"]:
        lines.append("")
        lines.append("<b>Самые результативные источники:</b>")
        for r in summary["top"]:
            lines.append(f"• {esc(r['name'])} — {r['total_new']} новых")
    if ai_scanner.last_scan_stats:
        ls = ai_scanner.last_scan_stats
        lines.append("")
        lines.append(
            f"Последний прогон: {esc(ls['finished_at'].replace('T', ' '))}, {ls['elapsed_sec']}с, "
            f"сниппетов {ls['snippets']}, кандидатов {ls['candidates']}, прошло проверку {ls['valid']}, "
            f"новых {ls['new']}, подтверждено известных {ls['seen_again']}"
        )
    lines.append("")
    lines.append(f"Расписание: ежедневно в {esc(SCAN_HOURS_RAW)} ({esc(TIMEZONE)}).")
    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("deactivate"))
@admin_only
async def manual_deactivate(message: types.Message):
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /deactivate <grant_id>")
        return
    grant_id = int(parts[1])
    grant = await get_grant_by_id(grant_id)
    if not grant:
        await message.answer("Грант с таким ID не найден.")
        return
    await set_grant_active(grant_id, is_active=False)
    await message.answer(f"Грант «{grant['name']}» деактивирован.")


_RECENT_LABELS = {"web_visit": "зашёл на сайт", "register": "зарегистрировался", "login": "вошёл", "site_open": "открыл ссылку на сайт",
                  "start": "запустил бота", "telegram_linked": "привязал Telegram"}


@dp.message(Command("stats"))
@admin_only
async def cmd_stats(message: types.Message):
    summary = await get_events_summary(days=7)
    active_users = await get_active_users_count(days=7)
    a = await get_audience_stats()
    u, act, nw = a["users"], a["active"], a["new"]

    pub = await get_public_usage()
    lines = [
        "👥 <b>Аудитория</b>\n",
        f"Публичный счётчик «нас уже»: <b>{pub['people']}</b> (Telegram {pub['telegram']} · сайт {pub['site']}), снимок за {pub['date']}"
        + (f", +{pub['week_delta']} за неделю" if pub.get("week_delta") else ""),
        f"Всего людей: <b>{u['total']}</b> (Telegram {u['telegram']} · сайт {u['site']})",
        f"Активны сегодня: <b>{act['today']['total']}</b> (бот {act['today']['telegram']} · сайт {act['today']['site']})",
        f"Активны за 7 дней: <b>{act['7d']['total']}</b> (бот {act['7d']['telegram']} · сайт {act['7d']['site']})",
        f"Активны за 30 дней: <b>{act['30d']['total']}</b> (бот {act['30d']['telegram']} · сайт {act['30d']['site']})",
        f"Новых: сегодня {nw['today']} · за 7 дней {nw['7d']} · за 30 дней {nw['30d']}",
        f"Аккаунтов на сайте: {u['accounts']}, привязано к Telegram: {u['linked']}",
        f"Подписаны на рассылку: {u['subscribed']} · заполнили профиль: {u['with_profile']} · есть избранное: {u['with_favorites']}",
    ]
    f = a["funnel"]
    lines += [
        "\n🔀 <b>Воронка</b> (сегодня · 7 дней · 30 дней)\n",
        f"Заходили на сайт: {f['today']['visitors']} · {f['7d']['visitors']} · {f['30d']['visitors']}",
        f"Пришли на сайт из бота: {f['today']['from_bot']} · {f['7d']['from_bot']} · {f['30d']['from_bot']}",
        f"Нажали «сайт» в боте: {f['today']['site_open']} · {f['7d']['site_open']} · {f['30d']['site_open']}",
        f"Зарегистрировались: {f['today']['registered']} · {f['7d']['registered']} · {f['30d']['registered']}",
        f"Входили в аккаунт: {f['today']['logins']} · {f['7d']['logins']} · {f['30d']['logins']}",
        f"Запускали бота: {f['today']['bot_starts']} · {f['7d']['bot_starts']} · {f['30d']['bot_starts']}",
    ]
    if a["recent"]:
        lines.append("\n🕒 <b>Последние заходы</b>")
        for r in a["recent"][:10]:
            who = ("✉️ " + esc(r["email"])) if r["email"] else ("🤖 tg " if r["source"] == "telegram" else "🌐 web ") + str(r["user_id"])
            lines.append(f"{r['at'][5:16]} · {who} · {_RECENT_LABELS.get(r['event'], r['event'])}{' (из бота)' if r['from'] == 'bot' else ''}")
    spark = " ".join(f"{d['date'][8:]}:{d['active']}" for d in a["daily"][-7:])
    lines.append(f"\nАктивных по дням (UTC): {spark}\n")

    if not summary:
        lines.append("Событий за последние 7 дней пока нет.")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    lines += ["📊 <b>Статистика за 7 дней</b>\n", f"👥 Активных пользователей: {active_users}\n"]
    labels = {
        "start": "🚀 Запусков /start",
        "browse_catalog": "📂 Просмотров каталога",
        "favorite_add": "⭐ Добавлений в избранное",
        "favorite_remove": "❌ Удалений из избранного",
        "ai_question": "💬 Вопросов к ИИ",
        "ai_feedback": "👍 Оценок ответов ИИ",
        "unsubscribe": "🚫 Отписок",
        "manual_scan": "🔍 Ручных сканирований",
        "search": "🔎 Поисковых запросов",
        "profile_saved": "🧑‍🎓 Сохранений профиля",
        "match_view": "🎯 Просмотров подбора",
        "telegram_linked": "🔗 Привязок Telegram",
        "site_open": "🌐 Нажатий «сайт» в боте",
        "web_visit": "🖥 Заходов на сайт",
        "register": "📝 Регистраций на сайте",
        "login": "🔑 Входов на сайте",
        "alert_add": "🔔 Подписок на открытие",
    }
    for event_type, count in summary.items():
        label = labels.get(event_type, event_type)
        lines.append(f"{label}: {count}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# --- Ответы ИИ на текстовые сообщения ---

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_user_question(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return  # пользователь в процессе заполнения профиля — не мешаем

    limit_error = await check_rate_limit(message.from_user.id)
    if limit_error:
        await message.answer(limit_error)
        return

    await log_event(message.from_user.id, "ai_question")

    async def _keep_typing():
        while True:
            try:
                await bot.send_chat_action(chat_id=message.chat.id, action="typing")
            except Exception:
                pass
            await asyncio.sleep(4)

    typing_task = asyncio.create_task(_keep_typing())
    try:
        answer = await ask_gemini_consultant(message.text[:2000], user_id=message.from_user.id,
                                             lang=await get_user_lang(message.from_user.id))
    finally:
        typing_task.cancel()

    answer_id = await save_ai_answer(message.from_user.id, message.text[:2000], answer)
    keyboard = get_feedback_keyboard(answer_id)

    try:
        await message.answer(md_to_html(answer), parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard)
    except Exception:
        await message.answer(answer, disable_web_page_preview=True, reply_markup=keyboard)


# --- Рассылка, планировщик, напоминания ---

async def broadcast_new_grants(new_grants: list):
    if not new_grants:
        return
    users = await get_all_users()
    if not users:
        return

    cards = [grant_card_text(g) for g in new_grants[:30]]  # не спамим десятками карточек
    full_text = "⚡️ <b>ИИ нашел новые стипендиальные программы!</b>\n\n" + "\n---\n\n".join(cards)
    chunks = split_message(full_text)

    for user_id in users:
        try:
            for chunk in chunks:
                await bot.send_message(
                    chat_id=user_id,
                    text=chunk,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                await asyncio.sleep(0.05)
        except TelegramForbiddenError:
            pass
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            logging.error(f"Ошибка отправки пользователю {user_id}: {e}")


async def scheduled_grant_scan():
    try:
        new_grants, expired = await run_scan_cycle()
        logging.info(f"Плановое сканирование завершено: новых {len(new_grants)}, снято истёкших {expired}")
        if ADMIN_ID:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"🗓 Плановое сканирование: новых <b>{len(new_grants)}</b>, снято истёкших <b>{expired}</b>.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    except Exception as e:
        logging.error(f"Ошибка в плановом сканировании грантов: {e}", exc_info=True)


async def send_deadline_reminders():
    """Раз в день проверяет избранные гранты с дедлайном за 7/3/1 день и напоминает."""
    try:
        favorites = await get_favorites_with_deadlines()
        today = datetime.date.today()

        for row in favorites:
            try:
                deadline = datetime.date.fromisoformat(row["deadline_date"])
            except (ValueError, TypeError):
                continue

            days_left = (deadline - today).days
            if days_left not in (7, 3, 1):
                continue

            can_send = await mark_reminder_sent(row["user_id"], row["grant_id"], days_left)
            if not can_send:
                continue

            text = (
                f"⏰ <b>Напоминание о дедлайне!</b>\n\n"
                f"До подачи заявки на «{esc(row['name'])}» осталось <b>{days_left} дн.</b>\n"
                f"🔗 {esc(row['link'])}"
            )
            try:
                await bot.send_message(row["user_id"], text, parse_mode="HTML", disable_web_page_preview=True)
            except TelegramForbiddenError:
                pass
            except Exception as e:
                logging.error(f"Ошибка отправки напоминания пользователю {row['user_id']}: {e}")

        logging.info("Проверка напоминаний о дедлайнах завершена.")
    except Exception as e:
        logging.error(f"Ошибка в задаче напоминаний о дедлайнах: {e}", exc_info=True)


async def send_open_alerts():
    """Сообщает подписчикам «Уведомить об открытии», что приём заявок начался. Каждому — один раз."""
    try:
        for row in await get_opened_alerts(only_unsent=True):
            if row["user_id"] >= 10**12:   # посетитель сайта без Telegram — увидит плашку на сайте
                continue
            text = (
                f"🔔 <b>Приём заявок открыт!</b>\n\n"
                f"Началась подача на «{esc(row['name'])}»"
                + (f", дедлайн {esc(row['deadline_date'])}" if row["deadline_date"] else "")
                + f".\n🔗 {esc(row['link'])}"
            )
            try:
                await bot.send_message(row["user_id"], text, parse_mode="HTML", disable_web_page_preview=True)
            except TelegramForbiddenError:
                pass
            except Exception as e:
                logging.error(f"Ошибка отправки уведомления об открытии пользователю {row['user_id']}: {e}")
                continue
            await mark_alert_notified(row["alert_id"])
    except Exception as e:
        logging.error(f"Ошибка в задаче уведомлений об открытии приёма: {e}", exc_info=True)


async def backup_and_send():
    """Копия базы перед очисткой; файл уходит администратору в Telegram — это и есть внешний бэкап."""
    try:
        path = await backup_database()
        logging.info(f"Резервная копия базы: {path}")
        if ADMIN_ID:
            await bot.send_document(ADMIN_ID, FSInputFile(path), caption=f"🗄 Резервная копия базы {path.name}")
    except Exception as e:
        logging.error(f"Ошибка резервной копии: {e}", exc_info=True)


async def weekly_link_check():
    """Раз в неделю открывает страницы всех найденных сканером грантов; мёртвые ссылки уводят грант в архив."""
    try:
        summary = await recheck_links()
        if ADMIN_ID and summary["archived"]:
            await bot.send_message(ADMIN_ID, f"🔗 Проверка ссылок: не открылось {summary['failed']} из {summary['checked']}, "
                                             f"снято с публикации {summary['archived']}.")
    except Exception as e:
        logging.error(f"Ошибка проверки ссылок: {e}", exc_info=True)


async def daily_cleanup():
    """Ежедневно: копия базы, удалить истёкшие гранты, перенести ежегодные, пересчитать статусы, разослать уведомления."""
    await backup_and_send()
    try:
        deleted = await cleanup_expired_grants()
        logging.info(f"Ежедневная очистка: удалено грантов с прошедшим дедлайном: {deleted}")
    except Exception as e:
        logging.error(f"Ошибка ежедневной очистки: {e}", exc_info=True)
    await send_open_alerts()


# --- Глобальный обработчик ошибок ---

@dp.error()
async def global_error_handler(event: ErrorEvent):
    logging.error(f"Необработанная ошибка: {event.exception}", exc_info=event.exception)

    update = event.update
    chat_id = None
    if update.message:
        chat_id = update.message.chat.id
    elif update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat.id

    if chat_id:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="⚠️ Что-то пошло не так. Мы уже знаем об этом. Попробуй ещё раз через пару секунд.",
            )
        except Exception:
            pass

    return True


async def setup_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Открыть меню поиска грантов"),
        BotCommand(command="site", description="Открыть сайт GrantHub"),
        BotCommand(command="lang", description="Язык / Тіл / Language"),
        BotCommand(command="favorites", description="Мои сохранённые гранты"),
        BotCommand(command="profile", description="Настроить профиль"),
        BotCommand(command="match", description="Гранты под мой профиль"),
        BotCommand(command="link", description="Привязать сайт GrantHub"),
        BotCommand(command="find", description="Поиск грантов по слову"),
        BotCommand(command="stop", description="Отписаться от рассылки"),
        BotCommand(command="help", description="Что я умею"),
    ])


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOGS_DIR / "bot.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    # Поисковая библиотека и http-клиенты пишут по строке на каждый запрос — оставляем только предупреждения
    for noisy in ("httpx", "httpcore", "ddgs", "primp", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    await init_db()
    await setup_commands()
    asyncio.create_task(warm_up_llm())  # грузим модель заранее, не блокируя старт бота

    for h in SCAN_HOURS:
        scheduler.add_job(
            scheduled_grant_scan,
            "cron",
            hour=h,
            minute=0,
            id=f"grant_scan_{h:02d}",
            replace_existing=True,
        )
    scheduler.add_job(
        send_deadline_reminders,
        "cron",
        hour=9,
        minute=0,
        id="daily_reminders",
        replace_existing=True,
    )
    scheduler.add_job(daily_cleanup, "cron", hour=0, minute=1, timezone="UTC", id="daily_cleanup", replace_existing=True)
    scheduler.add_job(weekly_link_check, "cron", day_of_week="mon", hour=3, minute=0, timezone="UTC", id="weekly_links", replace_existing=True)
    scheduler.add_job(refresh_usage_snapshot, "cron", hour=0, minute=5, timezone="UTC", id="usage_snapshot", replace_existing=True)
    scheduler.start()
    asyncio.create_task(daily_cleanup())  # и сразу при старте: бот мог быть выключен в полночь

    print("База данных готова. Сканер и бот работают...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())