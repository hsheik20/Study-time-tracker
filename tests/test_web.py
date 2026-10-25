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

    from focus_tracker.insights.service import InsightsService, RequestLimiter
    from focus_tracker.web import create_app
    from focus_tracker.web.deps import get_now

NOW = datetime(2026, 10, 22, 16, 0)  # a Thursday


class FakeGenerator:
    """Stands in for ClaudeReportGenerator; records what it was sent."""

    model = "fake-model"

    def __init__(self, configured=True, error=None):
        self.configured = configured
        self.error = error
        self.calls = []

    def generate(self, metrics, journal):
        from focus_tracker.insights.report import WeeklyReport

        self.calls.append((metrics, journal))
        if self.error:
            raise self.error
        section = {"summary": "s", "insights": [{"text": "t", "basis": "observation", "evidence": "e"}]}
        report = WeeklyReport(headline=f"{metrics['totals']['sessions']} sessions", overview=section,
                              focus_patterns=section, distraction_analysis=section,
                              strengths=section["insights"], improvements=section["insights"],
                              recommendations=[{"title": "a", "action": "b", "why": "c"}],
                              data_limitations="None")
        return report, {"input_tokens": 100, "output_tokens": 50}


@unittest.skipUnless(HAVE_WEB, "web dependencies not installed (pip install -e '.[dev]')")
class WebTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sessions.json"
        self.tracker = Tracker(Storage(self.path))
        # A fake generator: these tests never load .env or call the Claude API.
        self.generator = FakeGenerator()
        self.limiter = RequestLimiter(cooldown=0, per_hour=100, per_day=100)
        app = create_app(lambda: Storage(self.path),
                         insights_service=InsightsService(self.generator, self.limiter))
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
                     "/static/js/ui.js", "/static/js/store.js", "/static/js/sound.js",
                     "/static/js/views/dashboard.js",
                     "/static/js/views/focus.js", "/static/js/views/history.js",
                     "/static/js/views/activities.js", "/static/js/views/insights.js"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_page_and_modules_are_revalidated(self):
        # A stale cached view module run against a newer API breaks the page.
        for path in ("/", "/static/js/app.js", "/static/js/views/insights.js"):
            self.assertEqual(self.client.get(path).headers.get("cache-control"), "no-cache", path)
        self.assertNotIn("cache-control", self.client.get("/api/health").headers)

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
        data = self.get("/api/sessions/active")
        self.assertIsNone(data["session"])
        self.assertEqual(data["suggested_minutes"], 50)

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

    def test_insights_overview_makes_no_api_call(self):
        data = self.get("/api/insights")
        self.assertTrue(data["configured"])
        self.assertIsNone(data["report"])
        self.assertEqual(self.generator.calls, [])


class ClockedWebTestCase(WebTestCase):
    """Lets a test move the server's clock forward."""

    def setUp(self):
        super().setUp()
        self.now = NOW
        self.client.app.dependency_overrides[get_now] = lambda: self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)

    def send(self, method: str, path: str, expected: int = 200, **kwargs):
        response = self.client.request(method, path, **kwargs)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json() if response.content else None


