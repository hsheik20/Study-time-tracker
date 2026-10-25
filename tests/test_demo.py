"""The public demo: per-visitor data sent from the browser, validation, and the
AI report limits. The Claude API is never called (a fake generator stands in)."""

import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from focus_tracker.models import Session

HAVE_WEB = all(importlib.util.find_spec(m) for m in ("fastapi", "httpx", "anthropic", "pydantic"))

if HAVE_WEB:
    from fastapi.testclient import TestClient

    from focus_tracker.insights.report import WeeklyReport
    from focus_tracker.insights.service import InsightsService, RequestLimiter, VisitorLimiter
    from focus_tracker.web import create_app
    from focus_tracker.web.demo import MAX_SESSIONS, build_sample_data
    from focus_tracker.web.deps import get_now

NOW = datetime(2026, 10, 22, 16, 0)  # a Thursday


class FakeGenerator:
    model = "fake-model"
    configured = True

    def __init__(self):
        self.calls = []

    def generate(self, metrics, journal):
        self.calls.append((metrics, journal))
        section = {"summary": "s", "insights": [{"text": "t", "basis": "observation", "evidence": "e"}]}
        report = WeeklyReport(headline="h", overview=section, focus_patterns=section,
                              distraction_analysis=section, strengths=[], improvements=[],
                              recommendations=[], data_limitations="None")
        return report, {"input_tokens": 1, "output_tokens": 1}


def session(id, start, minutes=25, **extra):
    start = datetime.fromisoformat(start)
    return {"id": id, "activity": extra.pop("activity", "study"), "start": start.isoformat(),
            "end": (start + timedelta(minutes=minutes)).isoformat(), "note": "",
            "target_seconds": minutes * 60, "pauses": [], "location": "", "distractions": [],
            "reflection": "", **extra}


@unittest.skipUnless(HAVE_WEB, "web dependencies not installed")
class DemoCase(unittest.TestCase):
    def setUp(self):
        # Point the local data file at an empty temp dir to prove the demo never writes it.
        self.tmp = tempfile.TemporaryDirectory()
        env = patch.dict(os.environ, {"FOCUS_TRACKER_DATA": str(Path(self.tmp.name) / "s.json")})
        env.start()
        self.addCleanup(env.stop)
        self.generator = FakeGenerator()
        self.shared = RequestLimiter(cooldown=0, per_hour=100, per_day=100, max_concurrent=3,
                                     limit_message="The demo has reached its shared AI report limit.")
        self.visitors = VisitorLimiter(cooldown=0, per_hour=2, per_day=5)
        self.app = create_app(insights_service=InsightsService(self.generator, self.shared, self.visitors),
                              demo_mode=True)
        self.app.dependency_overrides[get_now] = lambda: NOW
        self.client = TestClient(self.app)

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, method, path, data, body=None, expected=200, visitor="1.1.1.1", **extra):
        envelope = {"method": method, "path": path, "body": body, "data": data, "tz_offset": 0, **extra}
        response = self.client.post("/api/demo", json=envelope, headers={"cf-connecting-ip": visitor})
        if expected == 200:  # any success (some routes answer 201 Created)
            self.assertLess(response.status_code, 300, response.text)
        else:
            self.assertEqual(response.status_code, expected, response.text)
        return response.json()


