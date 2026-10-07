import difflib
import datetime
import hashlib
import html
import json
import os
import re
import sqlite3
import aiosqlite

from pathlib import Path

from core.geo import domain_country, resolve_location

BASE_DIR = Path(__file__).resolve().parent.parent   # корень проекта
# На хостинге база лежит на постоянном диске: DATA_DIR=/data (переменная окружения)
DATA_DIR = Path(os.getenv("DATA_DIR") or BASE_DIR / "data")
LOGS_DIR = Path(os.getenv("LOGS_DIR") or BASE_DIR / "logs")
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DB_NAME = str(DATA_DIR / "grants.db")


# (category, degree, name, coverage, requirements, deadline, deadline_date, link, source)
KZ_SEED_GRANTS = [
    ("kz", "bachelor", "Государственный образовательный грант РК (по результатам ЕНТ)",
     "100% оплата обучения в вузах РК + государственная стипендия",
     "Пороговый балл ЕНТ, участие в конкурсе грантов, гражданство РК",
     "Июль, подача заявлений после ЕНТ", None, "https://testcenter.kz", "Министерство образования РК"),
    ("kz", "all", "Гранты и стипендии КБТУ — Казахстанско-Британский технический университет",
     "Гранты на обучение, скидки за высокие баллы ЕНТ и олимпиады",
     "Высокий балл ЕНТ, победы в олимпиадах, английский язык",
     "Уточняйте на сайте (приём летом)", None, "https://kbtu.edu.kz", "Kazakh-British Technical University"),
    ("kz", "all", "Гранты SDU University (Университет Сулеймана Демиреля)",
     "Внутренние гранты и скидки на обучение до 100%",
     "Баллы ЕНТ, внутренний конкурс, мотивационное письмо",
     "Уточняйте на сайте", None, "https://sdu.edu.kz", "Suleyman Demirel University"),
    ("kz", "all", "Стипендии и гранты KIMEP University",
     "Частичное и полное покрытие обучения, стипендии за успеваемость",
     "Английский язык (IELTS/внутренний тест), высокая успеваемость",
     "Уточняйте на сайте", None, "https://kimep.kz", "KIMEP University"),
    ("kz", "all", "Гранты AlmaU (Алматы Менеджмент Университет)",
     "Гранты ректора и скидки на обучение",
     "Баллы ЕНТ, портфолио, собеседование",
     "Уточняйте на сайте", None, "https://almau.edu.kz", "Almaty Management University"),
    ("kz", "all", "Гранты Satbayev University",
     "Госгранты на технические специальности + внутренние гранты университета",
     "Баллы ЕНТ по профильным предметам",
     "Уточняйте на сайте", None, "https://satbayev.university", "Satbayev University"),
    ("kz", "all", "Гранты КазНУ им. аль-Фараби",
     "Государственные гранты и гранты ректора, места в общежитии",
     "Баллы ЕНТ, для магистратуры — КТ и профильный экзамен",
     "Уточняйте на сайте", None, "https://www.kaznu.kz", "Al-Farabi Kazakh National University"),
    ("kz", "all", "Гранты ЕНУ им. Л. Н. Гумилёва",
     "Государственные гранты, стипендии, общежитие",
     "Баллы ЕНТ, для магистратуры — вступительные экзамены",
     "Уточняйте на сайте", None, "https://enu.kz", "Eurasian National University"),
    ("kz", "bachelor", "Гранты Astana IT University",
     "Государственные и внутренние гранты на IT-специальности",
     "Высокие баллы ЕНТ по математике и информатике",
     "Уточняйте на сайте", None, "https://astanait.edu.kz", "Astana IT University"),
    ("kz", "all", "Гранты и скидки Narxoz University",
     "Гранты на обучение и скидки за баллы ЕНТ",
     "Баллы ЕНТ, для магистратуры — портфолио",
     "Уточняйте на сайте", None, "https://narxoz.kz", "Narxoz University"),
    ("kz", "all", "Гранты Maqsut Narikbayev University (MNU, бывш. КазГЮУ)",
     "Гранты и скидки на обучение по праву, экономике, IT",
     "Баллы ЕНТ, собеседование",
     "Уточняйте на сайте", None, "https://mnu.kz", "Maqsut Narikbayev University"),
    ("kz", "all", "Гранты IITU — Международный университет информационных технологий",
     "Государственные гранты на IT-направления + гранты университета",
     "Баллы ЕНТ по математике и информатике",
     "Уточняйте на сайте", None, "https://iitu.edu.kz", "International IT University"),
    ("kz", "all", "Гранты Казахстанско-Немецкого университета (DKU)",
     "Гранты DAAD и университета, стипендии, программы двойного диплома с Германией",
     "Немецкий или английский язык, конкурс",
     "Уточняйте на сайте", None, "https://dku.kz", "Kazakh-German University"),
    ("kz", "all", "Гранты Turan University",
     "Гранты ректора и скидки на обучение",
     "Баллы ЕНТ, участие в конкурсе",
     "Уточняйте на сайте", None, "https://turan-edu.kz", "Turan University"),
    ("kz", "all", "Гранты КазНМУ им. С. Д. Асфендиярова",
     "Государственные гранты на медицинские специальности",
     "Баллы ЕНТ по биологии и химии",
     "Уточняйте на сайте", None, "https://kaznmu.kz", "Asfendiyarov Kazakh National Medical University"),
    ("kz", "all", "Гранты Карагандинского университета им. Букетова",
     "Государственные гранты и внутренние стипендии",
     "Баллы ЕНТ, конкурс",
     "Уточняйте на сайте", None, "https://buketov.edu.kz", "Karaganda Buketov University"),
    ("kz", "all", "Гранты КазНПУ им. Абая",
     "Государственные гранты на педагогические специальности",
     "Баллы ЕНТ, для магистратуры — вступительные экзамены",
     "Уточняйте на сайте", None, "https://abaiuniversity.edu.kz", "Abai Kazakh National Pedagogical University"),
    ("kz", "master", "Гранты магистратуры и PhD Nazarbayev University",
     "Полное покрытие обучения, стипендия, общежитие",
     "IELTS 6.5+, GRE/GMAT для ряда программ, диплом бакалавра",
     "Уточняйте на сайте", None, "https://nu.edu.kz/admissions", "Nazarbayev University"),
]


