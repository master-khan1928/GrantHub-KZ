"""Тесты ядра и API. Запуск из корня проекта:  .venv\\Scripts\\python.exe -m unittest -v

База создаётся во временной папке, сеть и модель не нужны.
"""
import asyncio
import datetime
import os
import random
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = tempfile.mkdtemp(prefix="granthub-test-")
os.environ["DATA_DIR"] = _TMP
os.environ["LOGS_DIR"] = os.path.join(_TMP, "logs")
os.environ["WEB_ADMIN_TOKEN"] = "test-token"
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.pop("GROQ_API_KEY", None)

import aiosqlite  # noqa: E402

from core import ai_scanner, database as db  # noqa: E402
from core.dates import date_in_text, page_text  # noqa: E402
from core.geo import flag_emoji, normalize_country, resolve_location  # noqa: E402

TODAY = datetime.date.today()


def day(n: int) -> str:
    return (TODAY + datetime.timedelta(days=n)).isoformat()


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def candidate(**over) -> dict:
    g = dict(name="Test grant — Germany", link="https://www.example-uni.de/scholarship", source="DAAD scholarship",
             category="abroad", country_code="DE", provider_country="DE", degree="master", funding="full",
             status="unknown", coverage="Full tuition and stipend", requirements="IELTS 6.5", deadline="1 March",
             deadline_date=day(90), deadline_confirmed=True)
    g.update(over)
    return g


async def save_candidates(cands: list) -> list:
    existing = await db.get_all_grants_light()
    out = []
    async with aiosqlite.connect(db.DB_NAME) as conn:
        for g in cands:
            record = ai_scanner._prepare_record(g)
            dup = db.find_duplicate_grant(existing, record["name"], record["link"])
            gid, action = await db.upsert_scanned_grant(conn, record, "2026-01-01T00:00:00", dup)
            if action == "created":
                existing.append((record["name"], record["link"], gid))
            out.append((gid, action, record))
        await conn.commit()
    return out


class TextTests(unittest.TestCase):
    def test_clean_source(self):
        from core.text import clean_source
        self.assertEqual(clean_source("scholarships for kazakhstan students deadline 2026", "https://www.daad.de/x"), "daad.de")
        self.assertEqual(clean_source("Nazarbayev University", "https://nu.edu.kz"), "Nazarbayev University")
        self.assertEqual(clean_source("Министерство образования РК", "https://testcenter.kz"), "Министерство образования РК")
        self.assertEqual(clean_source("Bolashak scholarship", None), "Bolashak scholarship")
        self.assertIsNone(clean_source("", "https://x.kz"))
        self.assertIsNone(clean_source("grant for students in kazakhstan", None))


class GeoTests(unittest.TestCase):
    def test_normalize_country(self):
        self.assertEqual(normalize_country(" de "), "DE")
        self.assertEqual(normalize_country("UK"), "GB")
        self.assertIsNone(normalize_country("EU"))
        self.assertIsNone(normalize_country("Germany"))

    def test_flag_emoji(self):
        self.assertEqual(flag_emoji("kz"), "🇰🇿")
        self.assertEqual(flag_emoji(None), "")

    def test_source_beats_model(self):
        cc, _, doubts = resolve_location("KZ", None, "kz", "Harvard University", "harvard.edu", "X")
        self.assertEqual(cc, "US")
        self.assertTrue(doubts)

    def test_bolashak_is_outbound(self):
        cc, provider, doubts = resolve_location("GB", "KZ", "kz", "Bolashak scholarship", "bolashak.gov.kz", "Болашак")
        self.assertEqual((cc, provider, doubts), ("GB", "KZ", []))

    def test_kz_without_evidence_is_doubtful(self):
        cc, _, doubts = resolve_location(None, None, "kz", "broad query", "example.com", "X")
        self.assertEqual(cc, "KZ")
        self.assertTrue(doubts)


