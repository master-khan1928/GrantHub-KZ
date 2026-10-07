import json
import logging
import os
import re
import random
import asyncio
import datetime
from pathlib import Path
from typing import Optional
import aiohttp
import aiosqlite
from dotenv import load_dotenv
try:
    from ddgs import DDGS  # актуальный пакет
except ImportError:  # pragma: no cover
    from duckduckgo_search import DDGS  # устаревший, оставлен как запасной
try:  # Gemini нужен только если он указан в LLM_PROVIDER/LLM_FALLBACK
    from google import genai
    from google.genai import types
except ImportError:  # пакет google-genai не установлен — работаем только с Ollama
    genai = None
    types = None
from core.database import (
    DB_NAME, DEGREES, SOURCE_SCANNER, clean_text, get_all_grants_light, find_duplicate_grant, get_user_profile,
    drop_tombstone, get_links_to_check, get_tombstones, grant_hash, guess_funding, link_domain, log_scan_run,
    normalize_link, record_link_check, record_monitor_result, status_by_dates, sweep_stale_grants,
    upsert_scanned_grant,
)
from core.dates import date_in_text, page_text
from core.geo import PROGRAM_COUNTRY, resolve_location

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# Провайдеры LLM: gemini (облако) и ollama (локально).
#   LLM_PROVIDER  — основной: "ollama" (по умолчанию, локально, без квот) или "gemini"
#   LLM_FALLBACK  — запасной, если основной упал (квота, сеть, Ollama не запущена)
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
LLM_FALLBACK = os.getenv("LLM_FALLBACK", "").strip().lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_RETRIES = 3
GEMINI_RETRY_DELAYS = (5, 20, 45)  # секунды между попытками при 429/503

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")            # модель сканера (извлечение JSON)
# Модель чата: без режима «размышлений» — отвечает сразу и быстро. qwen3 иногда думает вслух даже с think=false.
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "gemma3:4b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))      # локальная модель может думать долго
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))     # окно контекста для сканера; 16384 не влезает в 6 ГБ VRAM
CHAT_NUM_CTX = int(os.getenv("CHAT_NUM_CTX", "6144"))          # окно для чата — меньше контекст, быстрее ответ
CHAT_NUM_PREDICT = int(os.getenv("CHAT_NUM_PREDICT", "700"))   # лимит длины ответа консультанта в токенах
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "60m")      # держим модель в памяти, чтобы не грузить её заново
# Семейства с режимом «размышления»: отключаем, иначе ответ идёт минутами
_OLLAMA_THINKING_FAMILIES = ("qwen3", "deepseek-r1", "gpt-oss", "magistral")

# Groq — облачный API (OpenAI-совместимый), быстрый и с бесплатным тарифом. Для сервера без видеокарты.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_URL = os.getenv("GROQ_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-120b")       # чат: умная модель
GROQ_SCAN_MODEL = os.getenv("GROQ_SCAN_MODEL", "openai/gpt-oss-20b")        # сканер: дешёвая, большие лимиты
GROQ_RETRIES = 4

_VALID_PROVIDERS = ("gemini", "ollama", "groq")
if LLM_PROVIDER not in _VALID_PROVIDERS:
    raise RuntimeError(f"LLM_PROVIDER={LLM_PROVIDER!r}, допустимо: {_VALID_PROVIDERS}")
if LLM_FALLBACK and LLM_FALLBACK not in _VALID_PROVIDERS:
    raise RuntimeError(f"LLM_FALLBACK={LLM_FALLBACK!r}, допустимо: {_VALID_PROVIDERS}")
_GEMINI_ENABLED = "gemini" in (LLM_PROVIDER, LLM_FALLBACK)
if _GEMINI_ENABLED and not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY не найден. Проверь .env файл или переключи LLM_PROVIDER=ollama.")
if "groq" in (LLM_PROVIDER, LLM_FALLBACK) and not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY не найден. Возьмите ключ на console.groq.com и добавьте в .env.")
if _GEMINI_ENABLED and genai is None:
    raise RuntimeError("Пакет google-genai не установлен (pip install google-genai) или уберите gemini из LLM_PROVIDER/LLM_FALLBACK.")

client = genai.Client(api_key=GEMINI_API_KEY) if (_GEMINI_ENABLED and GEMINI_API_KEY) else None


def _is_retryable_gemini_error(e: Exception) -> bool:
    text = str(e)
    return any(marker in text for marker in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "overloaded"))


async def _gemini_generate(system: str, user: str, temperature: float, json_mode: bool, **_ignored) -> str:
    """Вызов Gemini с повторами при перегрузке/квоте. Бросает последнее исключение."""
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json" if json_mode else None,
    )
    last_exc = None
    for attempt in range(GEMINI_RETRIES):
        try:
            response = await client.aio.models.generate_content(
                model=GEMINI_MODEL, contents=user, config=config
            )
            return response.text or ""
        except Exception as e:
            last_exc = e
            if not _is_retryable_gemini_error(e) or attempt == GEMINI_RETRIES - 1:
                raise
            delay = GEMINI_RETRY_DELAYS[min(attempt, len(GEMINI_RETRY_DELAYS) - 1)]
            logging.warning(f"Gemini перегружен/квота (попытка {attempt + 1}/{GEMINI_RETRIES}), жду {delay}с: {e}")
            await asyncio.sleep(delay)
    raise last_exc


def _ollama_payload(system: str, user: str, temperature: float, json_mode: bool,
                    num_ctx: int = None, num_predict: int = None, stream: bool = False, model: str = None) -> dict:
    model = model or OLLAMA_MODEL
    payload = {
        "model": model,
        "stream": stream,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": temperature, "num_ctx": num_ctx or OLLAMA_NUM_CTX},
    }
    if num_predict:
        payload["options"]["num_predict"] = num_predict
    if json_mode:
        payload["format"] = "json"
    if any(fam in model.lower() for fam in _OLLAMA_THINKING_FAMILIES):
        payload["think"] = False
        # qwen3 не всегда слушается think=false — дублируем «мягким» переключателем в промпте
        if "qwen3" in model.lower():
            payload["messages"][0]["content"] = system + "\n/no_think"
            payload["messages"][1]["content"] = user + "\n/no_think"
    return payload


def _strip_thinking(content: str) -> str:
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
    if "</think>" in content:
        content = content.rsplit("</think>", 1)[1]
    return content.strip()