async def init_db():
    """Создает таблицы, накатывает миграции и заполняет стартовыми данными."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                degree TEXT NOT NULL,
                name TEXT NOT NULL,
                coverage TEXT NOT NULL,
                requirements TEXT NOT NULL,
                deadline TEXT NOT NULL,
                link TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subscribed INTEGER DEFAULT 1
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                grant_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, grant_id)
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                rating INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Напоминания о дедлайнах — чтобы не слать повторно
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                grant_id INTEGER NOT NULL,
                days_before INTEGER NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, grant_id, days_before)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS monitor_sources (
                name TEXT PRIMARY KEY,
                kind TEXT NOT NULL,            -- university | program | broad
                last_checked TEXT,
                last_snippets INTEGER DEFAULT 0,
                last_found INTEGER DEFAULT 0,  -- кандидатов прошло проверку в последний раз
                last_new INTEGER DEFAULT 0,    -- новых грантов в последний раз
                total_new INTEGER DEFAULT 0,
                last_error TEXT
            )
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_user_type_time ON events(user_id, event_type, created_at)")
        # Аккаунты сайта: почта+пароль или Google/GitHub. uid — числовой id в таблице users (избранное, профиль)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS web_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid INTEGER NOT NULL UNIQUE,
                email TEXT,
                name TEXT,
                avatar TEXT,
                provider TEXT NOT NULL,          -- email | google | github
                provider_id TEXT,                -- id пользователя у провайдера
                password_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
            """
        )
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_email ON web_accounts(email) WHERE email IS NOT NULL AND provider = 'email'")
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_provider ON web_accounts(provider, provider_id) WHERE provider_id IS NOT NULL")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_grants_active ON grants(is_active, category, degree)")
        await db.commit()

        # --- Миграции для старых баз ---
        migrations = [
            "ALTER TABLE users ADD COLUMN subscribed INTEGER DEFAULT 1",
            "ALTER TABLE users ADD COLUMN ielts REAL",
            "ALTER TABLE users ADD COLUMN gpa REAL",
            "ALTER TABLE users ADD COLUMN field_of_interest TEXT",
            "ALTER TABLE users ADD COLUMN lang TEXT",
            "ALTER TABLE users ADD COLUMN linked_at TEXT",         # когда Telegram и сайт связали в один аккаунт
            "ALTER TABLE web_accounts ADD COLUMN telegram_id INTEGER",
            "ALTER TABLE grants ADD COLUMN deadline_date TEXT",
            "ALTER TABLE grants ADD COLUMN source TEXT",       # университет/программа, где найдено
            "ALTER TABLE grants ADD COLUMN status TEXT",       # open | upcoming | unknown
            "ALTER TABLE grants ADD COLUMN first_seen TEXT",
            "ALTER TABLE grants ADD COLUMN last_seen TEXT",
            # --- Локация: раздел каталога задаётся только этими полями, не текстом ---
            "ALTER TABLE grants ADD COLUMN country_code TEXT",       # страна обучения, ISO-2; NULL = несколько стран
            "ALTER TABLE grants ADD COLUMN provider_country TEXT",   # страна, которая выдаёт грант
            # вычисляется базой: 1 только при country_code = 'KZ', вручную выставить нельзя
            "ALTER TABLE grants ADD COLUMN is_domestic INTEGER GENERATED ALWAYS AS (country_code IS 'KZ') VIRTUAL",
            # --- Парсинг: upsert и очистка ---
            "ALTER TABLE grants ADD COLUMN source_id TEXT",          # парсер: seed | ai_scanner
            "ALTER TABLE grants ADD COLUMN external_id TEXT",        # id у источника: нормализованная ссылка
            "ALTER TABLE grants ADD COLUMN data_hash TEXT",
            "ALTER TABLE grants ADD COLUMN missed_scans INTEGER DEFAULT 0",
            # статус записи (не путать с status — это статус приёма заявок: open | upcoming | unknown)
            "ALTER TABLE grants ADD COLUMN record_status TEXT DEFAULT 'active'",  # active | archived | draft | flagged_review
            "ALTER TABLE grants ADD COLUMN archived_reason TEXT",    # sweep | manual | duplicate
            "ALTER TABLE grants ADD COLUMN review_note TEXT",
            "ALTER TABLE grants ADD COLUMN funding TEXT",            # full | partial | unknown
            # --- Сроки: дедлайн подачи хранится в deadline_date ---
            "ALTER TABLE grants ADD COLUMN application_start_date TEXT",  # когда открывается приём документов
            "ALTER TABLE grants ADD COLUMN is_ongoing INTEGER DEFAULT 0",  # приём круглый год — очистка не трогает
            "ALTER TABLE grants ADD COLUMN recurrence_period TEXT",  # yearly — вместо удаления дедлайн переносится на год
            "ALTER TABLE grants ADD COLUMN deadline_confirmed INTEGER DEFAULT 0",  # дата найдена на странице гранта или подтверждена оператором
            "ALTER TABLE grants ADD COLUMN link_failures INTEGER DEFAULT 0",  # сколько проверок подряд ссылка не открывается
        ]
        for sql in migrations:
            try:
                await db.execute(sql)
                await db.commit()
            except Exception:
                pass  # колонка уже существует

        async with db.execute("SELECT COUNT(*) FROM grants") as cursor:
            count = (await cursor.fetchone())[0]

        if count == 0:
            initial_grants = [
                (
                    "kz", "master", "Программа «Болашак»",
                    "Полное покрытие: обучение, стипендия, перелет, страховка",
                    "GPA от 3.0, IELTS 6.0/6.5, опыт работы от 1–2 лет",
                    "Апрель – Сентябрь", None, "https://bolashak.gov.kz", 1,
                ),
                (
                    "kz", "bachelor", "Государственный образовательный грант РК",
                    "100% покрытие стоимости обучения в вузах РК + стипендия",
                    "Пороговый балл ЕНТ, участие в конкурсе",
                    "Июль (подача заявок)", None, "https://testcenter.kz", 1,
                ),
                (
                    "kz", "all", "Гранты Назарбаев Университета (NU)",
                    "Полная оплата обучения + ежемесячная стипендия",
                    "IELTS 6.5–7.0, вступительные тесты NU",
                    "Ноябрь – Март", None, "https://nu.edu.kz", 1,
                ),
                (
                    "abroad", "all", "Stipendium Hungaricum (Венгрия)",
                    "Обучение, проживание, стипендия, страховка",
                    "IELTS 5.5–6.5, подача через ЦМП и сайт программы",
                    "До 15–16 января ежегодно", "2027-01-15", "https://stipendiumhungaricum.hu", 1,
                ),
                (
                    "abroad", "master", "Erasmus Mundus (Страны ЕС)",
                    "Full Ride: €1400/мес стипендия + покрытие учебы и перелетов",
                    "Бакалавриат, IELTS 6.5–7.5, 2 рекомендации, CV",
                    "Декабрь – Февраль", None, "https://erasmus-plus.ec.europa.eu", 1,
                ),
            ]
            await db.executemany(
                """
                INSERT INTO grants (category, degree, name, coverage, requirements, deadline, deadline_date, link, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                initial_grants,
            )
            await db.commit()

        # Казахстанские вузы и госпрограммы: добавляем в любую базу, если такой ссылки ещё нет
        async with db.execute("SELECT link FROM grants") as cursor:
            existing_links = {normalize_link(r[0]) for r in await cursor.fetchall()}
        now = datetime.datetime.now().isoformat(timespec="seconds")
        to_add = [g for g in KZ_SEED_GRANTS if normalize_link(g[7]) not in existing_links]
        if to_add:
            await db.executemany(
                """
                INSERT INTO grants (category, degree, name, coverage, requirements, deadline, deadline_date, link, is_active,
                                    source, status, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 'unknown', ?, ?)
                """,
                [(g[0], g[1], g[2], g[3], g[4], g[5], g[6], g[7], g[8], now, now) for g in to_add],
            )
            await db.commit()

        await _backfill_grants(db)

        # Журнал запусков сканера: сколько создано / обновлено / заархивировано
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                created INTEGER DEFAULT 0,
                updated INTEGER DEFAULT 0,
                unchanged INTEGER DEFAULT 0,
                flagged INTEGER DEFAULT 0,
                archived INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0,
                error TEXT
            )
            """
        )
        # Словарь синонимов: NU = Nazarbayev University = Назарбаев Университет
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS synonyms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical TEXT NOT NULL,
                alias TEXT NOT NULL,
                alias_norm TEXT NOT NULL UNIQUE
            )
            """
        )
        async with db.execute("SELECT COUNT(*) FROM synonyms") as cursor:
            if (await cursor.fetchone())[0] == 0:
                await db.executemany(
                    "INSERT OR IGNORE INTO synonyms (canonical, alias, alias_norm) VALUES (?, ?, ?)",
                    [(canon, a, a.lower()) for canon, aliases in SEED_SYNONYMS.items() for a in aliases],
                )
        # «Уведомить об открытии»: подписка на будущий грант
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS open_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                grant_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notified_at TEXT,                  -- когда бот отправил сообщение в Telegram
                UNIQUE(user_id, grant_id)
            )
            """
        )
        # Привязка Telegram и сайта: одноразовый код живёт 10 минут. kind — кто его выдал (web | tg),
        # uid — чей это аккаунт (uid сайта или Telegram id). После привязки данные живут под Telegram id.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS link_codes (
                code TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                uid INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                linked_uid INTEGER
            )
            """
        )
        # Удалённые по дедлайну гранты: сканер не должен заново добавлять ту же истёкшую страницу как «новую»
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS grant_tombstones (
                external_id TEXT PRIMARY KEY,
                deadline_date TEXT,
                deleted_at TEXT NOT NULL
            )
            """
        )
        # Каскад: вместе с грантом уходят избранное, напоминания и подписки на открытие
        await db.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_grants_delete_cascade AFTER DELETE ON grants
            BEGIN
                DELETE FROM favorites WHERE grant_id = OLD.id;
                DELETE FROM reminders_sent WHERE grant_id = OLD.id;
                DELETE FROM open_alerts WHERE grant_id = OLD.id;
            END
            """
        )
        # Стартовые программы (госгранты, гранты вузов) объявляются каждый год
        await db.execute("UPDATE grants SET recurrence_period = 'yearly' WHERE source_id = 'seed' AND recurrence_period IS NULL")
        # стартовые записи внесены вручную — их даты не требуют подтверждения страницей
        await db.execute("UPDATE grants SET deadline_confirmed = 1 WHERE source_id = 'seed' AND COALESCE(deadline_confirmed, 0) = 0")
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_grants_source_external ON grants(source_id, external_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_grants_scope_active ON grants(is_domestic, record_status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_grants_destination_active ON grants(country_code, record_status)")
        # is_active (его читает старый код) и record_status всегда согласованы, какой бы из них ни меняли
        await db.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_grants_status_sync AFTER UPDATE OF record_status ON grants
            WHEN NEW.is_active IS NOT (NEW.record_status = 'active')
            BEGIN
                UPDATE grants SET is_active = (NEW.record_status = 'active'),
                                  archived_reason = CASE WHEN NEW.record_status = 'active' THEN NULL ELSE archived_reason END
                WHERE id = NEW.id;
            END
            """
        )
        await db.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_grants_active_sync AFTER UPDATE OF is_active ON grants
            WHEN NEW.is_active IS NOT (NEW.record_status = 'active')
            BEGIN
                UPDATE grants SET record_status = CASE WHEN NEW.is_active = 1 THEN 'active' ELSE 'archived' END,
                                  archived_reason = CASE WHEN NEW.is_active = 1 THEN NULL ELSE COALESCE(archived_reason, 'manual') END
                WHERE id = NEW.id;
            END
            """
        )
        await db.commit()


SEED_SYNONYMS = {
    "Nazarbayev University": ["NU", "НУ", "Назарбаев Университет", "Nazarbayev University"],
    "Kazakh-British Technical University": ["KBTU", "КБТУ", "Казахстанско-Британский технический университет"],
    "Al-Farabi Kazakh National University": ["KazNU", "КазНУ", "аль-Фараби"],
    "Eurasian National University": ["ENU", "ЕНУ", "Гумилёва", "Гумилева"],
    "Suleyman Demirel University": ["SDU", "СДУ", "Сулеймана Демиреля"],
    "Astana IT University": ["AITU", "АИТУ"],
    "International IT University": ["IITU", "МУИТ"],
    "Maqsut Narikbayev University": ["MNU", "КазГЮУ", "KAZGUU"],
    "Almaty Management University": ["AlmaU", "АлмаУ"],
    "Kazakh-German University": ["DKU", "КНУ", "Казахстанско-Немецкий университет"],
    "Bolashak": ["Болашак", "Bolashak"],
    "DAAD": ["DAAD", "ДААД"],
    "Erasmus": ["Erasmus", "Эразмус", "Erasmus Mundus", "Erasmus+"],
}

SOURCE_SEED, SOURCE_SCANNER = "seed", "ai_scanner"
_TAG_RE = re.compile(r"<[^>]{0,200}>")


def clean_text(value, limit: int = 600) -> str:
    """Текст из внешнего источника перед сохранением: без HTML-тегов, управляющих символов и лишних пробелов."""
    text = html.unescape(_TAG_RE.sub(" ", str(value or "")))
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")
    return " ".join(text.split())[:limit]


def grant_hash(g: dict) -> str:
    """Хэш содержимого записи — по нему сканер понимает, изменилась ли программа у источника."""
    parts = [g.get("name"), g.get("country_code"), link_domain(g.get("link") or ""), g.get("degree"),
             g.get("coverage"), g.get("requirements"), g.get("deadline"), g.get("deadline_date"), g.get("status"),
             g.get("application_start_date"), g.get("is_ongoing") or 0]
    return hashlib.sha256("\x1f".join(str(p or "").strip().lower() for p in parts).encode()).hexdigest()


_FULL_RE = re.compile(r"полн\w* (покрыт|оплат|грант)|full(y)?[ -](ride|funded|tuition|scholarship)|толық", re.I)
_PARTIAL_RE = re.compile(r"частич|partial|скидк|discount|жеңілдік", re.I)


def guess_funding(coverage: str) -> str:
    """Полный или частичный грант — по тексту покрытия, когда модель этого не сказала."""
    text = coverage or ""
    full, partial = bool(_FULL_RE.search(text)), bool(_PARTIAL_RE.search(text))
    if full and partial:   # «частичное и полное покрытие» — зависит от конкурса
        return "unknown"
    if full:
        return "full"
    if partial:
        return "partial"
    return "full" if re.search(r"100\s?%", text) else "unknown"


async def _backfill_grants(db):
    """Старые записи (до появления country_code): проставляет страну, source_id, external_id и хэш.

    Страна берётся из источника и домена; где данных не хватает — запись уходит на ручную проверку.
    """
    db.row_factory = aiosqlite.Row
    async with db.execute("SELECT * FROM grants WHERE source_id IS NULL ORDER BY id") as cursor:
        rows = [dict(r) for r in await cursor.fetchall()]
    db.row_factory = None
    if not rows:
        return
    async with db.execute("SELECT external_id FROM grants WHERE external_id IS NOT NULL") as cursor:
        taken = {r[0] for r in await cursor.fetchall()}
    seed_links = {normalize_link(g[7]) for g in KZ_SEED_GRANTS} | {
        "bolashak.gov.kz", "testcenter.kz", "nu.edu.kz", "stipendiumhungaricum.hu", "erasmus-plus.ec.europa.eu"}
    for g in rows:
        external_id = normalize_link(g["link"])
        domain = external_id.split("/")[0]
        hint = domain_country(domain) if g["category"] != "kz" else None
        cc, provider, doubts = resolve_location(hint if hint != "KZ" else None, None, g["category"],
                                                g["source"], domain, g["name"])
        source_id = SOURCE_SEED if external_id in seed_links else SOURCE_SCANNER
        record_status = "active" if g["is_active"] else "archived"
        reason = None if g["is_active"] else "manual"
        if external_id in taken:  # та же ссылка уже есть — оставляем первую запись
            external_id, record_status, reason = None, "archived", "duplicate"
        elif doubts and g["is_active"] and source_id != SOURCE_SEED:
            record_status = "flagged_review"
        taken.add(external_id)
        g["country_code"] = cc
        await db.execute(
            """
            UPDATE grants SET country_code = ?, provider_country = ?, category = ?, source_id = ?, external_id = ?,
                              data_hash = ?, record_status = ?, archived_reason = ?, review_note = ?, funding = ?,
                              is_active = ?, missed_scans = 0
            WHERE id = ?
            """,
            (cc, provider, "kz" if cc == "KZ" else "abroad", source_id, external_id, grant_hash(g), record_status,
             reason, "; ".join(doubts) or None, guess_funding(g["coverage"]), 1 if record_status == "active" else 0,
             g["id"]),
        )
    await db.commit()


# --- Пользователи ---

# --- Аккаунты сайта ---

def _account_row(row) -> dict:
    return dict(row) if row else None


async def get_account_by_id(account_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM web_accounts WHERE id = ?", (account_id,)) as cur:
            return _account_row(await cur.fetchone())


async def get_account_by_email(email: str) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM web_accounts WHERE provider = 'email' AND email = ?", (email.lower(),)) as cur:
            return _account_row(await cur.fetchone())


async def get_account_by_provider(provider: str, provider_id: str) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM web_accounts WHERE provider = ? AND provider_id = ?", (provider, str(provider_id))) as cur:
            return _account_row(await cur.fetchone())


async def create_account(uid: int, provider: str, email: str = None, name: str = None, avatar: str = None,
                         provider_id: str = None, password_hash: str = None) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
        cur = await db.execute(
            """
            INSERT INTO web_accounts (uid, email, name, avatar, provider, provider_id, password_hash, last_login)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (uid, email.lower() if email else None, name, avatar, provider,
             str(provider_id) if provider_id else None, password_hash),
        )
        await db.commit()
        return await get_account_by_id(cur.lastrowid)