class DateTests(unittest.TestCase):
    def test_formats(self):
        text = page_text("<html><script>x=1</script><p>Deadline: 15 January 2027. Also 15.01.2027</p></html>")
        self.assertNotIn("x=1", text)
        for fmt in ("15 january 2027", "january 15, 2027", "15.01.2027", "2027-01-15", "15 января 2027", "15 қаңтар 2027", "Jan. 15th, 2027"):
            self.assertTrue(date_in_text("2027-01-15", fmt.lower()), fmt)
        self.assertFalse(date_in_text("2027-01-15", "deadline 16 january 2027"))
        self.assertFalse(date_in_text(None, "anything"))


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        if os.path.exists(db.DB_NAME):
            os.remove(db.DB_NAME)
        run(db.init_db())
        run(db.init_db())  # повторный запуск не ломает миграции

    def rows(self, sql, *params):
        c = sqlite3.connect(db.DB_NAME)
        try:
            return c.execute(sql, params).fetchall()
        finally:
            c.close()

    def test_seed_location(self):
        self.assertEqual(self.rows("SELECT COUNT(*) FROM grants WHERE is_domestic = 1 AND country_code = 'KZ'")[0][0],
                         self.rows("SELECT COUNT(*) FROM grants WHERE category = 'kz'")[0][0])
        bolashak = self.rows("SELECT country_code, provider_country, is_domestic FROM grants WHERE name LIKE '%Болашак%'")[0]
        self.assertEqual(bolashak, (None, "KZ", 0))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM grants WHERE source_id = 'seed' AND deadline_confirmed = 1")[0][0],
                         self.rows("SELECT COUNT(*) FROM grants WHERE source_id = 'seed'")[0][0])

    def test_is_domestic_is_generated(self):
        with self.assertRaises(sqlite3.OperationalError):
            self.rows("UPDATE grants SET is_domestic = 1")

    def test_scopes_do_not_mix(self):
        kz = run(db.count_grants_filtered("kz", "all"))
        abroad = run(db.count_grants_filtered("abroad", "all"))
        self.assertEqual(kz + abroad, run(db.count_grants_filtered("all", "all")))
        self.assertTrue(all(g["is_domestic"] == 1 for g in run(db.get_grants_filtered("kz", "all"))))

    def test_upsert_and_update(self):
        (gid, action, _), = run(save_candidates([candidate()]))
        self.assertEqual(action, "created")
        (gid2, action2, _), = run(save_candidates([candidate(coverage="Changed")]))
        self.assertEqual((gid2, action2), (gid, "updated"))
        self.assertEqual(self.rows("SELECT coverage, deadline_confirmed FROM grants WHERE id = ?", gid)[0], ("Changed", 1))

    def test_doubtful_goes_to_review(self):
        (gid, _, record), = run(save_candidates([candidate(source="Harvard University", category="kz", country_code="KZ")]))
        self.assertEqual(record["record_status"], "flagged_review")
        self.assertEqual(len(run(db.get_review_queue())), 1)
        self.assertTrue(run(db.review_grant(gid, True, "US", True, day(10))))
        self.assertEqual(self.rows("SELECT record_status, country_code, deadline_date, deadline_confirmed FROM grants WHERE id = ?", gid)[0],
                         ("active", "US", day(10), 1))

    def test_search_country_is_filter_not_text(self):
        run(save_candidates([candidate(name="Kazakhstan students welcome", requirements="citizens of Kazakhstan")]))
        ids = {g["country_code"] for g in run(db.search_grants("казахстан", 50))}
        self.assertEqual(ids, {"KZ"})
        self.assertEqual(run(db.search_grants("германия", 50))[0]["country_code"], "DE")
        found = run(db.search_grants("NU", 50))
        self.assertTrue(found and all("nazarbayev" in g["name"].lower() or "назарбаев" in g["name"].lower() for g in found))

    def test_search_understands_forms_topics_and_typos(self):
        names = lambda q, scope="all": [g["name"] for g in run(db.search_grants(q, 10, scope))]
        self.assertTrue(all("КазНМУ" in n for n in names("медицинские")) and names("медицинские"))
        self.assertTrue(any("IT" in n or "IITU" in n for n in names("айти")))
        self.assertEqual(names("германя"), names("германия"))          # опечатка
        self.assertTrue(names("германия") and all("Немецк" in n for n in names("германия")))
        self.assertTrue(all("КБТУ" in n for n in names("кбту")) and names("кбту"))
        self.assertTrue(all("Nazarbayev" in n or "Назарбаев" in n for n in names("NU")) and names("NU"))
        self.assertEqual(names("казахстан", "abroad"), [])
        self.assertEqual(names("asdfgh"), [])

    def test_cleanup_deletes_only_confirmed(self):
        saved = run(save_candidates([
            candidate(name="Alpha programme", link="https://a.example.de/1", source=None, deadline_date=day(1)),
            candidate(name="Beta fellowship award", link="https://a.example.de/2", source=None, deadline_date=day(1), deadline_confirmed=False),
            candidate(name="Gamma yearly stipend", link="https://a.example.de/3", deadline_date=day(1)),
            candidate(name="Delta ongoing support", link="https://a.example.de/4", source=None, is_ongoing=True),
        ]))
        ids = [s[0] for s in saved]
        c = sqlite3.connect(db.DB_NAME)
        c.execute("UPDATE grants SET deadline_date = ? WHERE id IN (?, ?, ?)", (day(-5), *ids[:3]))
        c.execute("INSERT INTO favorites (user_id, grant_id) VALUES (1, ?)", (ids[0],))
        c.commit()
        c.close()
        self.assertEqual(run(db.cleanup_expired_grants()), 1)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM grants WHERE id = ?", ids[0])[0][0], 0)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM favorites WHERE grant_id = ?", ids[0])[0][0], 0)
        self.assertEqual(self.rows("SELECT record_status FROM grants WHERE id = ?", ids[1])[0][0], "flagged_review")
        self.assertGreater(self.rows("SELECT deadline_date FROM grants WHERE id = ?", ids[2])[0][0], TODAY.isoformat())
        self.assertEqual(self.rows("SELECT record_status FROM grants WHERE id = ?", ids[3])[0][0], "active")
        self.assertIn("a.example.de/1", run(db.get_tombstones()))

    def test_sweep_needs_repeated_misses(self):
        (gid, _, _), = run(save_candidates([candidate()]))
        for i in range(2):
            self.assertEqual(run(db.sweep_stale_grants(["DAAD scholarship"], "2026-02-01T00:00:00", 3)), 0)
        self.assertEqual(run(db.sweep_stale_grants(["DAAD scholarship"], "2026-02-01T00:00:00", 3)), 1)
        self.assertEqual(self.rows("SELECT record_status, archived_reason FROM grants WHERE id = ?", gid)[0], ("archived", "sweep"))
        (_, action, _), = run(save_candidates([candidate()]))
        self.assertEqual(action, "updated")
        self.assertEqual(self.rows("SELECT record_status FROM grants WHERE id = ?", gid)[0][0], "active")

    def test_dead_links_archive(self):
        (gid, _, _), = run(save_candidates([candidate()]))
        self.assertEqual(run(db.record_link_check([(gid, False)])), 0)
        self.assertEqual(run(db.record_link_check([(gid, False)])), 1)
        self.assertEqual(self.rows("SELECT archived_reason FROM grants WHERE id = ?", gid)[0][0], "dead_link")

    def test_backup(self):
        path = run(db.backup_database())
        self.assertTrue(path.exists() and path.stat().st_size > 0)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(db.DB_NAME):
            os.remove(db.DB_NAME)
        run(db.init_db())
        run(save_candidates([candidate(application_start_date=day(5), deadline_date=day(60))]))
        from fastapi.testclient import TestClient
        from website.web import app
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_catalog_scopes_and_validation(self):
        kz = self.client.get("/api/grants?category=kz&limit=50").json()
        abroad = self.client.get("/api/grants?category=abroad&limit=50").json()
        self.assertTrue(all(g["category"] == "kz" for g in kz["items"]))
        self.assertTrue(all(g["category"] == "abroad" for g in abroad["items"]))
        self.assertEqual(self.client.get("/api/grants?category=zz").status_code, 422)
        self.assertEqual(self.client.get("/api/grants?country=deu").status_code, 422)
        self.assertEqual(self.client.get("/api/grants?deadline=closed").status_code, 422)

    def test_pagination_cursor_and_offset(self):
        first = self.client.get("/api/grants?category=all&limit=5").json()
        second = self.client.get(f"/api/grants?category=all&limit=5&cursor={first['next_cursor']}").json()
        self.assertFalse({g["id"] for g in first["items"]} & {g["id"] for g in second["items"]})
        by_deadline = self.client.get("/api/grants?category=all&sort=deadline&limit=5").json()
        self.assertIsNone(by_deadline["next_cursor"])
        self.assertEqual(by_deadline["next_offset"], 5)

    def test_upcoming_alert_and_grant_page(self):
        gid = self.client.get("/api/grants?category=abroad&deadline=upcoming").json()["items"][0]["id"]
        self.assertEqual(self.client.post(f"/api/alerts/{gid}").status_code, 200)
        self.assertIn(gid, self.client.get("/api/me").json()["alerts"])
        page = self.client.get(f"/grant/{gid}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Test grant", page.text)
        self.assertIn(f"/grant/{gid}", self.client.get("/sitemap.xml").text)

    def test_match_by_profile(self):
        from core.matching import match_grants, score_grant
        g = {"name": "IT grant", "coverage": "", "requirements": "IELTS 6.5, GPA 3.5", "status": "open", "deadline_date": None}
        sc, why, gaps = score_grant(g, {"ielts": 6.0, "gpa": 3.7, "field_of_interest": "IT"})
        self.assertEqual(gaps, {"ielts": 0.5})
        self.assertIn("field", why)
        res = match_grants([g, dict(g, requirements="IELTS 6.0")], {"ielts": 6.0, "gpa": None, "field_of_interest": None})
        self.assertEqual(len(res["matches"]), 1)
        self.assertEqual(len(res["near"]), 1)
        # API: без профиля — пусто, с профилем — списки
        self.assertFalse(self.client.get("/api/match").json()["has_profile"])
        self.client.post("/api/profile", json={"ielts": 9.0, "gpa": None, "field_of_interest": None})
        d = self.client.get("/api/match").json()
        self.assertTrue(d["has_profile"])
        self.assertTrue(d["items"])
        self.assertIn("gaps", d["items"][0])

    def test_link_from_site_code_used_in_bot(self):
        gid = self.client.get("/api/grants?category=all&limit=1").json()["items"][0]["id"]
        self.client.post(f"/api/favorites/{gid}")
        self.assertFalse(self.client.get("/api/me").json()["telegram_linked"])
        code = self.client.post("/api/link/code").json()["code"]
        self.assertFalse(self.client.get(f"/api/link/status?code={code}").json()["linked"])
        tg_id = 424242
        self.assertTrue(run(db.consume_link_code(code, "web", tg_id))["ok"])          # бот принял код
        self.assertEqual(run(db.consume_link_code(code, "web", tg_id))["error"], "bad_code")  # повторно — нельзя
        self.assertTrue(self.client.get(f"/api/link/status?code={code}").json()["linked"])
        me = self.client.get("/api/me").json()
        self.assertEqual(me["user_id"], tg_id)
        self.assertTrue(me["telegram_linked"])
        self.assertIn(gid, {g["id"] for g in self.client.get("/api/favorites").json()["items"]})
        self.assertEqual(self.client.post("/api/link/code").status_code, 409)         # уже привязан
        self.client.cookies.clear()

    def test_link_from_bot_code_entered_on_site(self):
        tg_id = 515151
        run(db.add_user(tg_id))
        run(db.set_user_profile(tg_id, ielts=7.0))
        code = run(db.create_link_code("tg", tg_id))["code"]
        self.assertEqual(self.client.post("/api/link/confirm", json={"code": "ZZZZZZ"}).status_code, 400)
        self.assertEqual(self.client.post("/api/link/confirm", json={"code": code.lower()}).status_code, 200)
        me = self.client.get("/api/me").json()
        self.assertEqual(me["user_id"], tg_id)
        self.assertEqual(me["profile"]["ielts"], 7.0)
        self.client.cookies.clear()

    def test_link_keeps_web_session(self):
        r = self.client.post("/api/auth/register", json={"email": "link@test.kz", "password": "secret1", "name": "Linker"})
        self.assertEqual(r.status_code, 200)
        tg_id = 616161
        code = run(db.create_link_code("tg", tg_id))["code"]
        self.assertEqual(self.client.post("/api/link/confirm", json={"code": code}).status_code, 200)
        me = self.client.get("/api/me").json()
        self.assertEqual(me["user_id"], tg_id)
        self.assertEqual(me["account"]["email"], "link@test.kz")      # сессия не потерялась
        self.assertTrue(me["telegram_linked"])
        self.assertEqual(self.client.get("/api/auth/me").json()["user"]["name"], "Linker")
        self.client.cookies.clear()

    def test_audience_stats_admin_only(self):
        self.client.get("/api/grants?category=all&limit=1")   # посетитель сайта получает cookie и событие
        run(db.add_user(777))
        run(db.log_event(777, "start"))
        self.assertEqual(self.client.get("/api/admin/stats").status_code, 401)
        a = self.client.get("/api/admin/stats", headers={"X-Admin-Token": "test-token"}).json()["audience"]
        self.assertGreaterEqual(a["users"]["telegram"], 1)
        self.assertGreaterEqual(a["users"]["site"], 1)
        self.assertGreaterEqual(a["active"]["today"]["telegram"], 1)
        self.assertEqual(a["users"]["total"], a["users"]["telegram"] + a["users"]["site"])
        self.assertEqual(len(a["daily"]), 14)
        self.assertGreaterEqual(a["daily"][-1]["active"], 1)

    def test_admin_users_csv_and_digest_source(self):
        run(db.add_user(779))
        run(db.log_event(779, "start"))   # пользователь бота
        self.assertEqual(self.client.get("/api/admin/users.csv").status_code, 401)
        r = self.client.get("/api/admin/users.csv", headers={"X-Admin-Token": "test-token"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.headers["content-type"])
        self.assertIn("user_id;source;email", r.text)
        self.assertIn("telegram", r.text)                      # пользователь бота из других тестов
        fresh = run(db.get_grants_added_since(days=7))         # гранты, добавленные в setUpClass — «за неделю»
        self.assertGreaterEqual(len(fresh), 1)
        self.assertTrue(all(g["is_active"] == 1 for g in fresh))

    def test_favorite_status_and_ics(self):
        gid = self.client.get("/api/grants?category=all&limit=1").json()["items"][0]["id"]
        self.client.post(f"/api/favorites/{gid}")
        r = self.client.patch(f"/api/favorites/{gid}/status", json={"status": "submitted"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.patch(f"/api/favorites/{gid}/status", json={"status": "weird"}).status_code, 422)
        items = self.client.get("/api/favorites").json()["items"]
        self.assertEqual(next(g for g in items if g["id"] == gid)["fav_status"], "submitted")
        ics = self.client.get("/api/favorites.ics")
        self.assertEqual(ics.status_code, 200)
        self.assertIn("text/calendar", ics.headers["content-type"])
        self.assertIn("BEGIN:VEVENT", ics.text)
        self.assertIn("TRIGGER:-P7D", ics.text)
        self.assertEqual(self.client.post("/api/events/share", json={"grant_id": gid}).status_code, 200)

    def test_schema_migrations_recorded(self):
        with sqlite3.connect(db.DB_NAME) as c:
            self.assertGreaterEqual(c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 1)
            self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            cols = {r[1] for r in c.execute("PRAGMA table_info(favorites)")}
            self.assertIn("status", cols)

    def test_public_usage_counter(self):
        run(db.add_user(778))
        run(db.log_event(778, "start"))                                              # пользователь бота
        self.client.get("/api/grants?category=all&limit=1")                          # посетитель сайта только смотрел
        snap = run(db.refresh_usage_snapshot())
        self.assertGreaterEqual(snap["telegram"], 1)
        self.assertEqual(snap["people"], snap["telegram"] + snap["site"])
        self.assertEqual(snap["date"], datetime.date.today().isoformat())
        usage = run(db.get_public_usage())                                           # второй вызов берёт снимок из базы
        self.assertEqual(usage["people"], snap["people"])
        self.assertIsNone(usage["week_delta"])                                        # недельного снимка ещё нет
        s = self.client.get("/api/stats/public").json()
        self.assertIn("people", s)
        self.assertEqual(s["users"]["people"], s["people"])

    def test_funnel_visits_and_registrations(self):
        from fastapi.testclient import TestClient
        from website.web import app
        fresh = TestClient(app)                                   # новый посетитель без cookie
        r = fresh.get("/?from=bot")                               # заход на лендинг по ссылке из бота
        self.assertEqual(r.status_code, 200)
        self.assertIn("gh_uid", r.cookies)                        # новому посетителю выдана cookie вместе со страницей
        r = self.client.get("/?from=bot")
        self.assertEqual(r.status_code, 200)
        self.client.get("/app")
        email = f"funnel{random.randint(1, 10**6)}@test.kz"
        self.assertEqual(self.client.post("/api/auth/register", json={"email": email, "password": "secret123", "name": "F"}).status_code, 200)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.post("/api/auth/login", json={"email": email, "password": "secret123"}).status_code, 200)
        a = self.client.get("/api/admin/stats", headers={"X-Admin-Token": "test-token"}).json()["audience"]
        f = a["funnel"]["today"]
        self.assertGreaterEqual(f["visitors"], 1)
        self.assertGreaterEqual(f["from_bot"], 1)
        self.assertGreaterEqual(f["registered"], 1)
        self.assertGreaterEqual(f["logins"], 1)
        events = {r["event"] for r in a["recent"]}
        self.assertTrue({"login", "register"} & events)
        self.assertTrue(any(r["email"] == email for r in a["recent"]))

    def test_admin_rate_limit_and_health(self):
        self.assertEqual(self.client.get("/healthz").json()["db"], True)
        self.assertEqual(self.client.get("/api/admin/runs", headers={"X-Admin-Token": "test-token"}).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/runs", headers={"X-Admin-Token": "wrong"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