class TestDemoMode(DemoCase):
    def test_health_reports_demo_and_data_routes_are_closed(self):
        self.assertTrue(self.client.get("/api/health").json()["demo"])
        for path in ("/api/sessions", "/api/dashboard", "/api/insights"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assertEqual(self.client.post("/api/sessions/active", json={}).status_code, 404)

    def test_timer_round_trip_returns_the_changed_data(self):
        data = {"activities": [], "sessions": []}
        started = self.call("POST", "/sessions/active", data, {"activity": "Reading", "minutes": 25})
        self.assertEqual(started["data"]["session"]["activity"], "Reading")
        data = started["state"]
        self.assertEqual(data["activities"], ["Reading"])
        for step in ("pause", "resume", "stop"):
            data = self.call("POST", f"/sessions/active/{step}", data)["state"]
        self.assertIsNotNone(data["sessions"][0]["end"])
        self.assertEqual(len(data["sessions"][0]["pauses"]), 1)
        # A read changes nothing, so no new state comes back.
        listing = self.call("GET", "/sessions", data)
        self.assertNotIn("state", listing)
        self.assertEqual(listing["data"]["total"], 1)

    def test_activity_and_session_crud(self):
        data = {"activities": ["Old"], "sessions": [session(1, "2026-10-21T09:00:00", activity="Old")]}
        data = self.call("POST", "/activities", data, {"name": "Spanish"})["state"]
        data = self.call("PATCH", "/activities/Old", data, {"name": "New"})["state"]
        self.assertEqual(data["sessions"][0]["activity"], "New")
        data = self.call("POST", "/sessions", data, {"activity": "Spanish", "minutes": 20})["state"]
        details = {"location": "Library", "distractions": ["Phone"], "reflection": "Good."}
        data = self.call("PATCH", "/sessions/2", data, details)["state"]
        self.assertEqual(data["sessions"][1]["distractions"], ["Phone"])
        deleted = self.call("DELETE", "/sessions/1", data)
        self.assertIsNone(deleted["data"])
        data = self.call("DELETE", "/activities/New", deleted["state"])["state"]
        self.assertEqual([s["id"] for s in data["sessions"]], [2])
        stats = self.call("GET", "/stats", data, query="period=all")["data"]
        self.assertEqual(stats["sessions"], 1)

    def test_errors_keep_their_status_and_message(self):
        result = self.call("POST", "/sessions/active/pause", {"activities": [], "sessions": []},
                           expected=409)
        self.assertEqual(result["data"]["detail"], "No session is currently running.")
        self.call("GET", "/sessions/99", None, expected=404)

    def test_visitors_are_isolated_and_nothing_is_saved_on_the_server(self):
        alice = self.call("POST", "/activities", {"activities": [], "sessions": []},
                          {"name": "Alice's"}, visitor="1.1.1.1")["state"]
        bob = self.call("GET", "/activities", {"activities": ["Bob's"], "sessions": []}, visitor="2.2.2.2")
        self.assertEqual([a["name"] for a in bob["data"]["activities"]], ["Bob's"])
        self.assertEqual(alice["activities"], ["Alice's"])
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_visitor_time_zone_is_used(self):
        del self.app.dependency_overrides[get_now]
        result = self.call("POST", "/sessions/active", None, {"activity": "a", "minutes": 5},
                           tz_offset=420)  # UTC-7
        started = datetime.fromisoformat(result["state"]["sessions"][0]["start"])
        expected = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=420)
        self.assertLess(abs(started - expected), timedelta(seconds=5))


class TestDemoValidation(DemoCase):
    def rejected(self, data=None, **envelope):
        payload = {"method": "GET", "path": "/sessions", "data": data, "tz_offset": 0, **envelope}
        response = self.client.post("/api/demo", json=payload)
        self.assertEqual(response.status_code, 400, response.text)
        return response.json()["detail"]

    def test_bad_session_data_is_rejected(self):
        ok = session(1, "2026-10-21T09:00:00")
        bad_cases = [
            {"sessions": [{**ok, "id": "1"}]},
            {"sessions": [{**ok, "start": "yesterday"}]},
            {"sessions": [{**ok, "start": "2026-10-21T09:00:00+00:00"}]},
            {"sessions": [{**ok, "end": "2026-10-21T08:00:00"}]},
            {"sessions": [{**ok, "note": "x" * 501}]},
            {"sessions": [{**ok, "distractions": ["x"] * 21}]},
            {"sessions": [{**ok, "target_seconds": 10**9}]},
            {"sessions": [{**ok, "pauses": [["2026-10-21T09:10:00"]]}]},
            {"sessions": [{**ok, "unexpected": 1}]},
            {"sessions": [ok, {**ok}]},  # duplicate id
            {"sessions": [{**ok, "end": None}, {**ok, "id": 2, "end": None}]},  # two running
            {"activities": [""]},
            {"activities": "study"},
            {"sessions": [ok] * (MAX_SESSIONS + 1)},
            {"extra": []},
            [],
        ]
        for data in bad_cases:
            with self.subTest(data=str(data)[:80]):
                self.rejected(data)

    def test_bad_envelopes_are_rejected(self):
        self.rejected(method="PUT")
        self.rejected(path="/demo")
        self.rejected(path="sessions")
        self.rejected(tz_offset=10_000)
        self.rejected(reports={"not-a-week": {}})
        self.assertEqual(self.client.post("/api/demo", content=b"{nope").status_code, 400)

    def test_oversized_requests_are_refused(self):
        response = self.client.post("/api/demo", content=b"x" * 1_100_000)
        self.assertEqual(response.status_code, 413)