async def touch_account_login(account_id: int, name: str = None, avatar: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE web_accounts SET last_login = CURRENT_TIMESTAMP, name = COALESCE(?, name), avatar = COALESCE(?, avatar) WHERE id = ?",
            (name, avatar, account_id),
        )
        await db.commit()


async def merge_anonymous_user(from_uid: int, to_uid: int):
    """Переносит избранное и профиль анонимного посетителя в аккаунт после входа."""
    if not from_uid or from_uid == to_uid:
        return
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO favorites (user_id, grant_id) SELECT ?, grant_id FROM favorites WHERE user_id = ?", (to_uid, from_uid))
        await db.execute(
            """
            UPDATE users SET
                ielts = COALESCE(ielts, (SELECT ielts FROM users WHERE user_id = ?)),
                gpa = COALESCE(gpa, (SELECT gpa FROM users WHERE user_id = ?)),
                field_of_interest = COALESCE(field_of_interest, (SELECT field_of_interest FROM users WHERE user_id = ?))
            WHERE user_id = ?
            """,
            (from_uid, from_uid, from_uid, to_uid),
        )
        await db.commit()


# --- Привязка Telegram и сайта ---

LINK_CODE_TTL_MINUTES = 10
_LINK_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # без O/0 и I/1 — код диктуют или вводят вручную


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