class TestFocusTimerApi(ClockedWebTestCase):
    def start(self, **body):
        return self.send("POST", "/api/sessions/active", 201,
                         json={"activity": "study", "minutes": 25, **body})

    def test_start_creates_activity_and_session(self):
        data = self.start(location="Library", note="chapter 4")
        session = data["session"]
        self.assertEqual((session["activity"], session["status"]), ("study", "running"))
        self.assertEqual((session["target_seconds"], session["remaining_seconds"]), (1500, 1500))
        self.assertEqual((session["location"], session["note"]), ("Library", "chapter 4"))
        self.assertIn("study", Tracker(Storage(self.path)).activities())
        self.assertEqual(data["recent_locations"], ["Library"])

    def test_pause_excludes_time_and_survives_refresh(self):
        self.start()
        self.advance(minutes=5)
        self.send("POST", "/api/sessions/active/pause")
        self.advance(minutes=30)  # e.g. the browser was closed while paused
        session = self.get("/api/sessions/active")["session"]
        self.assertEqual((session["status"], session["remaining_seconds"]), ("paused", 20 * 60))
        self.assertEqual(session["paused_seconds"], 30 * 60)
        self.send("POST", "/api/sessions/active/resume")
        self.advance(minutes=2)
        session = self.get("/api/sessions/active")["session"]
        self.assertEqual((session["status"], session["focused_seconds"]), ("running", 7 * 60))

    def test_end_early_saves_focused_time(self):
        self.start()
        self.advance(minutes=12)
        session = self.send("POST", "/api/sessions/active/stop")["session"]
        self.assertEqual((session["status"], session["focused_seconds"]), ("ended_early", 12 * 60))
        self.assertIsNone(self.get("/api/sessions/active")["session"])

    def test_cancel_discards(self):
        self.start()
        self.send("POST", "/api/sessions/active/cancel")
        self.assertEqual(self.get("/api/sessions")["total"], 0)

    def test_completes_automatically_at_zero(self):
        self.start(minutes=1)
        session_id = self.get("/api/sessions/active")["session"]["id"]
        self.advance(seconds=75)
        session = self.get(f"/api/sessions/{session_id}")["session"]
        self.assertEqual((session["status"], session["focused_seconds"]), ("completed", 60))
        self.assertIsNone(self.get("/api/sessions/active")["session"])

    def test_conflicts_and_validation(self):
        self.send("POST", "/api/sessions/active/pause", 409)          # nothing running
        self.start()
        self.assertIn("Already tracking", self.send("POST", "/api/sessions/active", 409,
                      json={"activity": "work", "minutes": 25})["detail"])
        self.send("POST", "/api/sessions/active/resume", 409)          # not paused
        for bad in ({"activity": "", "minutes": 25}, {"activity": "x", "minutes": 0},
                    {"activity": "x", "minutes": 721}, {"activity": "x"}):
            self.send("POST", "/api/sessions/active", 422, json=bad)

    def test_started_in_cli_controlled_on_web(self):
        Tracker(Storage(self.path)).start("cli work", now=self.now, target=timedelta(minutes=50))
        self.advance(minutes=10)
        self.send("POST", "/api/sessions/active/pause")
        self.assertTrue(Tracker(Storage(self.path)).active_session().paused)


class TestSessionDetailsApi(ClockedWebTestCase):
    def test_reflection_after_session(self):
        self.send("POST", "/api/sessions/active", 201, json={"activity": "study", "minutes": 25})
        self.advance(minutes=20)
        session_id = self.send("POST", "/api/sessions/active/stop")["session"]["id"]
        updated = self.send("PATCH", f"/api/sessions/{session_id}",
                            json={"distractions": ["Phone", "Noise"], "reflection": "Good flow."})
        self.assertEqual(updated["session"]["distractions"], ["Phone", "Noise"])
        saved = Tracker(Storage(self.path)).find_session(session_id)
        self.assertEqual((saved.reflection, saved.distractions), ("Good flow.", ["Phone", "Noise"]))

    def test_patch_validation_and_missing(self):
        self.tracker.add("study", timedelta(minutes=5), NOW)
        self.send("PATCH", "/api/sessions/1", 422, json={"reflection": "x" * 2001})
        self.send("PATCH", "/api/sessions/1", 422, json={"distractions": ["a"] * 21})
        self.send("PATCH", "/api/sessions/99", 404, json={"reflection": "hi"})

    def test_log_past_session(self):
        data = self.send("POST", "/api/sessions", 201, json={
            "activity": "reading", "minutes": 45, "ended_at": "2026-10-22T14:30",
            "location": "Café", "note": "novel"})["session"]
        self.assertEqual((data["start"], data["end"]), ("2026-10-22T13:45:00", "2026-10-22T14:30:00"))
        self.assertEqual((data["status"], data["location"]), ("untimed", "Café"))
        self.assertEqual(self.get("/api/dashboard")["today"]["focused_seconds"], 45 * 60)

    def test_log_rejects_future_and_bad_input(self):
        self.send("POST", "/api/sessions", 422,
                  json={"activity": "x", "minutes": 10, "ended_at": "2026-10-22T18:00"})
        self.send("POST", "/api/sessions", 422, json={"activity": "x", "minutes": -5})

    def test_delete_session(self):
        self.tracker.add("study", timedelta(minutes=5), NOW)
        self.send("DELETE", "/api/sessions/1", 204)
        self.assertEqual(self.get("/api/sessions")["total"], 0)
        self.send("DELETE", "/api/sessions/1", 404)

    def test_cannot_delete_running_session(self):
        self.send("POST", "/api/sessions/active", 201, json={"activity": "study", "minutes": 25})
        self.assertIn("still running", self.send("DELETE", "/api/sessions/1", 409)["detail"])