class TestDemoInsights(DemoCase):
    def week_data(self, sample=False):
        sessions = [session(i, f"2026-10-{19 + i % 3}T{8 + i:02d}:00:00", sample=sample) for i in range(1, 6)]
        return {"activities": ["study"], "sessions": sessions}

    def test_report_is_saved_in_the_browser_and_sample_data_is_labelled(self):
        data = self.week_data(sample=True)
        result = self.call("POST", "/insights", data, {"week": "current"}, reports={})
        self.assertEqual(result["data"]["report"]["headline"], "h")
        self.assertIn("2026-10-19", result["reports"])
        self.assertNotIn("state", result)
        metrics, journal = self.generator.calls[0]
        self.assertEqual(metrics["data_quality"]["sample_sessions"], 5)
        self.assertIn("All of these are sample data", metrics["data_quality"]["note"])
        # The saved report comes back when the browser sends it again.
        again = self.call("GET", "/insights", data, reports=result["reports"])
        self.assertEqual(again["data"]["report"]["headline"], "h")
        self.assertEqual(len(self.generator.calls), 1)

    def test_per_visitor_limit(self):
        data = self.week_data()
        for _ in range(2):
            self.call("POST", "/insights", data, {"week": "current"}, visitor="1.1.1.1")
        refused = self.call("POST", "/insights", data, {"week": "current"}, expected=429,
                            visitor="1.1.1.1")
        self.assertIn("demo's report limit", refused["data"]["detail"])
        self.call("POST", "/insights", data, {"week": "current"}, visitor="2.2.2.2")  # others unaffected
        self.assertEqual(len(self.generator.calls), 3)
        status = self.call("GET", "/insights", data, visitor="1.1.1.1")["data"]["limits"]
        self.assertEqual(status["remaining_this_hour"], 0)

    def test_global_quota_applies_to_everyone(self):
        self.shared.per_hour = 2
        data = self.week_data()
        self.call("POST", "/insights", data, {"week": "current"}, visitor="1.1.1.1")
        self.call("POST", "/insights", data, {"week": "current"}, visitor="2.2.2.2")
        refused = self.call("POST", "/insights", data, {"week": "current"}, expected=429,
                            visitor="3.3.3.3")
        self.assertIn("shared AI report limit", refused["data"]["detail"])
        # The refused visitor's own allowance wasn't used up by the failed attempt.
        self.assertEqual(self.visitors.for_visitor("3.3.3.3").status()["remaining_this_hour"], 2)
        self.assertEqual(len(self.generator.calls), 2)

    def test_invalid_data_never_reaches_claude(self):
        bad = self.week_data()
        bad["sessions"][0]["reflection"] = "x" * 5000
        response = self.client.post("/api/demo", json={"method": "POST", "path": "/insights",
                                                       "body": {"week": "current"}, "data": bad})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.generator.calls, [])


    def test_demo_defaults_are_conservative(self):
        from focus_tracker.web.demo import insights_limiters

        shared, per_visitor = insights_limiters()
        visitor = per_visitor.for_visitor("x")
        self.assertEqual((visitor.cooldown, visitor.per_hour, visitor.per_day), (60, 2, 3))
        self.assertEqual((shared.cooldown, shared.per_hour, shared.per_day, shared.max_concurrent),
                         (0, 10, 20, 2))

    def test_spoofed_headers_cannot_dodge_the_visitor_limit(self):
        data = self.week_data()
        for fake in ("6.6.6.6", "7.7.7.7"):
            response = self.client.post("/api/demo", json={
                "method": "POST", "path": "/insights", "body": {"week": "current"}, "data": data},
                headers={"cf-connecting-ip": "1.1.1.1", "x-forwarded-for": fake, "true-client-ip": fake})
            self.assertEqual(response.status_code, 200, response.text)
        response = self.client.post("/api/demo", json={
            "method": "POST", "path": "/insights", "body": {"week": "current"}, "data": data},
            headers={"cf-connecting-ip": "1.1.1.1", "x-forwarded-for": "8.8.8.8", "true-client-ip": "8.8.8.8"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(self.generator.calls), 2)


@unittest.skipUnless(HAVE_WEB, "web dependencies not installed")
class TestVisitorIdentity(unittest.TestCase):
    def identify(self, client="10.0.0.5", **headers):
        from focus_tracker.web.demo import identify_visitor

        scope = {"client": (client, 1234),
                 "headers": [(k.replace("_", "-").encode(), v.encode()) for k, v in headers.items()]}
        return identify_visitor(scope)

    def test_cloudflare_header_wins_over_client_supplied_headers(self):
        self.assertEqual(self.identify(cf_connecting_ip="203.0.113.7", x_forwarded_for="1.2.3.4",
                                       true_client_ip="5.6.7.8"), ("203.0.113.7", "cf-connecting-ip"))

    def test_forged_left_end_of_x_forwarded_for_is_ignored(self):
        # The client wrote 1.2.3.4; the proxy appended the address it really saw.
        self.assertEqual(self.identify(x_forwarded_for="1.2.3.4, 198.51.100.9"),
                         ("198.51.100.9", "x-forwarded-for (right-most)"))

    def test_true_client_ip_is_never_trusted(self):
        self.assertEqual(self.identify(true_client_ip="5.6.7.8"), ("10.0.0.5", "connection"))

    def test_invalid_values_are_ignored(self):
        self.assertEqual(self.identify(cf_connecting_ip="evil, 1.1.1.1", x_forwarded_for="1.1.1.1, nonsense"),
                         ("10.0.0.5", "connection"))
        self.assertEqual(self.identify(client="not-an-ip"), ("unknown", "connection"))

    def test_ipv6_network_counts_as_one_visitor(self):
        first = self.identify(cf_connecting_ip="2001:db8:1:2::1")[0]
        self.assertEqual(first, "2001:db8:1:2::/64")
        self.assertEqual(self.identify(cf_connecting_ip="2001:db8:1:2:ffff::9")[0], first)
        self.assertNotEqual(self.identify(cf_connecting_ip="2001:db8:1:3::1")[0], first)
        self.assertEqual(self.identify(cf_connecting_ip="::ffff:203.0.113.7")[0], "203.0.113.7")

    def test_whoami_shows_the_key_used(self):
        client = TestClient(create_app(insights_service=InsightsService(FakeGenerator()), demo_mode=True))
        result = client.get("/api/demo/whoami", headers={"cf-connecting-ip": "203.0.113.7",
                                                         "x-forwarded-for": "1.2.3.4"}).json()
        self.assertEqual(result, {"visitor": "203.0.113.7", "source": "cf-connecting-ip"})
        local = TestClient(create_app(insights_service=InsightsService(FakeGenerator()), demo_mode=False))
        self.assertEqual(local.get("/api/demo/whoami").status_code, 404)


@unittest.skipUnless(HAVE_WEB, "web dependencies not installed")
class TestSampleData(unittest.TestCase):
    def test_sample_data_is_realistic_past_and_marked(self):
        result = build_sample_data(NOW)
        sessions = result["data"]["sessions"]
        self.assertGreaterEqual(len(sessions), 12)
        self.assertTrue(all(s["sample"] for s in sessions))
        self.assertTrue(all(datetime.fromisoformat(s["end"]) <= NOW for s in sessions))
        self.assertEqual(set(result["sample_activities"]), {s["activity"] for s in sessions})
        self.assertTrue(any(s["distractions"] for s in sessions))
        self.assertTrue(any(s["reflection"] for s in sessions))
        self.assertTrue(any(s["pauses"] for s in sessions))

    def test_sample_endpoint_uses_the_visitor_time_zone(self):
        client = TestClient(create_app(insights_service=InsightsService(FakeGenerator()), demo_mode=True))
        data = client.get("/api/demo/sample?tz_offset=-600").json()["data"]
        self.assertTrue(data["sessions"])
        self.assertEqual(client.get("/api/demo/sample?tz_offset=99999").status_code, 422)


class TestLocalModeUnchanged(unittest.TestCase):
    def test_sample_flag_only_written_when_set(self):
        plain = Session(1, "a", datetime(2026, 1, 1, 9))
        self.assertNotIn("sample", plain.to_dict())
        self.assertFalse(Session.from_dict(plain.to_dict()).sample)
        marked = Session(2, "a", datetime(2026, 1, 1, 9), sample=True)
        self.assertTrue(Session.from_dict(marked.to_dict()).sample)

    @unittest.skipUnless(HAVE_WEB, "web dependencies not installed")
    def test_local_app_has_no_demo_endpoints(self):
        client = TestClient(create_app(insights_service=InsightsService(FakeGenerator()), demo_mode=False))
        self.assertFalse(client.get("/api/health").json()["demo"])
        self.assertEqual(client.post("/api/demo", json={}).status_code, 404)
        self.assertEqual(client.get("/api/demo/sample").status_code, 404)

    def test_server_uses_port_from_environment(self):
        from focus_tracker.web import server

        with patch.dict(os.environ, {"PORT": "10000"}), patch.object(server, "serve") as serve:
            server.main(["--host", "0.0.0.0", "--no-browser"])
        serve.assert_called_once_with("0.0.0.0", 10000, False)