async def create_link_code(kind: str, uid: int) -> dict:
    """Новый одноразовый код. Старые неиспользованные коды этого же пользователя отменяются."""
    import secrets
    assert kind in ("web", "tg")
    now = _utcnow()
    expires = now + datetime.timedelta(minutes=LINK_CODE_TTL_MINUTES)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM link_codes WHERE (uid = ? AND kind = ? AND used_at IS NULL) OR expires_at < ?",
                         (uid, kind, now.isoformat(timespec="seconds")))
        while True:
            code = "".join(secrets.choice(_LINK_ALPHABET) for _ in range(6))
            async with db.execute("SELECT 1 FROM link_codes WHERE code = ?", (code,)) as cur:
                if not await cur.fetchone():
                    break
        await db.execute(
            "INSERT INTO link_codes (code, kind, uid, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (code, kind, uid, now.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds")),
        )
        await db.commit()
    return {"code": code, "expires_at": expires.isoformat(timespec="seconds") + "Z",
            "expires_in": LINK_CODE_TTL_MINUTES * 60}


async def get_link_code(code: str) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM link_codes WHERE code = ?", (code.strip().upper(),)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def is_linked(uid: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT linked_at FROM users WHERE user_id = ?", (uid,)) as cur:
            row = await cur.fetchone()
            return bool(row and row[0])


async def link_accounts(web_uid: int, telegram_id: int, code: str = None) -> dict:
    """Сливает посетителя сайта (web_uid) с пользователем Telegram: избранное, профиль, подписки
    переезжают под Telegram id, аккаунт сайта (если есть) начинает указывать на него.

    -> {"ok": True, "uid": telegram_id} либо {"ok": False, "error": код ошибки}:
       same          — это уже один и тот же пользователь
       web_linked    — у этого аккаунта сайта уже привязан другой Telegram
       tg_taken      — к этому Telegram уже привязан другой аккаунт сайта
    """
    if web_uid == telegram_id:
        return {"ok": False, "error": "same"}
    now = _utcnow().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT linked_at FROM users WHERE user_id = ?", (web_uid,)) as cur:
            row = await cur.fetchone()
        if row and row["linked_at"]:
            return {"ok": False, "error": "web_linked"}
        async with db.execute("SELECT id FROM web_accounts WHERE uid = ?", (web_uid,)) as cur:
            account = await cur.fetchone()
        async with db.execute("SELECT id FROM web_accounts WHERE uid = ? OR telegram_id = ?", (telegram_id, telegram_id)) as cur:
            other = await cur.fetchone()
        if other and (not account or other["id"] != account["id"]):
            return {"ok": False, "error": "tg_taken"}

        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (telegram_id,))
        await db.execute("INSERT OR IGNORE INTO favorites (user_id, grant_id) SELECT ?, grant_id FROM favorites WHERE user_id = ?",
                         (telegram_id, web_uid))
        await db.execute("INSERT OR IGNORE INTO open_alerts (user_id, grant_id) SELECT ?, grant_id FROM open_alerts WHERE user_id = ?",
                         (telegram_id, web_uid))
        await db.execute(
            """
            UPDATE users SET
                ielts = COALESCE(ielts, (SELECT ielts FROM users WHERE user_id = ?)),
                gpa = COALESCE(gpa, (SELECT gpa FROM users WHERE user_id = ?)),
                field_of_interest = COALESCE(field_of_interest, (SELECT field_of_interest FROM users WHERE user_id = ?)),
                linked_at = ?
            WHERE user_id = ?
            """,
            (web_uid, web_uid, web_uid, now, telegram_id),
        )
        if account:
            await db.execute("UPDATE web_accounts SET uid = ?, telegram_id = ? WHERE id = ?", (telegram_id, telegram_id, account["id"]))
        # данные посетителя сайта переехали — старый uid больше не используется (cookie станет Telegram id)
        await db.execute("DELETE FROM favorites WHERE user_id = ?", (web_uid,))
        await db.execute("DELETE FROM open_alerts WHERE user_id = ?", (web_uid,))
        await db.execute("DELETE FROM users WHERE user_id = ?", (web_uid,))
        if code:
            await db.execute("UPDATE link_codes SET used_at = ?, linked_uid = ? WHERE code = ?", (now, telegram_id, code.strip().upper()))
        await db.commit()
    return {"ok": True, "uid": telegram_id}


async def consume_link_code(code: str, expected_kind: str, other_uid: int) -> dict:
    """Проверяет код и выполняет привязку. expected_kind — кто должен был выдать код:
    бот вводит код сайта (web), сайт вводит код бота (tg). other_uid — тот, кто вводит код.

    -> результат link_accounts или {"ok": False, "error": "bad_code" | "expired"}.
    """
    row = await get_link_code(code or "")
    if not row or row["kind"] != expected_kind or row["used_at"]:
        return {"ok": False, "error": "bad_code"}
    if row["expires_at"] < _utcnow().isoformat(timespec="seconds"):
        return {"ok": False, "error": "expired"}
    if expected_kind == "web":      # код выдал сайт, вводит пользователь Telegram
        return await link_accounts(web_uid=row["uid"], telegram_id=other_uid, code=row["code"])
    return await link_accounts(web_uid=other_uid, telegram_id=row["uid"], code=row["code"])


async def add_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.execute("UPDATE users SET subscribed = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def unsubscribe_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET subscribed = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_all_users() -> list[int]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users WHERE subscribed = 1") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


# --- Профиль пользователя ---