class TestActivityManagementApi(ClockedWebTestCase):
    def test_create_rename_delete(self):
        self.assertEqual(self.send("POST", "/api/activities", 201, json={"name": " Guitar "})["name"], "Guitar")
        self.send("POST", "/api/activities", 409, json={"name": "guitar"})  # duplicate
        self.tracker.add("Guitar", timedelta(minutes=30), NOW)
        self.assertEqual(self.send("PATCH", "/api/activities/Guitar", json={"name": "Music"})["name"], "Music")
        self.assertEqual(self.get("/api/sessions")["sessions"][0]["activity"], "Music")  # sessions follow
        self.assertEqual(self.send("DELETE", "/api/activities/Music")["sessions_deleted"], 1)
        self.assertEqual(self.get("/api/activities")["activities"], [])
        self.assertEqual(self.get("/api/dashboard")["all_time"]["focused_seconds"], 0)

    def test_errors(self):
        self.send("PATCH", "/api/activities/nope", 404, json={"name": "x"})
        self.send("DELETE", "/api/activities/nope", 404)
        self.send("POST", "/api/activities", 422, json={"name": ""})
        self.tracker.add_activity("a"); self.tracker.add_activity("b")
        self.send("PATCH", "/api/activities/a", 409, json={"name": "B"})

    def test_cannot_delete_activity_with_running_session(self):
        self.send("POST", "/api/sessions/active", 201, json={"activity": "study", "minutes": 25})
        self.send("DELETE", "/api/activities/study", 409)

    def test_names_with_special_characters(self):
        self.send("POST", "/api/activities", 201, json={"name": "C++ / data"})
        self.send("PATCH", "/api/activities/C%2B%2B%20%2F%20data", json={"name": "C++"})
        self.assertEqual([a["name"] for a in self.get("/api/activities")["activities"]], ["C++"])


class TestInsightsApi(ClockedWebTestCase):
    def add_sessions(self):
        self.timed("study", NOW.replace(hour=9), 50, 50, "chapter 3")
        self.tracker.annotate(1, distractions=["Phone"], reflection="Went well.")
        self.timed("study", NOW.replace(hour=14), 25, 10)

    def test_generate_and_reload_saved_report(self):
        self.add_sessions()
        data = self.send("POST", "/api/insights", json={"week": "current"})
        self.assertEqual(data["report"]["headline"], "2 sessions")
        self.assertEqual(data["report"]["model"], "fake-model")
        self.assertEqual(data["metrics"]["totals"]["sessions"], 2)
        metrics, journal = self.generator.calls[0]
        self.assertEqual(journal[-1]["reflection"], "Went well.")
        # The saved report comes back on the next page load without another call.
        self.assertEqual(self.get("/api/insights")["report"]["headline"], "2 sessions")
        self.assertEqual(len(self.generator.calls), 1)
        saved = self.path.with_name("insights.json")
        self.assertTrue(saved.exists())

    def test_regenerate_replaces_report(self):
        self.add_sessions()
        self.send("POST", "/api/insights", json={})
        self.tracker.add("work", timedelta(minutes=30), NOW)
        self.assertEqual(self.send("POST", "/api/insights", json={})["report"]["headline"], "3 sessions")
        self.assertEqual(len(self.generator.calls), 2)

    def test_previous_week(self):
        self.timed("study", NOW - timedelta(days=7), 25, 25)
        data = self.send("POST", "/api/insights", json={"week": "previous"})
        self.assertEqual(data["metrics"]["week"]["start"], "2026-10-12")
        self.assertEqual(self.get("/api/insights")["report"], None)  # this week untouched

    def test_no_data_is_not_sent(self):
        detail = self.send("POST", "/api/insights", 422, json={})["detail"]
        self.assertIn("no finished sessions", detail)
        self.assertEqual(self.generator.calls, [])

    def test_not_configured(self):
        self.add_sessions()
        self.generator.configured = False
        self.assertFalse(self.get("/api/insights")["configured"])
        self.assertIn("ANTHROPIC_API_KEY", self.send("POST", "/api/insights", 503, json={})["detail"])
        self.assertEqual(self.generator.calls, [])

    def test_api_failure_is_reported(self):
        from focus_tracker.insights.report import InsightsError

        self.add_sessions()
        self.generator.error = InsightsError("Claude couldn't generate the report right now.", 502)
        self.assertIn("couldn't", self.send("POST", "/api/insights", 502, json={})["detail"])
        self.assertIsNone(self.get("/api/insights")["report"])

    def test_rate_limited(self):
        self.add_sessions()
        self.limiter.per_hour = 1
        self.send("POST", "/api/insights", json={})
        response = self.client.post("/api/insights", json={})
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
        self.assertEqual(len(self.generator.calls), 1)

    def test_bad_week(self):
        self.send("POST", "/api/insights", 422, json={"week": "someday"})

    def test_no_credentials_anywhere_in_responses(self):
        self.add_sessions()
        import os
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-not-a-real-key"
        try:
            pages = [self.client.get("/api/insights").text,
                     self.client.post("/api/insights", json={}).text,
                     self.client.get("/").text, self.client.get("/static/js/views/insights.js").text]
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
        for text in pages:
            self.assertNotIn("sk-test-not-a-real-key", text)


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
