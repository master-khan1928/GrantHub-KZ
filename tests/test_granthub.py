"""Тесты ядра и API. Запуск из корня проекта:  .venv\\Scripts\\python.exe -m unittest -v

База создаётся во временной папке, сеть и модель не нужны.
"""
import asyncio
import datetime
import os
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
        c.commit(); c.close()
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

    def test_admin_rate_limit_and_health(self):
        self.assertEqual(self.client.get("/healthz").json()["db"], True)
        self.assertEqual(self.client.get("/api/admin/runs", headers={"X-Admin-Token": "test-token"}).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/runs", headers={"X-Admin-Token": "wrong"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