async def set_user_profile(user_id: int, ielts=None, gpa=None, field_of_interest=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.execute(
            "UPDATE users SET ielts = ?, gpa = ?, field_of_interest = ? WHERE user_id = ?",
            (ielts, gpa, field_of_interest, user_id),
        )
        await db.commit()


async def get_user_lang(user_id: int) -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return (row[0] if row and row[0] in ("ru", "kz", "en") else "ru")


async def set_user_lang(user_id: int, lang: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
        await db.commit()


async def get_user_profile(user_id: int) -> dict:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT ielts, gpa, field_of_interest FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {"ielts": None, "gpa": None, "field_of_interest": None}
            return dict(row)


# --- Гранты ---

SCOPES = ("kz", "abroad", "all")
DEGREES = ("bachelor", "master", "phd", "language", "all")
# Требования ищем по тексту: GLOB учитывает регистр, поэтому «SAT» не совпадёт с «satisfactory»
_REQ_SQL = {
    "ielts": "requirements GLOB '*IELTS*'",
    "toefl": "requirements GLOB '*TOEFL*'",
    "sat": "requirements GLOB '*SAT*'",
    "gpa": "requirements GLOB '*GPA*'",
    "ent": "(requirements GLOB '*ЕНТ*' OR requirements GLOB '*ҰБТ*' OR requirements GLOB '*UNT*')",
}
REQUIREMENTS = tuple(_REQ_SQL)


def _scope_sql(scope: str) -> str:
    """Раздел каталога — строго по флагу локации. Вузы Казахстана и зарубежья не смешиваются."""
    return {"kz": "is_domestic = 1", "abroad": "is_domestic = 0"}.get(scope, "1 = 1")


def _grant_filters(scope: str, degree: str = "all", country: str = None, funding: str = None,
                   deadline: str = None, req: str = None) -> tuple:
    """-> (WHERE-условие, параметры). Значения идут только параметрами, текст SQL — из констант."""
    where, params = [_scope_sql(scope), "record_status = 'active'"], []
    if deadline in ("open", "upcoming"):
        where.append("status = ?")
        params.append(deadline)
    if degree != "all":
        where.append("(degree = ? OR degree = 'all')")
        params.append(degree)
    if country:
        where.append("country_code = ?")
        params.append(country)
    if funding in ("full", "partial"):
        where.append("funding = ?")
        params.append(funding)
    if req in _REQ_SQL:
        where.append(_REQ_SQL[req])
    return " AND ".join(where), params


SORTS = {
    "new": "id DESC",
    "deadline": "(deadline_date IS NULL), deadline_date ASC, id DESC",          # ближайшие сроки первыми, без даты — в конце
    "funding": "CASE funding WHEN 'full' THEN 0 WHEN 'partial' THEN 1 ELSE 2 END, id DESC",
}


async def get_grants_page(scope: str, degree: str = "all", *, country: str = None, funding: str = None,
                          deadline: str = None, req: str = None, limit: int = 12, cursor: int = None,
                          offset: int = 0, sort: str = "new") -> tuple:
    """Страница каталога -> (записи, всего по фильтру).

    При сортировке по новизне cursor — id последней показанной записи (keyset): следующая страница
    не замедляется с глубиной. Для других сортировок и для Telegram-бота страницы нумеруются смещением.
    """
    where, params = _grant_filters(scope, degree, country, funding, deadline, req)
    order = SORTS.get(sort, SORTS["new"])
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"SELECT COUNT(*) FROM grants WHERE {where}", params) as cur:
            total = (await cur.fetchone())[0]
        if cursor and sort == "new":
            query = f"SELECT * FROM grants WHERE {where} AND id < ? ORDER BY {order} LIMIT ?"
            page_params = params + [cursor, limit]
        else:
            query = f"SELECT * FROM grants WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?"
            page_params = params + [limit if limit is not None else -1, offset]
        async with db.execute(query, page_params) as cur:
            return [dict(row) for row in await cur.fetchall()], total


async def get_grants_filtered(category: str, degree: str, limit=None, offset: int = 0) -> list[dict]:
    rows, _ = await get_grants_page(category, degree, limit=limit, offset=offset)
    return rows


async def count_grants_filtered(category: str, degree: str) -> int:
    where, params = _grant_filters(category, degree)
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(f"SELECT COUNT(*) FROM grants WHERE {where}", params) as cursor:
            return (await cursor.fetchone())[0]


async def get_active_countries() -> list:
    """Страны, по которым есть активные зарубежные гранты — для фильтра «Страна»."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT country_code, COUNT(*) FROM grants WHERE record_status = 'active' AND is_domestic = 0 "
            "AND country_code IS NOT NULL GROUP BY country_code ORDER BY COUNT(*) DESC, country_code"
        ) as cursor:
            return [{"code": r[0], "count": r[1]} for r in await cursor.fetchall()]


async def get_grant_by_id(grant_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM grants WHERE id = ?", (grant_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def set_grant_active(grant_id: int, is_active: bool):
    """Ручное снятие/возврат. Снятую вручную запись сканер сам обратно не публикует."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE grants SET is_active = ?, record_status = ?, archived_reason = ? WHERE id = ?",
            (1, "active", None, grant_id) if is_active else (0, "archived", "manual", grant_id),
        )
        await db.commit()


async def get_all_grants_light() -> list[tuple]:
    """(name, link, id) всех грантов — для дедупликации при сканировании."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT name, link, id FROM grants") as cursor:
            rows = await cursor.fetchall()
            return [(r[0], r[1], r[2]) for r in rows]


async def get_recent_grants(limit: int = 10) -> list:
    """Последние найденные активные гранты — для живой ленты на лендинге."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, category, country_code, degree, deadline, deadline_date, status, source, first_seen "
            "FROM grants WHERE is_active = 1 ORDER BY COALESCE(first_seen, '') DESC, id DESC LIMIT ?", (limit,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_all_active_grants() -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM grants WHERE is_active = 1") as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def _synonyms_for(db, keyword: str) -> dict:
    """{слово запроса: [полные названия]} по словарю админки: «nu» -> [«Nazarbayev University», «Назарбаев Университет»]."""
    words = keyword.lower().split()
    out = {}
    for phrase in {keyword.lower()} | set(words):
        async with db.execute(
            "SELECT canonical FROM synonyms WHERE alias_norm = ? OR lower(canonical) = ?", (phrase, phrase)
        ) as cursor:
            for (canonical,) in await cursor.fetchall():
                async with db.execute("SELECT alias FROM synonyms WHERE canonical = ?", (canonical,)) as cur2:
                    aliases = [r[0] for r in await cur2.fetchall() if len(r[0]) >= 4]
                for w in (phrase.split() if phrase != keyword.lower() else words):
                    out.setdefault(w, []).extend([canonical] + aliases)
    return out


async def search_grants(keyword: str, limit: int = 5, scope: str = "all") -> list[dict]:
    """Поиск по каталогу с пониманием словоформ, направлений, стран и опечаток (см. core/search.py).

    Раздел (Казахстан / зарубеж) и страна — это поля базы, а не текст: слово «Казахстан» в описании
    зарубежного гранта не подмешивает его в выдачу.
    """
    from core.search import rank
    keyword = " ".join(keyword.split())
    if not keyword:
        return []
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        synonyms = await _synonyms_for(db, keyword)
        async with db.execute(
            f"SELECT * FROM grants WHERE {_scope_sql(scope)} AND record_status = 'active' ORDER BY id DESC"
        ) as cursor:
            rows = [dict(r) for r in await cursor.fetchall()]
    return rank(rows, keyword, limit, synonyms)


def normalize_link(link: str) -> str:
    link = link.strip().lower()
    link = link.split("?")[0]
    for prefix in ("https://www.", "http://www.", "https://", "http://"):
        if link.startswith(prefix):
            link = link[len(prefix):]
            break
    return link.rstrip("/")


def link_domain(link: str) -> str:
    return normalize_link(link).split("/")[0]


def find_duplicate_grant(existing: list[tuple], name: str, link: str, threshold: float = 0.9):
    """Возвращает id дубликата (или True, если у записи нет id), иначе None.

    Дубликат — та же ссылка, либо очень похожее имя на том же домене.
    Сравнивать имена между разными доменами нельзя: «Harvard University Scholarships»
    и «Stanford University Scholarships» похожи на 92%, но это разные гранты.
    """
    norm_link = normalize_link(link)
    domain = norm_link.split("/")[0]
    norm_name = name.strip().lower()
    for row in existing:
        ex_name, ex_link = row[0], row[1]
        ex_id = row[2] if len(row) > 2 else True
        ex_norm_link = normalize_link(ex_link)
        if ex_norm_link == norm_link:
            return ex_id
        if ex_norm_link.split("/")[0] != domain:
            continue
        ex_norm_name = ex_name.strip().lower()
        if ex_norm_name == norm_name:
            return ex_id
        if difflib.SequenceMatcher(None, norm_name, ex_norm_name).ratio() >= threshold:
            return ex_id
    return None


def is_duplicate_grant(existing: list[tuple], name: str, link: str, threshold: float = 0.9) -> bool:
    return find_duplicate_grant(existing, name, link, threshold) is not None


def status_by_dates(start_date, deadline_date, fallback: str = "unknown", today: str = None) -> str:
    """Статус приёма по датам: до application_start_date — upcoming, от неё до дедлайна — open."""
    if not start_date:
        return fallback
    today = today or datetime.date.today().isoformat()
    if today < start_date:
        return "upcoming"
    return "open" if not deadline_date or today <= deadline_date else fallback


def _shift_years(iso_date: str, years: int) -> str:
    d = datetime.date.fromisoformat(iso_date)
    try:
        return d.replace(year=d.year + years).isoformat()
    except ValueError:   # 29 февраля
        return d.replace(year=d.year + years, day=28).isoformat()


async def cleanup_expired_grants() -> int:
    """Ежедневная очистка. Возвращает число удалённых грантов.

    1. Ежегодные гранты (recurrence_period = 'yearly') с прошедшим дедлайном не удаляются:
       дедлайн и дата открытия переносятся на следующий год, статус — «скоро откроется».
    2. Гранты с прошедшим и подтверждённым (deadline_confirmed = 1) дедлайном удаляются насовсем
       (кроме бессрочных, is_ongoing = 1); избранное, напоминания и подписки уходят каскадом.
       Если дата была только оценкой модели и не найдена на странице — запись не удаляется,
       а уходит в очередь на проверку оператору.
    3. Статусы приёма пересчитываются по application_start_date.
    """
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT id, deadline_date, application_start_date FROM grants "
            "WHERE deadline_date < ? AND recurrence_period = 'yearly' AND COALESCE(is_ongoing, 0) = 0", (today,)
        ) as cursor:
            recurring = await cursor.fetchall()
        for grant_id, deadline, start in recurring:
            try:
                years = 1
                while _shift_years(deadline, years) < today:
                    years += 1
                new_deadline = _shift_years(deadline, years)
                new_start = _shift_years(start, years) if start else None
            except (ValueError, TypeError):
                continue   # дата в непонятном формате — оставляем запись как есть
            await db.execute(
                "UPDATE grants SET deadline_date = ?, application_start_date = ?, status = 'upcoming' WHERE id = ?",
                (new_deadline, new_start, grant_id),
            )
            # новый цикл приёма — напоминания и уведомления об открытии должны сработать заново
            await db.execute("DELETE FROM reminders_sent WHERE grant_id = ?", (grant_id,))
            await db.execute("UPDATE open_alerts SET notified_at = NULL WHERE grant_id = ?", (grant_id,))

        await db.execute(
            "UPDATE grants SET record_status = 'flagged_review', is_active = 0, "
            "review_note = 'Срок подачи (' || deadline_date || ') прошёл, но дата не найдена на странице гранта. "
            "Укажите верный дедлайн и одобрите — или отклоните' "
            "WHERE deadline_date < ? AND COALESCE(is_ongoing, 0) = 0 AND COALESCE(deadline_confirmed, 0) = 0 "
            "AND record_status = 'active'", (today,))
        expired = "deadline_date IS NOT NULL AND deadline_date < ? AND COALESCE(is_ongoing, 0) = 0 AND deadline_confirmed = 1"
        await db.execute(
            f"INSERT OR REPLACE INTO grant_tombstones (external_id, deadline_date, deleted_at) "
            f"SELECT external_id, deadline_date, ? FROM grants WHERE {expired} AND external_id IS NOT NULL", (now, today),
        )
        cursor = await db.execute(f"DELETE FROM grants WHERE {expired}", (today,))
        deleted = cursor.rowcount
        year_ago = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
        await db.execute("DELETE FROM grant_tombstones WHERE deleted_at < ?", (year_ago,))

        await db.execute(
            "UPDATE grants SET status = 'upcoming' WHERE application_start_date > ? AND status IS NOT 'upcoming'", (today,))
        await db.execute(
            "UPDATE grants SET status = 'open' WHERE application_start_date <= ? "
            "AND (deadline_date IS NULL OR deadline_date >= ?) AND status IS NOT 'open'", (today, today))
        await db.commit()
        return deleted


