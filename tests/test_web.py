"""Tests for the web API. Skipped when the optional web dependencies aren't installed."""

import importlib.util
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from focus_tracker.storage import Storage
from focus_tracker.tracker import Tracker

HAVE_WEB = all(importlib.util.find_spec(m) for m in ("fastapi", "httpx"))

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from focus_tracker.web import create_app
    from focus_tracker.web.deps import get_now

NOW = datetime(2026, 10, 22, 16, 0)  # a Thursday


@unittest.skipUnless(HAVE_WEB, "web dependencies not installed (pip install -e '.[dev]')")
class WebTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sessions.json"
        self.tracker = Tracker(Storage(self.path))
        app = create_app(lambda: Storage(self.path))
        app.dependency_overrides[get_now] = lambda: NOW
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, path: str):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def timed(self, activity, start, minutes, focused, note=""):
        self.tracker.start(activity, note, now=start, target=timedelta(minutes=minutes))
        self.tracker.stop(now=start + timedelta(minutes=focused))


class TestPages(WebTestCase):
    def test_index_and_static_files(self):
        index = self.client.get("/")
        self.assertEqual(index.status_code, 200)
        self.assertIn("Focus Tracker", index.text)
        for nav in ("Dashboard", "Focus Sessions", "History", "Activities", "AI Insights"):
            self.assertIn(nav, index.text)
        for path in ("/static/css/app.css", "/static/js/app.js", "/static/js/api.js",
                     "/static/js/ui.js", "/static/js/views/dashboard.js",
                     "/static/js/views/focus.js", "/static/js/views/history.js",
                     "/static/js/views/activities.js", "/static/js/views/insights.js"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_health(self):
        self.assertEqual(self.get("/api/health")["status"], "ok")


class TestDashboard(WebTestCase):
    def test_empty(self):
        data = self.get("/api/dashboard")
        self.assertEqual(data["today"]["focused_seconds"], 0)
        self.assertEqual(data["recent_sessions"], [])
        self.assertIsNone(data["active_session"])
        self.assertEqual(len(data["last_7_days"]), 7)

    def test_with_sessions(self):
        self.timed("study", NOW.replace(hour=9), 50, 50, "chapter 3")
        self.timed("study", NOW - timedelta(days=1), 25, 10)
        self.tracker.add("work", timedelta(hours=2), NOW.replace(hour=13))
        data = self.get("/api/dashboard")
        self.assertEqual(data["today"]["focused_seconds"], 170 * 60)
        self.assertEqual(data["today"]["sessions"], 2)
        self.assertEqual(data["streak_days"], 2)
        self.assertEqual(data["last_7_days"][-1],
                         {"date": "2026-10-22", "focused_seconds": 170 * 60})
        self.assertEqual(data["last_7_days"][-2]["focused_seconds"], 10 * 60)
        self.assertEqual([a["name"] for a in data["week"]["by_activity"]], ["work", "study"])
        recent = data["recent_sessions"][0]
        self.assertEqual(recent["activity"], "work")
        self.assertEqual(recent["status"], "untimed")
        self.assertEqual(data["activity_count"], 2)

    def test_active_session_is_shown(self):
        self.tracker.start("study", now=NOW - timedelta(minutes=10), target=timedelta(minutes=25))
        active = self.get("/api/dashboard")["active_session"]
        self.assertEqual(active["status"], "running")
        self.assertEqual(active["remaining_seconds"], 15 * 60)
        self.assertEqual(active["percent"], 40)


class TestSessions(WebTestCase):
    def setUp(self):
        super().setUp()
        self.timed("study", NOW.replace(hour=9), 50, 50, "chapter 3")
        self.timed("study", NOW.replace(hour=11), 50, 35)
        self.tracker.add("work", timedelta(hours=1), NOW.replace(hour=14))

    def test_list_newest_first_with_statuses(self):
        data = self.get("/api/sessions")
        self.assertEqual(data["total"], 3)
        self.assertEqual([s["status"] for s in data["sessions"]],
                         ["untimed", "ended_early", "completed"])
        completed = data["sessions"][2]
        self.assertEqual(completed["start"], "2026-10-22T09:00:00")
        self.assertEqual(completed["focused_seconds"], 50 * 60)
        self.assertEqual(completed["note"], "chapter 3")
        self.assertEqual(data["sessions"][1]["percent"], 70)

    def test_filter_and_limit(self):
        data = self.get("/api/sessions?activity=STUDY&limit=1")
        self.assertEqual(data["total"], 2)
        self.assertEqual(len(data["sessions"]), 1)
        self.assertEqual(data["focused_seconds"], 85 * 60)

    def test_unknown_activity(self):
        self.assertEqual(self.client.get("/api/sessions?activity=nope").status_code, 404)

    def test_paused_session(self):
        self.tracker.start("study", now=NOW - timedelta(minutes=20), target=timedelta(minutes=25))
        self.tracker.pause(now=NOW - timedelta(minutes=5))
        data = self.get("/api/sessions/active")
        self.assertEqual(data["session"]["status"], "paused")
        self.assertEqual(data["session"]["focused_seconds"], 15 * 60)
        self.assertEqual(data["suggested_minutes"], 25)

    def test_no_active_session(self):
        self.assertEqual(self.get("/api/sessions/active"),
                         {"session": None, "suggested_minutes": 50})

    def test_expired_session_is_completed_on_load(self):
        # Like the CLI, the site saves a countdown that ran out while nobody watched.
        self.tracker.start("study", now=NOW - timedelta(hours=1), target=timedelta(minutes=10))
        self.assertIsNone(self.get("/api/sessions/active")["session"])
        self.assertEqual(Tracker(Storage(self.path)).sessions[-1].duration(),
                         timedelta(minutes=10))


class TestActivitiesAndStats(WebTestCase):
    def test_activities_sorted_by_focus(self):
        self.tracker.add_activity("reading")
        self.timed("study", NOW.replace(hour=9), 50, 50)
        self.tracker.add("work", timedelta(hours=2), NOW.replace(hour=14))
        names = [a["name"] for a in self.get("/api/activities")["activities"]]
        self.assertEqual(names, ["work", "study", "reading"])
        reading = self.get("/api/activities")["activities"][2]
        self.assertEqual((reading["sessions"], reading["last_session"]), (0, None))

    def test_stats_completion_rate(self):
        self.timed("study", NOW.replace(hour=9), 50, 50)
        self.timed("study", NOW.replace(hour=11), 50, 35)
        self.timed("study", NOW.replace(hour=13), 25, 25)
        data = self.get("/api/stats?period=today")
        self.assertEqual(data["sessions"], 3)
        self.assertEqual(data["outcomes"], {"completed": 2, "ended_early": 1, "untimed": 0})
        self.assertAlmostEqual(data["completion_rate"], 0.667)
        self.assertEqual(data["longest_seconds"], 50 * 60)

    def test_stats_rejects_bad_period(self):
        self.assertEqual(self.client.get("/api/stats?period=decade").status_code, 422)

    def test_insights_placeholder(self):
        data = self.get("/api/insights")
        self.assertFalse(data["available"])
        self.assertTrue(data["planned"])


class TestSharedData(WebTestCase):
    def test_reads_changes_made_by_the_cli(self):
        self.assertEqual(self.get("/api/sessions")["total"], 0)
        Tracker(Storage(self.path)).add("study", timedelta(minutes=30), NOW)  # e.g. the CLI
        self.assertEqual(self.get("/api/sessions")["total"], 1)

    def test_escaping_is_left_to_frontend_but_data_is_intact(self):
        self.tracker.add("<b>html</b>", timedelta(minutes=5), NOW, note='"quoted" & <tags>')
        session = self.get("/api/sessions")["sessions"][0]
        self.assertEqual(session["activity"], "<b>html</b>")
        self.assertEqual(session["note"], '"quoted" & <tags>')


if __name__ == "__main__":
    unittest.main()