async def _ollama_generate(system: str, user: str, temperature: float, json_mode: bool,
                           num_ctx: int = None, num_predict: int = None, model: str = None) -> str:
    """Вызов локальной Ollama через /api/chat."""
    payload = _ollama_payload(system, user, temperature, json_mode, num_ctx, num_predict, model=model)
    timeout = aiohttp.ClientTimeout(total=OLLAMA_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(f"{OLLAMA_URL}/api/chat", json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Ollama HTTP {resp.status}: {body[:300]}")
            data = await resp.json()
    return _strip_thinking((data.get("message") or {}).get("content") or "")


async def _ollama_stream(system: str, user: str, temperature: float,
                         num_ctx: int = None, num_predict: int = None, model: str = None):
    """Потоковый вызов Ollama: отдаёт кусочки текста по мере генерации."""
    payload = _ollama_payload(system, user, temperature, False, num_ctx, num_predict, stream=True, model=model)
    timeout = aiohttp.ClientTimeout(total=OLLAMA_TIMEOUT, sock_read=OLLAMA_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(f"{OLLAMA_URL}/api/chat", json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Ollama HTTP {resp.status}: {body[:300]}")
            async for line in resp.content:
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                piece = (chunk.get("message") or {}).get("content") or ""
                if piece:
                    yield piece
                if chunk.get("done"):
                    break


async def warm_up_llm():
    """Прогрев: загружает модель в память заранее, чтобы первый ответ не ждал загрузки."""
    if LLM_PROVIDER != "ollama":
        return
    try:
        payload = {"model": OLLAMA_CHAT_MODEL, "keep_alive": OLLAMA_KEEP_ALIVE, "messages": [], "stream": False,
                   "options": {"num_ctx": CHAT_NUM_CTX}}
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{OLLAMA_URL}/api/chat", json=payload) as resp:
                await resp.read()
        logging.info(f"Ollama: модель чата {OLLAMA_CHAT_MODEL} загружена в память (keep_alive={OLLAMA_KEEP_ALIVE}).")
    except Exception as e:
        logging.warning(f"Ollama: не удалось прогреть модель: {e}")


async def ollama_status() -> str:
    """Короткая диагностика для админа: доступен ли сервер и скачана ли модель."""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{OLLAMA_URL}/api/tags") as resp:
                data = await resp.json()
        models = [m.get("name", "") for m in data.get("models", [])]
        def mark(name):
            have = any(m == name or m.split(":")[0] == name.split(":")[0] for m in models)
            return "✅ есть" if have else f"❌ не скачана (ollama pull {name})"
        return (f"Ollama {OLLAMA_URL}: сервер отвечает. Сканер {OLLAMA_MODEL} — {mark(OLLAMA_MODEL)}; "
                f"чат {OLLAMA_CHAT_MODEL} — {mark(OLLAMA_CHAT_MODEL)}. Установлено: {', '.join(models) or 'ничего'}")
    except Exception as e:
        return f"Ollama {OLLAMA_URL}: недоступна ({e})"


def _groq_body(system: str, user: str, temperature: float, json_mode: bool, num_predict: int, model: str, stream: bool) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "stream": stream,
    }
    if num_predict:
        body["max_tokens"] = num_predict
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if "gpt-oss" in model:
        body["reasoning_effort"] = "low"   # быстрее: минимум скрытых размышлений
    return body


def _groq_headers() -> dict:
    return {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}


async def _groq_retry_delay(resp) -> float:
    """429/5xx: ждём столько, сколько просит сервер (retry-after), иначе растущую паузу."""
    ra = resp.headers.get("retry-after")
    try:
        return max(1.0, float(ra)) + 0.5
    except (TypeError, ValueError):
        return 0.0


async def _groq_generate(system: str, user: str, temperature: float, json_mode: bool,
                         num_ctx: int = None, num_predict: int = None, model: str = None, **_ignored) -> str:
    """Вызов Groq (OpenAI-совместимый chat/completions) с повторами при лимитах."""
    model = GROQ_SCAN_MODEL if json_mode else GROQ_CHAT_MODEL
    body = _groq_body(system, user, temperature, json_mode, num_predict, model, stream=False)
    timeout = aiohttp.ClientTimeout(total=120)
    last_exc = None
    for attempt in range(GROQ_RETRIES):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(GROQ_URL, json=body, headers=_groq_headers()) as resp:
                    if resp.status in (429, 500, 502, 503):
                        delay = await _groq_retry_delay(resp) or (5 * (attempt + 1))
                        text = (await resp.text())[:200]
                        logging.warning(f"Groq {resp.status} (попытка {attempt + 1}/{GROQ_RETRIES}), жду {delay:.0f}с: {text}")
                        last_exc = RuntimeError(f"Groq HTTP {resp.status}: {text}")
                        await asyncio.sleep(delay)
                        continue
                    if resp.status == 400 and json_mode:
                        # JSON-режим Groq отвергает ответ, если модель ничего не нашла и вернула «[]» —
                        # для нас это штатный результат «кандидатов нет», а не ошибка батча
                        err = await resp.text()
                        if "json_validate_failed" in err:
                            fg = re.search(r'"failed_generation"\s*:\s*"((?:[^"\\]|\\.)*)"', err)
                            raw = (fg.group(1) if fg else "").encode().decode("unicode_escape", "ignore").strip()
                            if raw in ("", "[]", "{}", '{"grants": []}', '{"grants":[]}'):
                                return "[]"
                            logging.warning(f"Groq отверг JSON ответа (json_validate_failed): {raw[:160]}")
                            return "[]"
                        raise RuntimeError(f"Groq HTTP 400: {err[:300]}")
                    if resp.status != 200:
                        raise RuntimeError(f"Groq HTTP {resp.status}: {(await resp.text())[:300]}")
                    data = await resp.json()
            return (data["choices"][0]["message"].get("content") or "").strip()
        except aiohttp.ClientError as e:
            last_exc = e
            await asyncio.sleep(3 * (attempt + 1))
    raise last_exc or RuntimeError("Groq: нет ответа")


async def _groq_stream(system: str, user: str, temperature: float, num_predict: int = None, model: str = None):
    """Потоковый вызов Groq (SSE)."""
    model = GROQ_CHAT_MODEL
    body = _groq_body(system, user, temperature, False, num_predict, model, stream=True)
    timeout = aiohttp.ClientTimeout(total=120, sock_read=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(GROQ_URL, json=body, headers=_groq_headers()) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Groq HTTP {resp.status}: {(await resp.text())[:300]}")
            async for raw in resp.content:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    yield piece


_PROVIDERS = {"gemini": _gemini_generate, "ollama": _ollama_generate, "groq": _groq_generate}


async def llm_generate(system: str, user: str, temperature: float = 0.4, json_mode: bool = False,
                       num_ctx: int = None, num_predict: int = None, model: str = None) -> str:
    """Единая точка вызова LLM: основной провайдер, затем запасной. Бросает последнее исключение."""
    chain = [LLM_PROVIDER]
    if LLM_FALLBACK and LLM_FALLBACK != LLM_PROVIDER:
        chain.append(LLM_FALLBACK)
    last_exc = None
    for name in chain:
        try:
            return await _PROVIDERS[name](system, user, temperature, json_mode, num_ctx=num_ctx, num_predict=num_predict, model=model)
        except Exception as e:
            last_exc = e
            if name != chain[-1]:
                logging.warning(f"LLM {name} не ответил ({e}); переключаюсь на {chain[-1]}")
    raise last_exc


async def llm_stream(system: str, user: str, temperature: float = 0.4,
                     num_ctx: int = None, num_predict: int = None, model: str = None):
    """Потоковая генерация: для Ollama отдаёт текст по кусочкам, иначе — весь ответ одним куском."""
    streamers = {"ollama": lambda: _ollama_stream(system, user, temperature, num_ctx, num_predict, model=model),
                 "groq": lambda: _groq_stream(system, user, temperature, num_predict)}
    if LLM_PROVIDER in streamers:
        try:
            async for piece in streamers[LLM_PROVIDER]():
                yield piece
            return
        except Exception as e:
            if not LLM_FALLBACK or LLM_FALLBACK == LLM_PROVIDER:
                raise
            logging.warning(f"LLM {LLM_PROVIDER} (stream) не ответил ({e}); переключаюсь на {LLM_FALLBACK}")
    yield await llm_generate(system, user, temperature, False, num_ctx=num_ctx, num_predict=num_predict, model=model)


def _parse_grants_json(text: str) -> list:
    """Ответ модели -> список словарей. Локальные модели любят оборачивать массив в объект."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "grants" in data and isinstance(data["grants"], list):
            return data["grants"]
        for value in data.values():
            if isinstance(value, list):
                return value
        if data.get("name"):
            return [data]
    return []

SYSTEM_PROMPT_CHAT = """
Ты — вежливый и умный ментор по поступлению, грантам и стипендиям (Казахстан и зарубежье).
Твоя задача — отвечать на любые вопросы пользователя о поступлении, баллах ЕНТ, IELTS, GPA, мотивационных письмах и доступных программах.

Если пользователь просто поздоровался (например, "привет"), поздоровайся в ответ и кратко предложи свою помощь в поиске гранта.
Отвечай структурированно, по пунктам, выделяй важное жирным шрифтом.
Если у тебя есть данные о профиле пользователя (IELTS, GPA, интересующее направление) — обязательно учитывай их и рекомендуй то, что реально подходит под его уровень.
"""

DEADLINE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

PROMPT_EXTRACT_TEMPLATE = """
Ты — эксперт по образовательным грантам и стипендиям. Ты мониторишь университеты и международные
грантовые конкурсы и должен выявлять ТОЛЬКО реальные, действующие программы.
Сегодняшняя дата: {today}.

Перед каждым фрагментом текста стоит строка "Источник: ..." — это университет или программа, по которой шёл поиск.

Правила:
- Бери только стипендии/гранты/конкурсы, у которых приём заявок открыт сейчас или откроется в будущем.
- Если по тексту видно, что дедлайн уже прошёл (раньше {today}) или конкурс закрыт — пропусти.
- Не выдумывай ссылки: "link" только из текста, лучше всего URL официальной страницы программы.
- Общие статьи-подборки ("топ-10 стипендий") без конкретной программы — пропускай.
- Название пиши так, чтобы было понятно, что это и где: "Программа — Университет/Страна".

Извлеки в строгий JSON:
[
  {{
    "source": "значение из строки Источник для этого фрагмента",
    "category": "kz" (учёба в Казахстане) или "abroad" (учёба за рубежом),
    "country_code": "двухбуквенный код ISO страны, ГДЕ ПРОХОДИТ УЧЁБА (KZ, US, DE, GB...). Если стран несколько — null",
    "provider_country": "код ISO страны или организации, которая ВЫДАЁТ грант (для «Болашак» — KZ). Если неясно — null",
    "degree": "bachelor", "master", "phd", "language" (языковые курсы) или "all",
    "funding": "full" (полное покрытие), "partial" (частичное, скидка) или "unknown",
    "name": "Название и страна",
    "coverage": "Что покрывают (обучение, стипендия, проживание, перелёт)",
    "requirements": "Требования (гражданство, GPA, IELTS, возраст и т.п.)",
    "deadline": "Дедлайн в свободном виде, как написано в источнике",
    "deadline_date": "Дедлайн в формате YYYY-MM-DD, твоя лучшая оценка ближайшей будущей даты подачи заявки. Если оценить невозможно — null.",
    "application_start_date": "Дата открытия приёма документов в формате YYYY-MM-DD, если она указана. Иначе null.",
    "is_ongoing": true, если заявки принимают круглый год и дедлайна нет; иначе false,
    "recurrence_period": "yearly", если программа проводится каждый год; иначе null,
    "status": "open" (приём открыт), "upcoming" (откроется позже) или "unknown",
    "link": "Ссылка"
  }}
]
Если в тексте нет реальных стипендий/грантов — верни пустой массив [].
Допустимо вернуть объект {{"grants": [...]}} с тем же содержимым. Никакого текста вне JSON.
"""

# --- Годы для запросов: текущий и следующий (приём на 2027 идёт уже в 2026) ---
_THIS_YEAR = datetime.date.today().year
YEARS = f"{_THIS_YEAR} {_THIS_YEAR + 1}"

# --- Широкие запросы ---
BROAD_QUERIES = [
    f"scholarships for kazakhstan students deadline {YEARS}",
    "актуальные международные гранты магистратура бакалавриат приём заявок",
    f"fully funded scholarships bachelor {YEARS} applications open",
    f"fully funded scholarships master's degree {YEARS} applications open",
    f"гранты для студентов из Казахстана за рубежом {YEARS}",
    f"study abroad scholarship application deadline {YEARS}",
    f"government scholarship international students call for applications {YEARS}",
    f"конкурс на обучение за рубежом стипендия {YEARS} подача заявок",
]

# --- Международные грантовые программы и конкурсы (раздают гранты на учёбу за рубежом) ---
PROGRAMS = [
    # Казахстан / СНГ
    "Bolashak scholarship", "Yessenov Foundation scholarship", "Open Doors Russian Scholarship Project",
    "Abai-Verne scholarship France Kazakhstan",
    # США
    "Fulbright Foreign Student Program", "Hubert H. Humphrey Fellowship", "Global UGRAD program",
    "Knight-Hennessy Scholars", "Schwarzman Scholars", "Yenching Academy scholarship",
    "Mastercard Foundation Scholars Program", "Aga Khan Foundation International Scholarship",
    # Великобритания / Ирландия
    "Chevening scholarship", "Commonwealth Scholarship", "Rhodes Scholarship", "Gates Cambridge scholarship",
    "Clarendon Scholarship Oxford", "Weidenfeld-Hoffmann Scholarships", "Government of Ireland International Education Scholarship",
    # Европа
    "DAAD scholarship", "Erasmus Mundus Joint Master scholarship", "Eiffel Excellence Scholarship",
    "Swedish Institute Scholarships for Global Professionals", "Stipendium Hungaricum", "Swiss Government Excellence Scholarships",
    "Holland Scholarship", "Orange Tulip Scholarship", "Italian Government Scholarship foreign students",
    "Turkiye Burslari scholarship", "Romanian Government Scholarship", "Visegrad Scholarship",
    "Finland Scholarship master", "Danish Government Scholarship", "Vienna Biocenter PhD program",
    "Polish NAWA scholarship", "Czech Government Scholarship", "Estonian Government scholarship",
    "Konrad Adenauer Stiftung scholarship", "Heinrich Boll Foundation scholarship", "Friedrich Ebert Stiftung scholarship",
    # Азия / Океания
    "MEXT scholarship Japan", "Global Korea Scholarship GKS", "Chinese Government Scholarship CSC",
    "Taiwan ICDF scholarship", "Singapore International Graduate Award", "ASEAN scholarship",
    "Brunei Darussalam Government Scholarship", "Australia Awards scholarship", "Manaaki New Zealand Scholarship",
    "Hong Kong PhD Fellowship Scheme", "Malaysia International Scholarship", "KAUST Fellowship",
    "Qatar University international scholarship", "Kuwait Government scholarship", "Vanier Canada Graduate Scholarships",
    "Lester B. Pearson International Scholarship", "Emirates Diplomatic Academy scholarship",
    # Фонды и организации
    "Rotary Peace Fellowship", "OPEC Fund scholarship", "World Bank scholarship JJ/WBGSP", "Joint Japan World Bank scholarship",
    "Islamic Development Bank scholarship", "Wells Mountain Initiative scholarship", "Civil Society Leadership Awards",
    "EU4Youth scholarship", "Central European University scholarship", "American University of Central Asia scholarship",
    "OSCE Academy scholarship", "Nazarbayev University grant admission", "Ministry of Education Kazakhstan state grant",
]

# --- 344 университетов для точечного поиска ---
UNIVERSITIES = [
    "Harvard University", "Stanford University", "Massachusetts Institute of Technology",
    "University of Oxford", "University of Cambridge", "California Institute of Technology",
    "Princeton University", "Yale University", "University of Chicago", "Imperial College London",
    "University of Pennsylvania", "Columbia University", "Cornell University",
    "University of California, Berkeley", "University of California, Los Angeles",
    "University of Michigan", "Johns Hopkins University", "Duke University",
    "Northwestern University", "University of Toronto", "McGill University",
    "University of British Columbia", "University of Melbourne", "University of Sydney",
    "Australian National University", "University of Edinburgh", "King's College London",
    "London School of Economics", "University College London", "University of Manchester",
    "ETH Zurich", "EPFL", "University of Zurich", "Sciences Po", "Sorbonne University",
    "Ludwig Maximilian University of Munich", "Technical University of Munich",
    "Heidelberg University", "Humboldt University of Berlin", "Free University of Berlin",
    "University of Amsterdam", "Delft University of Technology", "Leiden University",
    "Utrecht University", "KU Leuven", "University of Copenhagen", "Karolinska Institute",
    "Uppsala University", "Lund University", "University of Helsinki", "University of Oslo",
    "University of Vienna", "University of Warsaw", "Charles University", "University of Bologna",
    "Sapienza University of Rome", "Politecnico di Milano", "Universidad Autonoma de Madrid",
    "Universidad Complutense de Madrid", "University of Barcelona", "Pompeu Fabra University",
    "National University of Singapore", "Nanyang Technological University", "University of Hong Kong",
    "Hong Kong University of Science and Technology", "Chinese University of Hong Kong",
    "Peking University", "Tsinghua University", "Fudan University", "Shanghai Jiao Tong University",
    "Seoul National University", "KAIST", "Yonsei University", "Korea University",
    "University of Tokyo", "Kyoto University", "Osaka University", "Tokyo Institute of Technology",
    "Waseda University", "Keio University", "National Taiwan University",
    "Indian Institute of Technology Bombay", "Indian Institute of Technology Delhi",
    "Indian Institute of Science", "University of Malaya", "Chulalongkorn University",
    "Mahidol University", "Universiti Teknologi Malaysia", "American University of Beirut",
    "King Abdullah University of Science and Technology", "King Fahd University of Petroleum and Minerals",
    "King Saud University", "Qatar University", "Khalifa University",
    "United Arab Emirates University", "American University of Sharjah", "University of Cape Town",
    "University of the Witwatersrand", "Stellenbosch University", "American University in Cairo",
    "University of Nairobi", "Makerere University", "Cairo University", "University of Sao Paulo",
    "Universidade Estadual de Campinas", "Pontificia Universidad Catolica de Chile",
    "Universidad de Buenos Aires", "Universidad Nacional Autonoma de Mexico",
    "Tecnologico de Monterrey", "University of the West Indies", "University of Waterloo",
    "Queen's University", "University of Alberta", "University of Montreal", "Boston University",
    "New York University", "University of Texas at Austin", "Georgia Institute of Technology",
    "University of Illinois Urbana-Champaign", "University of Wisconsin-Madison",
    "University of Washington", "Carnegie Mellon University", "Purdue University",
    "University of California, San Diego", "University of California, Davis", "Ohio State University",
    "Pennsylvania State University", "University of Minnesota", "Rice University",
    "Vanderbilt University", "University of Southern California", "University of Notre Dame",
    "Georgetown University", "Brown University", "Dartmouth College", "University of Virginia",
    "University of North Carolina at Chapel Hill", "Michigan State University", "Arizona State University",
    "Nazarbayev University", "Al-Farabi Kazakh National University", "Eurasian National University",
    "Kazakh-British Technical University", "Suleyman Demirel University", "KIMEP University",
    "Almaty Management University", "Satbayev University", "Astana IT University", "Narxoz University",
    "Maqsut Narikbayev University", "International IT University Almaty", "Kazakh-German University",
    "Turan University", "Asfendiyarov Kazakh National Medical University", "Karaganda Buketov University",
    "Abai Kazakh National Pedagogical University", "Auezov South Kazakhstan University", "Toraighyrov University", "University of Auckland",
    "University of Otago", "Trinity College Dublin", "University College Dublin",
    "Sungkyunkwan University", "Hanyang University",
    # --- Расширение: Центральная Азия, СНГ, Турция, Европа, Азия, Америка, Африка ---
    "Nazarbayev University School of Medicine", "Kazakh National University of Arts", "Kazakh-Turkish Manas University",
    "American University of Central Asia", "Ala-Too International University", "Westminster International University in Tashkent",
    "Inha University in Tashkent", "National University of Uzbekistan", "Tashkent State University of Economics",
    "Belarusian State University", "Moscow State University", "Higher School of Economics",
    "ITMO University", "Saint Petersburg State University", "Tomsk State University",
    "Novosibirsk State University", "Baku Higher Oil School", "ADA University",
    "Yerevan State University", "Tbilisi State University", "Koc University",
    "Sabanci University", "Bilkent University", "Bogazici University",
    "Middle East Technical University", "Istanbul Technical University", "Hacettepe University",
    "Tel Aviv University", "Hebrew University of Jerusalem", "Technion Israel Institute of Technology",
    "Weizmann Institute of Science", "New York University Abu Dhabi", "Hamad Bin Khalifa University",
    "Sultan Qaboos University", "University of Groningen", "Erasmus University Rotterdam",
    "Wageningen University", "Eindhoven University of Technology", "Ghent University",
    "Universite catholique de Louvain", "University of Geneva", "University of Bern",
    "University of Basel", "RWTH Aachen University", "University of Freiburg",
    "University of Tubingen", "University of Gottingen", "Karlsruhe Institute of Technology",
    "University of Bonn", "University of Hamburg", "TU Berlin",
    "TU Dresden", "University of Stuttgart", "Ecole Polytechnique",
    "Universite PSL", "Universite Paris-Saclay", "Universite Grenoble Alpes",
    "HEC Paris", "University of Glasgow", "University of Bristol",
    "University of Warwick", "University of Birmingham", "University of Leeds",
    "University of Sheffield", "University of Nottingham", "University of Southampton",
    "Durham University", "University of St Andrews", "Lancaster University",
    "University of Bath", "Queen Mary University of London", "University of Exeter",
    "Chalmers University of Technology", "KTH Royal Institute of Technology", "Stockholm University",
    "University of Gothenburg", "Aarhus University", "Technical University of Denmark",
    "Aalto University", "University of Turku", "University of Bergen",
    "Norwegian University of Science and Technology", "University of Iceland", "Vienna University of Technology",
    "University of Graz", "Jagiellonian University", "Warsaw University of Technology",
    "AGH University of Krakow", "Czech Technical University in Prague", "Masaryk University",
    "Eotvos Lorand University", "University of Debrecen", "Semmelweis University",
    "University of Szeged", "University of Ljubljana", "University of Zagreb",
    "University of Belgrade", "University of Bucharest", "Sofia University",
    "University of Tartu", "Vilnius University", "University of Latvia",
    "University of Padua", "University of Milan", "University of Pisa",
    "University of Turin", "University of Lisbon", "University of Porto",
    "Universidad de Navarra", "IE University", "University of Cyprus",
    "National and Kapodistrian University of Athens", "University of Malta", "Zhejiang University",
    "Nanjing University", "University of Science and Technology China", "Wuhan University",
    "Sun Yat-sen University", "Harbin Institute of Technology", "Xi'an Jiaotong University",
    "Tongji University", "Hong Kong Polytechnic University", "City University of Hong Kong",
    "Macau University of Science and Technology", "Tohoku University", "Nagoya University",
    "Hokkaido University", "Kyushu University", "University of Tsukuba",
    "Pohang University of Science and Technology", "Kyung Hee University", "Ewha Womans University",
    "Nanyang Business School", "Singapore Management University", "University of Indonesia",
    "Universiti Putra Malaysia", "Universiti Sains Malaysia", "Universiti Kebangsaan Malaysia",
    "Ateneo de Manila University", "University of the Philippines", "Vietnam National University Hanoi",
    "Indian Institute of Technology Madras", "Indian Institute of Management Ahmedabad", "University of Delhi",
    "University of Queensland", "Monash University", "University of New South Wales",
    "University of Western Australia", "University of Adelaide", "Macquarie University",
    "RMIT University", "Victoria University of Wellington", "University of Canterbury",
    "Massey University", "University of Florida", "University of Maryland",
    "University of Pittsburgh", "University of Colorado Boulder", "University of Arizona",
    "Texas A&M University", "University of Rochester", "Emory University",
    "Tufts University", "Washington University in St. Louis", "University of Massachusetts Amherst",
    "Indiana University Bloomington", "University of Ottawa", "Western University",
    "McMaster University", "Simon Fraser University", "University of Calgary",
    "Dalhousie University", "University of Chile", "Universidad de los Andes",
    "Universidad Nacional de Colombia", "University of Ghana", "University of Lagos",
    "Addis Ababa University", "University of Pretoria", "University of Rwanda",
]

CONCURRENT_SEARCH_LIMIT = 8       # сколько запросов к DDGS одновременно
SEARCH_DELAY_RANGE = (0.4, 1.2)   # случайная задержка перед каждым запросом, чтобы не забанили
UNIVERSITY_RESULTS_PER_QUERY = 3  # сниппетов на каждый запрос по университету
PROGRAM_RESULTS_PER_QUERY = 3     # сниппетов на каждый запрос по программе-конкурсу
BROAD_RESULTS_PER_QUERY = 5       # сниппетов на общий запрос
EXTRACTION_CHUNK_SNIPPETS = int(os.getenv(
    "EXTRACTION_CHUNK_SNIPPETS", {"gemini": "50", "groq": "7"}.get(LLM_PROVIDER, "12")
))  # сколько сниппетов отправляем в модель за один вызов; локальной — меньше
EXTRACTION_DELAY = float(os.getenv(
    "EXTRACTION_DELAY", {"groq": "15"}.get(LLM_PROVIDER, "0")
))  # пауза между вызовами модели, сек — чтобы не упереться в лимит токенов/минуту облачного API
LINK_CHECK_CONCURRENCY = 10
LINK_CHECK_TIMEOUT = 8
# Сколько запусков подряд грант может не встретиться в поиске, прежде чем автоочистка снимет его с публикации
SWEEP_MAX_MISSES = int(os.getenv("SWEEP_MAX_MISSES", "6"))
# Что отправлять оператору на проверку: doubtful — только записи с сомнительной страной; all — все новые
REVIEW_MODE = os.getenv("REVIEW_MODE", "doubtful").strip().lower()


SYSTEM_PROMPT_CHAT += """

Формат ответа: коротко и по делу — не больше 8–10 предложений или короткий список из 3–6 пунктов.
Не пересказывай весь список программ: выбери 2–4 самых подходящих и объясни почему.
Если данных не хватает — задай один уточняющий вопрос в конце.
"""

_WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ]{3,}")
CHAT_CONTEXT_LIMIT = int(os.getenv("CHAT_CONTEXT_LIMIT", "18"))  # сколько грантов отдаём модели за раз


def _short(text, limit: int = 90) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


async def _chat_grants_context(question: str) -> str:
    """Компактный список грантов, отсортированный по совпадению слов с вопросом.

    Раньше в модель уходили ВСЕ гранты с полными описаниями — это медленно.
    Теперь: короткие строки, только самые релевантные, не больше CHAT_CONTEXT_LIMIT.
    """
    q_words = {w.lower() for w in _WORD_RE.findall(question)}
    if any(w in q_words for w in ("казахстан", "казахстане", "ент", "болашак")):
        q_words.add("kz")
    rows = []
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT name, CASE WHEN is_domestic = 1 THEN 'kz' ELSE 'abroad' END AS category, degree, coverage, "
            "requirements, deadline, status FROM grants WHERE record_status = 'active'"
        ) as cursor:
            rows = await cursor.fetchall()
    scored = []
    for r in rows:
        hay = f"{r['name']} {r['coverage']} {r['requirements']} {r['category']} {r['degree']}".lower()
        score = sum(1 for w in q_words if w in hay)
        if r["status"] == "open":
            score += 0.5
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    lines = []
    for _, r in scored[:CHAT_CONTEXT_LIMIT]:
        region = "Казахстан" if r["category"] == "kz" else "за рубежом"
        level = {"bachelor": "бакалавриат", "master": "магистратура", "phd": "PhD",
                 "language": "языковые курсы"}.get(r["degree"], "все уровни")
        lines.append(
            f"- {r['name']} ({region}, {level}); дедлайн: {_short(r['deadline'], 40)}; "
            f"покрытие: {_short(r['coverage'], 70)}; требования: {_short(r['requirements'], 70)}"
        )
    return "\n".join(lines)


LANG_INSTRUCTION = {
    "kz": "\n\nОтвечай на казахском языке (қазақ тілінде), латиницу не используй.",
    "en": "\n\nAnswer in English.",
    "ru": "",
}


async def _chat_instruction(user_question: str, user_id: int = None, lang: str = "ru") -> str:
    instruction = SYSTEM_PROMPT_CHAT + "\n\nАктуальные программы из нашей базы (самые подходящие к вопросу):\n" + \
        await _chat_grants_context(user_question)
    if user_id:
        profile = await get_user_profile(user_id)
        profile_lines = []
        if profile.get("ielts"):
            profile_lines.append(f"IELTS: {profile['ielts']}")
        if profile.get("gpa"):
            profile_lines.append(f"GPA: {profile['gpa']}")
        if profile.get("field_of_interest"):
            profile_lines.append(f"Интересующее направление: {profile['field_of_interest']}")
        if profile_lines:
            instruction += "\n\nПрофиль пользователя:\n" + "\n".join(profile_lines)
    instruction += LANG_INSTRUCTION.get((lang or "ru").lower(), "")
    return instruction


async def ask_gemini_consultant(user_question: str, user_id: int = None, lang: str = "ru") -> str:
    """Отвечает на любые вопросы пользователя прямо в чате, с учётом профиля."""
    try:
        instruction = await _chat_instruction(user_question, user_id, lang)
        return await llm_generate(instruction, user_question, temperature=0.4, num_ctx=CHAT_NUM_CTX,
                                  num_predict=CHAT_NUM_PREDICT, model=OLLAMA_CHAT_MODEL if LLM_PROVIDER == "ollama" else None)
    except Exception as e:
        logging.error(f"Ошибка вызова LLM в чате: {e}")
        return "⚠️ ИИ-консультант временно недоступен. Попробуй через минуту."


async def ask_consultant_stream(user_question: str, user_id: int = None, lang: str = "ru"):
    """То же, что ask_gemini_consultant, но отдаёт ответ по кусочкам (для сайта)."""
    instruction = await _chat_instruction(user_question, user_id, lang)
    buffer, in_think = "", False
    async for piece in llm_stream(instruction, user_question, temperature=0.4, num_ctx=CHAT_NUM_CTX,
                                  num_predict=CHAT_NUM_PREDICT, model=OLLAMA_CHAT_MODEL if LLM_PROVIDER == "ollama" else None):
        # на случай, если модель всё же начала «размышлять» — не показываем блок <think>
        buffer += piece
        if "<think>" in buffer and not in_think:
            in_think = True
        if in_think:
            if "</think>" in buffer:
                buffer = buffer.split("</think>", 1)[1]
                in_think = False
            else:
                continue
        if buffer:
            yield buffer
            buffer = ""


def _search_sync(query: str, max_results: int) -> list:
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


def _build_sources() -> list:
    """Список источников для мониторинга: (kind, name, [queries], results_per_query)."""
    sources = [("broad", q, [q], BROAD_RESULTS_PER_QUERY) for q in BROAD_QUERIES]
    sources += [
        ("program", prog, [
            f"{prog} {YEARS} application deadline",
            f"{prog} call for applications open {YEARS}",
        ], PROGRAM_RESULTS_PER_QUERY)
        for prog in PROGRAMS
    ]
    sources += [
        ("university", uni, [
            f"{uni} scholarships international students {YEARS} deadline",
            f"{uni} fully funded scholarship financial aid apply {YEARS}",
        ], UNIVERSITY_RESULTS_PER_QUERY)
        for uni in UNIVERSITIES
    ]
    return sources


async def fetch_all_snippets():
    """Мониторинг: проходит по всем источникам (общие запросы, программы, университеты) параллельно.

    Возвращает (results, seen_links): results — список dict
    {"kind", "name", "snippets": [...], "error"} в порядке источников.
    """
    sources = _build_sources()
    semaphore = asyncio.Semaphore(CONCURRENT_SEARCH_LIMIT)
    loop = asyncio.get_running_loop()
    results = [None] * len(sources)
    seen_links: set = set()

    async def _worker(idx: int, kind: str, name: str, queries: list, max_results: int):
        snippets, errors, seen_here = [], [], set()
        for query in queries:
            async with semaphore:
                await asyncio.sleep(random.uniform(*SEARCH_DELAY_RANGE))
                try:
                    raw_results = await loop.run_in_executor(None, _search_sync, query, max_results)
                except Exception as e:
                    logging.warning(f"Ошибка поиска по запросу '{query}': {e}")
                    errors.append(str(e)[:120])
                    continue
            for r in raw_results:
                href = r.get("href")
                if not href or href in seen_here:
                    continue
                seen_here.add(href)
                snippets.append(
                    f"Источник: {name}\nTitle: {r['title']}\nSnippet: {r['body']}\nURL: {href}\n"
                )
            seen_links.update(seen_here)
        results[idx] = {
            "kind": kind, "name": name, "snippets": snippets,
            "error": "; ".join(errors) if errors and not snippets else None,
        }
        _progress("searching", done=sum(1 for r in results if r is not None), total=len(sources))

    logging.info(
        f"Мониторинг: {len(BROAD_QUERIES)} общих запросов, {len(PROGRAMS)} программ, "
        f"{len(UNIVERSITIES)} университетов..."
    )
    await asyncio.gather(*[
        _worker(i, kind, name, queries, mr) for i, (kind, name, queries, mr) in enumerate(sources)
    ])
    total = sum(len(r["snippets"]) for r in results)
    logging.info(f"Поиск завершён, собрано {total} сниппетов из {len(sources)} источников.")
    return results, seen_links


def is_link_from_search(link: str, seen_links_norm: set) -> bool:
    """Ссылка допускается, если она была в результатах поиска или хотя бы её домен там встречался."""
    norm = normalize_link(link)
    if norm in seen_links_norm:
        return True
    return link_domain(link) in {l.split("/")[0] for l in seen_links_norm}


def _is_public_host(url: str) -> bool:
    """Не ходим на localhost / внутренние адреса сервера (защита от SSRF через подставные ссылки)."""
    import ipaddress
    import socket
    from urllib.parse import urlparse
    try:
        host = urlparse(url).hostname or ""
        if not host or host.lower() in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
            return False
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return bool(infos)
    except Exception:
        return False


PAGE_MAX_BYTES = 400_000   # сколько читаем со страницы гранта для подтверждения дедлайна


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple:
    """-> (страница открывается, текст страницы). Текст пустой, если это не HTML или страница не открылась."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; GrantBot/1.0)", "Accept-Language": "en,ru;q=0.8,kk;q=0.7"}
    timeout = aiohttp.ClientTimeout(total=LINK_CHECK_TIMEOUT)
    if not url.lower().startswith(("http://", "https://")):
        return False, ""
    if not await asyncio.get_running_loop().run_in_executor(None, _is_public_host, url):
        return False, ""
    try:
        async with session.get(url, headers=headers, timeout=timeout, allow_redirects=True) as resp:
            if resp.status >= 400:
                logging.warning(f"Ссылка отвечает {resp.status}: {url}")
                return False, ""
            if "html" not in (resp.headers.get("Content-Type") or "").lower():
                return True, ""
            raw = await resp.content.read(PAGE_MAX_BYTES)
            return True, page_text(raw.decode(resp.charset or "utf-8", "ignore"))
    except Exception as e:
        logging.warning(f"Ссылка недоступна: {url} ({e})")
        return False, ""


async def is_link_valid(session: aiohttp.ClientSession, url: str) -> bool:
    return (await fetch_page(session, url))[0]


async def recheck_links() -> dict:
    """Еженедельно: открывает страницы всех активных грантов сканера; мёртвые ссылки уводят грант в архив."""
    links = await get_links_to_check()
    semaphore = asyncio.Semaphore(LINK_CHECK_CONCURRENCY)

    async def _check(session, grant_id, url):
        async with semaphore:
            return grant_id, await is_link_valid(session, url)

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[_check(session, gid, url) for gid, url in links])
    archived = await record_link_check(list(results))
    summary = {"checked": len(results), "failed": sum(1 for _, ok in results if not ok), "archived": archived}
    logging.info(f"Проверка ссылок: проверено {summary['checked']}, не открылось {summary['failed']}, в архив {archived}.")
    return summary


def validate_iso_date(value) -> Optional[str]:
    """Дата YYYY-MM-DD (в том числе прошедшая) или None."""
    if not isinstance(value, str) or not DEADLINE_DATE_RE.match(value.strip()):
        return None
    try:
        datetime.date.fromisoformat(value.strip())
    except ValueError:
        return None
    return value.strip()


def validate_deadline_date(value) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    if not DEADLINE_DATE_RE.match(value.strip()):
        return None
    try:
        parsed = datetime.date.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed < datetime.date.today():
        return None
    return value.strip()


async def _extract_grants_from_chunk(chunk_snippets: list, prompt_extract: str, batch_num: int, total_batches: int) -> list:
    raw_text = "\n---\n".join(chunk_snippets)
    try:
        text = await llm_generate(prompt_extract, f"Текст:\n\n{raw_text}", temperature=0.2, json_mode=True)
        grants_list = _parse_grants_json(text)
        logging.info(f"Батч {batch_num}/{total_batches}: извлечено {len(grants_list)} кандидатов.")
        return grants_list
    except Exception as e:
        logging.error(f"Ошибка извлечения в батче {batch_num}/{total_batches}: {e}")
        return []


last_scan_stats: dict = {}
# Живой прогресс текущего сканирования — читает сайт (/api/scan/progress)
scan_progress: dict = {"phase": "idle", "done": 0, "total": 0, "started_at": None, "found": 0}


def _progress(phase: str = None, done: int = None, total: int = None, **extra):
    if phase is not None:
        scan_progress["phase"] = phase
    if done is not None:
        scan_progress["done"] = done
    if total is not None:
        scan_progress["total"] = total
    scan_progress.update(extra)


async def scan_and_save_grants() -> list:
    """Полный цикл мониторинга: поиск по всем источникам -> извлечение ИИ -> проверка -> сохранение."""
    started = datetime.datetime.now()
    run_started = started.isoformat(timespec="seconds")   # всё, что не встретится после этой отметки, — «пропуск»
    _progress("searching", 0, 0, started_at=run_started, found=0)
    logging.info("Начинаю мониторинг грантов по университетам и международным конкурсам...")
    results, seen_links = await fetch_all_snippets()
    seen_links_norm = {normalize_link(l) for l in seen_links}

    # Батчи собираем из сниппетов; каждый сниппет уже несёт строку «Источник: ...»
    chunks, current = [], []
    for r in results:
        current.extend(r["snippets"])
        if len(current) >= EXTRACTION_CHUNK_SNIPPETS:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)

    today_str = datetime.date.today().isoformat()
    now_str = datetime.datetime.now().isoformat(timespec="seconds")
    source_kind = {r["name"]: r["kind"] for r in results}
    # статистика по источникам: snippets / found / new
    stats = {r["name"]: {"snippets": len(r["snippets"]), "found": 0, "new": 0, "error": r["error"]} for r in results}

    all_candidates = []
    if chunks:
        prompt_extract = PROMPT_EXTRACT_TEMPLATE.format(today=today_str)
        logging.info(f"Извлечение ИИ из {len(chunks)} батчей...")
        _progress("extracting", 0, len(chunks))
        for i, chunk in enumerate(chunks, start=1):
            all_candidates.extend(await _extract_grants_from_chunk(chunk, prompt_extract, i, len(chunks)))
            _progress("extracting", i, len(chunks), found=len(all_candidates))
            if EXTRACTION_DELAY and i < len(chunks):
                await asyncio.sleep(EXTRACTION_DELAY)
    else:
        logging.info("Ничего не найдено при поиске.")

    # Фильтр: имя + ссылка из результатов поиска
    candidates, hallucinated = [], 0
    for g in all_candidates:
        if not isinstance(g, dict) or not g.get("name") or not g.get("link"):
            continue
        g["name"] = clean_text(g["name"], 200)
        g["link"] = str(g["link"]).strip()
        if not g["name"]:
            continue
        if not is_link_from_search(g["link"], seen_links_norm):
            hallucinated += 1
            continue
        src = str(g.get("source") or "").strip()
        g["source"] = src if src in stats else None
        candidates.append(g)
    logging.info(
        f"Кандидатов после извлечения: {len(candidates)} "
        f"(отброшено ссылок не из поиска: {hallucinated}). Проверяю ссылки..."
    )
    _progress("checking", 0, len(candidates))

    semaphore = asyncio.Semaphore(LINK_CHECK_CONCURRENCY)

    async def _check(session, g):
        async with semaphore:
            ok, text = await fetch_page(session, g["link"])
            # дата дедлайна подтверждена, только если она написана на самой странице гранта
            g["deadline_confirmed"] = ok and date_in_text(validate_deadline_date(g.get("deadline_date")), text)
            return g, ok

    async with aiohttp.ClientSession() as session:
        checked = await asyncio.gather(*[_check(session, g) for g in candidates])
    valid_candidates = [g for g, ok in checked if ok]
    logging.info(f"Ссылок прошло проверку: {len(valid_candidates)} из {len(candidates)}.")

    existing = await get_all_grants_light()
    tombstones = await get_tombstones()
    newly_added, seen_again = [], set()
    counts = {"created": 0, "updated": 0, "unchanged": 0, "flagged": 0}
    skipped_expired, revived = 0, []

    async with aiosqlite.connect(DB_NAME) as db:
        for g in valid_candidates:
            if g["source"]:
                stats[g["source"]]["found"] += 1
            record = _prepare_record(g)
            dup_id = find_duplicate_grant(existing, record["name"], record["link"])
            if dup_id is None and record["external_id"] in tombstones:
                # Эту страницу уже удаляли по истёкшему дедлайну. Берём снова, только если объявлен новый срок
                old_deadline = tombstones[record["external_id"]] or ""
                if not record["deadline_date"] or record["deadline_date"] <= old_deadline:
                    skipped_expired += 1
                    continue
                revived.append(record["external_id"])
            grant_id, action = await upsert_scanned_grant(db, record, now_str, dup_id)
            if action != "created":
                if grant_id not in seen_again:
                    seen_again.add(grant_id)
                    counts[action] += 1
                continue
            record["id"] = grant_id
            existing.append((record["name"], record["link"], grant_id))
            if record["record_status"] != "active":   # ждёт проверки оператором, в каталог и рассылку не идёт
                counts["flagged"] += 1
                logging.info(f"На проверку: «{record['name']}» — {record['review_note'] or 'новая запись'}")
                continue
            counts["created"] += 1
            newly_added.append(record)
            if g["source"]:
                stats[g["source"]]["new"] += 1
        await db.commit()
    for external_id in revived:
        await drop_tombstone(external_id)
    if skipped_expired:
        logging.info(f"Пропущено ранее удалённых по дедлайну программ без нового срока: {skipped_expired}.")

    # Автоочистка: только по источникам, поиск по которым в этом запуске сработал
    checked_sources = [name for name, st in stats.items() if st["snippets"] and not st["error"]]
    counts["archived"] = await sweep_stale_grants(checked_sources, run_started, SWEEP_MAX_MISSES)
    counts["errors"] = sum(1 for st in stats.values() if st["error"])

    for name, st in stats.items():
        await record_monitor_result(
            name, source_kind[name], now_str, st["snippets"], st["found"], st["new"], st["error"]
        )
    finished_str = datetime.datetime.now().isoformat(timespec="seconds")
    await log_scan_run(SOURCE_SCANNER, run_started, finished_str, counts)

    elapsed = (datetime.datetime.now() - started).seconds
    last_scan_stats.clear()
    last_scan_stats.update({
        "finished_at": now_str, "elapsed_sec": elapsed, "sources": len(results),
        "snippets": sum(st["snippets"] for st in stats.values()),
        "candidates": len(candidates), "valid": len(valid_candidates),
        "new": len(newly_added), "seen_again": len(seen_again),
        "updated": counts["updated"], "flagged": counts["flagged"], "archived": counts["archived"],
        "errors": counts["errors"],
    })
    _progress("done", len(results), len(results), found=len(newly_added), finished_at=now_str)
    logging.info(
        f"Мониторинг завершён за {elapsed}с. Новых: {len(newly_added)}, обновлено: {counts['updated']}, "
        f"без изменений: {counts['unchanged']}, на проверку: {counts['flagged']}, в архив: {counts['archived']}."
    )
    return newly_added


def _prepare_record(g: dict) -> dict:
    """Кандидат от модели -> запись для базы: очищенный текст, страна по жёстким правилам, статус модерации."""
    # Модель может вернуть null вместо строки — .get(key, default) от этого не спасает
    category = g.get("category") if g.get("category") in ("kz", "abroad") else None
    country, provider, doubts = resolve_location(
        g.get("country_code"), g.get("provider_country"), category, g["source"], link_domain(g["link"]), g["name"]
    )
    coverage = clean_text(g.get("coverage")) or "Не указано"
    is_ongoing = 1 if g.get("is_ongoing") is True else 0
    deadline_date = None if is_ongoing else validate_deadline_date(g.get("deadline_date"))
    start_date = validate_iso_date(g.get("application_start_date"))
    status = g.get("status") if g.get("status") in ("open", "upcoming") else "unknown"
    # программы из списка конкурсов (государственные стипендии, фонды) объявляются ежегодно
    yearly = g.get("recurrence_period") == "yearly" or g["source"] in PROGRAM_COUNTRY
    if doubts:
        record_status = "flagged_review"
    else:
        record_status = "draft" if REVIEW_MODE == "all" else "active"
    record = {
        "name": g["name"], "link": g["link"], "source": g["source"],
        "category": "kz" if country == "KZ" else "abroad",   # раздел следует из страны, а не из слов модели
        "country_code": country, "provider_country": provider,
        "degree": g.get("degree") if g.get("degree") in DEGREES else "all",
        "status": status_by_dates(start_date, deadline_date, status),   # даты надёжнее слов модели
        "application_start_date": start_date, "is_ongoing": is_ongoing,
        "recurrence_period": "yearly" if yearly and not is_ongoing else None,
        "deadline_confirmed": 1 if deadline_date and g.get("deadline_confirmed") else 0,
        "coverage": coverage,
        "requirements": clean_text(g.get("requirements")) or "Уточняйте на сайте",
        "deadline": clean_text(g.get("deadline"), 200) or "Уточняется",
        "deadline_date": deadline_date,
        "funding": g.get("funding") if g.get("funding") in ("full", "partial") else guess_funding(coverage),
        "source_id": SOURCE_SCANNER, "external_id": normalize_link(g["link"]),
        "record_status": record_status, "review_note": "; ".join(doubts) or None,
    }
    record["data_hash"] = grant_hash(record)
    return record