async def get_tombstones() -> dict:
    """{нормализованная ссылка: дедлайн} грантов, удалённых по истёкшему сроку."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT external_id, deadline_date FROM grant_tombstones") as cursor:
            return {r[0]: r[1] for r in await cursor.fetchall()}


async def drop_tombstone(external_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM grant_tombstones WHERE external_id = ?", (external_id,))
        await db.commit()


# --- Уведомления об открытии приёма ---

async def add_open_alert(user_id: int, grant_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO open_alerts (user_id, grant_id) VALUES (?, ?)", (user_id, grant_id))
        await db.commit()


async def remove_open_alert(user_id: int, grant_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM open_alerts WHERE user_id = ? AND grant_id = ?", (user_id, grant_id))
        await db.commit()


async def get_open_alert_ids(user_id: int) -> set:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT grant_id FROM open_alerts WHERE user_id = ?", (user_id,)) as cursor:
            return {r[0] for r in await cursor.fetchall()}


async def get_opened_alerts(user_id: int = None, only_unsent: bool = False) -> list:
    """Подписки, по которым приём уже открылся. only_unsent — те, о которых бот ещё не написал."""
    query = (
        "SELECT a.id AS alert_id, a.user_id AS user_id, g.id AS grant_id, g.name AS name, g.link AS link, "
        "g.deadline_date AS deadline_date FROM open_alerts a JOIN grants g ON g.id = a.grant_id "
        "WHERE g.record_status = 'active' AND g.status = 'open'"
    )
    params = []
    if user_id is not None:
        query += " AND a.user_id = ?"
        params.append(user_id)
    if only_unsent:
        query += " AND a.notified_at IS NULL"
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def mark_alert_notified(alert_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE open_alerts SET notified_at = ? WHERE id = ?",
                         (datetime.datetime.now().isoformat(timespec="seconds"), alert_id))
        await db.commit()


# --- Сохранение результатов сканера: upsert, очистка, журнал ---

_UPSERT_SQL = """
    INSERT INTO grants (category, degree, name, coverage, requirements, deadline, deadline_date, link, is_active,
                        source, status, first_seen, last_seen, country_code, provider_country, source_id,
                        external_id, data_hash, record_status, review_note, funding, missed_scans,
                        application_start_date, is_ongoing, recurrence_period, deadline_confirmed)
    VALUES (:category, :degree, :name, :coverage, :requirements, :deadline, :deadline_date, :link, :is_active,
            :source, :status, :now, :now, :country_code, :provider_country, :source_id,
            :external_id, :data_hash, :record_status, :review_note, :funding, 0,
            :application_start_date, :is_ongoing, :recurrence_period, :deadline_confirmed)
    ON CONFLICT (source_id, external_id) DO UPDATE SET
        name = excluded.name, coverage = excluded.coverage, requirements = excluded.requirements,
        deadline = excluded.deadline, deadline_date = excluded.deadline_date, status = excluded.status,
        degree = excluded.degree, funding = excluded.funding, data_hash = excluded.data_hash,
        application_start_date = excluded.application_start_date, is_ongoing = excluded.is_ongoing,
        recurrence_period = excluded.recurrence_period, deadline_confirmed = excluded.deadline_confirmed,
        last_seen = excluded.last_seen, missed_scans = 0
"""


async def upsert_scanned_grant(db, g: dict, now: str, dup_id: int = None) -> tuple:
    """Сохраняет найденный сканером грант: обновляет существующую запись вместо дубликата.

    -> (id, действие): created | updated | unchanged. Запись ищется по dup_id (нашёл дедупликатор)
    или по ключу (source_id, external_id). Страну и статус модерации у существующей записи не трогаем —
    их мог исправить оператор.
    """
    db.row_factory = aiosqlite.Row
    if dup_id is not None:
        query, args = "SELECT * FROM grants WHERE id = ?", (dup_id,)
    else:
        query, args = "SELECT * FROM grants WHERE source_id = ? AND external_id = ?", (g["source_id"], g["external_id"])
    async with db.execute(query, args) as cursor:
        row = await cursor.fetchone()

    if row is None:
        cursor = await db.execute(_UPSERT_SQL, {**g, "now": now, "is_active": 1 if g["record_status"] == "active" else 0})
        return cursor.lastrowid, "created"

    sets, params = ["last_seen = ?", "missed_scans = 0"], [now]
    action = "unchanged"
    # Текст обновляем только у записей сканера и только при точном совпадении ссылки:
    # стартовые записи написаны вручную, а «похожее имя на том же домене» — не повод переписывать
    same_link = normalize_link(row["link"]) == g["external_id"]
    if row["source_id"] == SOURCE_SCANNER and same_link and row["data_hash"] != g["data_hash"]:
        for field in ("name", "coverage", "requirements", "deadline", "deadline_date", "status", "degree", "funding",
                      "data_hash", "application_start_date", "is_ongoing", "recurrence_period", "deadline_confirmed"):
            sets.append(f"{field} = ?")
            params.append(g[field])
        action = "updated"
    # Возвращаем в каталог то, что сняла автоочистка (запись снова появилась у источника)
    if row["record_status"] == "archived" and row["archived_reason"] == "sweep":
        sets += ["record_status = 'active'", "is_active = 1", "archived_reason = NULL"]
        action = "updated"
    sets.append("link_failures = 0")   # страница только что открылась при проверке ссылки
    await db.execute(f"UPDATE grants SET {', '.join(sets)} WHERE id = ?", params + [row["id"]])
    return row["id"], action


async def sweep_stale_grants(checked_sources: list, run_started: str, max_misses: int) -> int:
    """Mark-and-sweep: архивирует записи, которые источник перестал отдавать. Возвращает число снятых.

    Источник здесь — веб-поиск, он не обязан каждый раз возвращать ту же страницу. Поэтому запись,
    не встретившаяся в этом запуске (last_seen < run_started), получает «пропуск», а в архив уходит
    только после max_misses пропусков подряд. Источники, поиск по которым упал, не трогаем.
    """
    if not checked_sources:
        return 0
    async with aiosqlite.connect(DB_NAME) as db:
        await db.executemany(
            "UPDATE grants SET missed_scans = COALESCE(missed_scans, 0) + 1 "
            "WHERE source_id = ? AND source = ? AND record_status = 'active' AND (last_seen IS NULL OR last_seen < ?)",
            [(SOURCE_SCANNER, name, run_started) for name in checked_sources],
        )
        cursor = await db.execute(
            "UPDATE grants SET record_status = 'archived', is_active = 0, archived_reason = 'sweep' "
            "WHERE source_id = ? AND record_status = 'active' AND missed_scans >= ?",
            (SOURCE_SCANNER, max_misses),
        )
        await db.commit()
        return cursor.rowcount


async def log_scan_run(source_id: str, started_at: str, finished_at: str, counts: dict, error: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT INTO scan_runs (source_id, started_at, finished_at, created, updated, unchanged, flagged,
                                   archived, errors, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source_id, started_at, finished_at, counts.get("created", 0), counts.get("updated", 0),
             counts.get("unchanged", 0), counts.get("flagged", 0), counts.get("archived", 0),
             counts.get("errors", 0), error),
        )
        await db.commit()


async def get_scan_runs(limit: int = 20) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT ?", (limit,)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_data_version() -> int:
    """Меняется после каждого запуска сканера — по нему сайт сбрасывает кэш, даже если сканировал бот."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COALESCE(MAX(id), 0) FROM scan_runs") as cursor:
            return (await cursor.fetchone())[0]


# --- Модерация: очередь на проверку и словарь синонимов ---

async def get_review_queue(limit: int = 50) -> list:
    """Записи, которые ждут решения оператора и в каталоге пока не видны."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM grants WHERE record_status IN ('flagged_review', 'draft') ORDER BY id DESC LIMIT ?", (limit,)
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def review_grant(grant_id: int, approve: bool, country_code: str = None, set_country: bool = False,
                       deadline_date: str = None) -> bool:
    """Решение оператора. При одобрении можно исправить страну (set_country=True; None = несколько стран)
    и дедлайн; одобренная дата считается подтверждённой."""
    async with aiosqlite.connect(DB_NAME) as db:
        if not approve:
            cursor = await db.execute(
                "UPDATE grants SET record_status = 'archived', is_active = 0, archived_reason = 'manual' "
                "WHERE id = ? AND record_status IN ('flagged_review', 'draft')", (grant_id,))
        else:
            sets = ["record_status = 'active'", "is_active = 1", "archived_reason = NULL", "review_note = NULL",
                    "deadline_confirmed = 1"]
            params = []
            if set_country:
                sets += ["country_code = ?", "category = ?"]
                params += [country_code, "kz" if country_code == "KZ" else "abroad"]
            if deadline_date:
                sets += ["deadline_date = ?", "deadline = ?"]
                params += [deadline_date, deadline_date]
            cursor = await db.execute(
                f"UPDATE grants SET {', '.join(sets)} WHERE id = ? AND record_status IN ('flagged_review', 'draft')",
                params + [grant_id])
        await db.commit()
        return cursor.rowcount > 0


# --- Проверка ссылок и резервные копии ---

async def get_links_to_check() -> list:
    """Активные гранты сканера: (id, link) — раз в неделю проверяем, что страницы живы."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT id, link FROM grants WHERE record_status = 'active' AND source_id = ?", (SOURCE_SCANNER,)
        ) as cursor:
            return [(r[0], r[1]) for r in await cursor.fetchall()]


async def record_link_check(results: list, max_failures: int = 2) -> int:
    """results — [(id, ok)]. Ссылка, не открывшаяся max_failures проверок подряд, уводит грант в архив."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.executemany("UPDATE grants SET link_failures = 0 WHERE id = ?", [(gid,) for gid, ok in results if ok])
        await db.executemany("UPDATE grants SET link_failures = COALESCE(link_failures, 0) + 1 WHERE id = ?",
                             [(gid,) for gid, ok in results if not ok])
        cursor = await db.execute(
            "UPDATE grants SET record_status = 'archived', is_active = 0, archived_reason = 'dead_link' "
            "WHERE record_status = 'active' AND link_failures >= ?", (max_failures,))
        await db.commit()
        return cursor.rowcount


BACKUP_DIR = DATA_DIR / "backups"
BACKUP_KEEP = int(os.getenv("BACKUP_KEEP", "7"))


def _backup_sync() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"grants-{datetime.date.today().isoformat()}.db"
    src, dst = sqlite3.connect(DB_NAME), sqlite3.connect(str(path))
    try:
        src.backup(dst)   # корректная копия даже во время работы бота и сайта
    finally:
        dst.close()
        src.close()
    for old in sorted(BACKUP_DIR.glob("grants-*.db"))[:-BACKUP_KEEP]:
        old.unlink(missing_ok=True)
    return path


async def backup_database() -> Path:
    """Копия базы в data/backups/grants-ГГГГ-ММ-ДД.db; хранится последние BACKUP_KEEP штук."""
    import asyncio
    return await asyncio.get_running_loop().run_in_executor(None, _backup_sync)


async def get_synonyms() -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, canonical, alias FROM synonyms ORDER BY canonical, alias") as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def add_synonym(canonical: str, alias: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute("INSERT INTO synonyms (canonical, alias, alias_norm) VALUES (?, ?, ?)",
                             (canonical, alias, alias.lower()))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def delete_synonym(synonym_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM synonyms WHERE id = ?", (synonym_id,))
        await db.commit()


async def record_monitor_result(name: str, kind: str, checked_at: str, snippets: int,
                                found: int, new: int, error: str = None):
    """Запоминает результат проверки одного источника (университета / программы)."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT INTO monitor_sources (name, kind, last_checked, last_snippets, last_found, last_new, total_new, last_error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                kind = excluded.kind,
                last_checked = excluded.last_checked,
                last_snippets = excluded.last_snippets,
                last_found = excluded.last_found,
                last_new = excluded.last_new,
                total_new = monitor_sources.total_new + excluded.last_new,
                last_error = excluded.last_error
            """,
            (name, kind, checked_at, snippets, found, new, new, error),
        )
        await db.commit()


async def get_monitor_summary() -> dict:
    """Сводка по мониторингу: источники по видам, лучшие источники, активные гранты по статусу."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT kind, COUNT(*) AS n, MAX(last_checked) AS last, "
            "SUM(last_found) AS found, SUM(last_new) AS new, SUM(total_new) AS total, "
            "SUM(CASE WHEN last_error IS NOT NULL THEN 1 ELSE 0 END) AS errors "
            "FROM monitor_sources GROUP BY kind"
        ) as cursor:
            by_kind = {r["kind"]: dict(r) for r in await cursor.fetchall()}
        async with db.execute(
            "SELECT name, kind, total_new, last_found FROM monitor_sources "
            "WHERE total_new > 0 ORDER BY total_new DESC, last_found DESC LIMIT 10"
        ) as cursor:
            top = [dict(r) for r in await cursor.fetchall()]
        async with db.execute(
            "SELECT source, COUNT(*) AS n FROM grants WHERE is_active = 1 AND source IS NOT NULL "
            "GROUP BY source ORDER BY n DESC LIMIT 10"
        ) as cursor:
            active_by_source = [dict(r) for r in await cursor.fetchall()]
        async with db.execute(
            "SELECT status, COUNT(*) AS n FROM grants WHERE is_active = 1 GROUP BY status"
        ) as cursor:
            by_status = {(r["status"] or "unknown"): r["n"] for r in await cursor.fetchall()}
    return {"by_kind": by_kind, "top": top, "active_by_source": active_by_source, "by_status": by_status}


# --- Избранное ---

async def add_favorite(user_id: int, grant_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute("INSERT INTO favorites (user_id, grant_id) VALUES (?, ?)", (user_id, grant_id))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_favorite(user_id: int, grant_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM favorites WHERE user_id = ? AND grant_id = ?", (user_id, grant_id))
        await db.commit()


async def is_favorite(user_id: int, grant_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND grant_id = ?", (user_id, grant_id)
        ) as cursor:
            return (await cursor.fetchone()) is not None


async def get_user_favorites(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT g.* FROM grants g
            JOIN favorites f ON f.grant_id = g.id
            WHERE f.user_id = ?
            ORDER BY f.added_at DESC
            """,
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_favorites_with_deadlines() -> list[dict]:
    """Избранные гранты с известной датой дедлайна — для напоминаний."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT f.user_id AS user_id, g.id AS grant_id, g.name AS name,
                   g.link AS link, g.deadline_date AS deadline_date
            FROM favorites f
            JOIN grants g ON g.id = f.grant_id
            WHERE g.is_active = 1 AND g.deadline_date IS NOT NULL
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def mark_reminder_sent(user_id: int, grant_id: int, days_before: int) -> bool:
    """Возвращает True, если напоминание отправляется впервые (можно слать)."""
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute(
                "INSERT INTO reminders_sent (user_id, grant_id, days_before) VALUES (?, ?, ?)",
                (user_id, grant_id, days_before),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


# --- События (аналитика + rate limiting) ---

def _to_utc_str(local_dt: datetime.datetime) -> str:
    """Локальное наивное время -> строка UTC в формате SQLite CURRENT_TIMESTAMP."""
    utc = local_dt.astimezone().astimezone(datetime.timezone.utc)
    return utc.replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")


async def log_event(user_id: int, event_type: str, payload: dict = None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO events (user_id, event_type, payload) VALUES (?, ?, ?)",
            (user_id, event_type, json.dumps(payload, ensure_ascii=False) if payload else None),
        )
        await db.commit()


async def count_events_today(user_id: int, event_type: str) -> int:
    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM events WHERE user_id = ? AND event_type = ? AND created_at >= ?",
            (user_id, event_type, _to_utc_str(today_start)),
        ) as cursor:
            return (await cursor.fetchone())[0]


async def get_events_summary(days: int = 7) -> dict:
    since = _to_utc_str(datetime.datetime.now() - datetime.timedelta(days=days))
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT event_type, COUNT(*) FROM events WHERE created_at >= ? GROUP BY event_type",
            (since,),
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}


async def get_active_users_count(days: int = 7) -> int:
    since = _to_utc_str(datetime.datetime.now() - datetime.timedelta(days=days))
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM events WHERE created_at >= ?", (since,)
        ) as cursor:
            return (await cursor.fetchone())[0]


SITE_UID_MIN = 10**12   # посетители сайта без Telegram получают случайный id от 13 знаков; Telegram id короче


async def get_audience_stats(days_series: int = 14) -> dict:
    """Сколько людей пользуются ботом и сайтом. Только для администратора.

    users       — все известные пользователи: Telegram, посетители сайта (по cookie), аккаунты сайта, привязанные
    active      — уникальные пользователи с событиями за сегодня / 7 / 30 дней, с разбивкой бот / сайт
    new         — новые пользователи за сегодня / 7 / 30 дней
    daily       — последние N дней: новые и активные за день (для графика)
    """
    now = datetime.datetime.now()
    today = _to_utc_str(now.replace(hour=0, minute=0, second=0, microsecond=0))
    since = {"today": today, "7d": _to_utc_str(now - datetime.timedelta(days=7)), "30d": _to_utc_str(now - datetime.timedelta(days=30))}
    out = {"users": {}, "active": {}, "new": {}, "funnel": {}, "daily": [], "recent": []}
    async with aiosqlite.connect(DB_NAME) as db:
        async def one(sql, *params):
            async with db.execute(sql, params) as cur:
                return (await cur.fetchone())[0]

        out["users"] = {
            "total": await one("SELECT COUNT(*) FROM users"),
            "telegram": await one("SELECT COUNT(*) FROM users WHERE user_id < ?", SITE_UID_MIN),
            "site": await one("SELECT COUNT(*) FROM users WHERE user_id >= ?", SITE_UID_MIN),
            "accounts": await one("SELECT COUNT(*) FROM web_accounts"),
            "linked": await one("SELECT COUNT(*) FROM users WHERE linked_at IS NOT NULL"),
            "subscribed": await one("SELECT COUNT(*) FROM users WHERE subscribed = 1 AND user_id < ?", SITE_UID_MIN),
            "with_profile": await one("SELECT COUNT(*) FROM users WHERE ielts IS NOT NULL OR gpa IS NOT NULL OR field_of_interest IS NOT NULL"),
            "with_favorites": await one("SELECT COUNT(DISTINCT user_id) FROM favorites"),
        }
        for key, ts in since.items():
            out["active"][key] = {
                "total": await one("SELECT COUNT(DISTINCT user_id) FROM events WHERE created_at >= ?", ts),
                "telegram": await one("SELECT COUNT(DISTINCT user_id) FROM events WHERE created_at >= ? AND user_id < ?", ts, SITE_UID_MIN),
                "site": await one("SELECT COUNT(DISTINCT user_id) FROM events WHERE created_at >= ? AND user_id >= ?", ts, SITE_UID_MIN),
            }
            out["new"][key] = await one("SELECT COUNT(*) FROM users WHERE joined_at >= ?", ts)
            # воронка: кто зашёл на сайт, кто пришёл из бота, кто зарегистрировался / вошёл, кто нажал «сайт» в боте
            out["funnel"][key] = {
                "visitors": await one("SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = 'web_visit' AND created_at >= ?", ts),
                "visits": await one("SELECT COUNT(*) FROM events WHERE event_type = 'web_visit' AND created_at >= ?", ts),
                "from_bot": await one("SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = 'web_visit' AND payload LIKE '%\"from\": \"bot\"%' AND created_at >= ?", ts),
                "site_open": await one("SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = 'site_open' AND created_at >= ?", ts),
                "registered": await one("SELECT COUNT(*) FROM events WHERE event_type = 'register' AND created_at >= ?", ts),
                "logins": await one("SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = 'login' AND created_at >= ?", ts),
                "bot_starts": await one("SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = 'start' AND created_at >= ?", ts),
            }
        # по дням: события и регистрации сгруппированы по дате (UTC)
        start = _to_utc_str(now - datetime.timedelta(days=days_series - 1)).split(" ")[0]
        async with db.execute("SELECT substr(created_at, 1, 10) d, COUNT(DISTINCT user_id) FROM events WHERE created_at >= ? GROUP BY d", (start,)) as cur:
            active_by_day = {r[0]: r[1] for r in await cur.fetchall()}
        async with db.execute("SELECT substr(joined_at, 1, 10) d, COUNT(*) FROM users WHERE joined_at >= ? GROUP BY d", (start,)) as cur:
            new_by_day = {r[0]: r[1] for r in await cur.fetchall()}
        # кто заходил последним: последние события «вход / регистрация / заход / переход», по одному на пользователя
        async with db.execute(
            """SELECT e.user_id, e.event_type, e.payload, MAX(e.created_at) AS t, u.linked_at IS NOT NULL, a.email
               FROM events e LEFT JOIN users u ON u.user_id = e.user_id LEFT JOIN web_accounts a ON a.uid = e.user_id
               WHERE e.event_type IN ('web_visit', 'register', 'login', 'site_open', 'start', 'telegram_linked')
               GROUP BY e.user_id ORDER BY t DESC LIMIT 25"""
        ) as cur:
            for uid, et, payload, t, linked, email in await cur.fetchall():
                src = "telegram" if uid < SITE_UID_MIN else "site"
                try:
                    came_from = (json.loads(payload) or {}).get("from") if payload else None
                except ValueError:
                    came_from = None
                out["recent"].append({"user_id": uid, "source": src, "event": et, "from": came_from, "at": t,
                                      "linked": bool(linked), "email": email})
    first = datetime.date.fromisoformat(start)
    for i in range(days_series):
        d = (first + datetime.timedelta(days=i)).isoformat()
        out["daily"].append({"date": d, "active": active_by_day.get(d, 0), "new": new_by_day.get(d, 0)})
    return out


# --- Ответы ИИ и фидбек ---

async def save_ai_answer(user_id: int, question: str, answer: str) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO ai_answers (user_id, question, answer) VALUES (?, ?, ?)",
            (user_id, question, answer),
        )
        await db.commit()
        return cursor.lastrowid


async def set_answer_rating(answer_id: int, rating: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE ai_answers SET rating = ? WHERE id = ?", (rating, answer_id))
        await db.commit()