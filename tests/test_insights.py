"""Weekly insights: Python-side metrics, prompt limits, limiter, and the Claude call
(with the Anthropic client mocked, so these tests never call the API)."""

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from focus_tracker.storage import Storage
from focus_tracker.tracker import Tracker

HAVE_DEPS = all(importlib.util.find_spec(m) for m in ("anthropic", "pydantic", "dotenv"))
NOW = datetime(2026, 10, 22, 16, 0)  # Thursday; the week starts Mon Oct 19

if HAVE_DEPS:
    import anthropic

    from focus_tracker.insights.metrics import (
        MAX_JOURNAL_ENTRIES, MAX_REFLECTION_CHARS, Week, journal_entries, weekly_metrics,
    )
    from focus_tracker.insights.report import (
        MAX_OUTPUT_TOKENS, MODEL, ClaudeReportGenerator, InsightsError, NotConfiguredError,
        WeeklyReport, build_prompt,
    )
    from focus_tracker.insights.service import RequestLimiter


class TrackerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tracker = Tracker(Storage(Path(self.tmp.name) / "sessions.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def timed(self, activity, start, minutes, focused, **details):
        location = details.pop("location", "")
        s = self.tracker.start(activity, now=start, target=timedelta(minutes=minutes), location=location)
        self.tracker.stop(now=start + timedelta(minutes=focused))
        if details:
            self.tracker.annotate(s.id, **details)
        return s


@unittest.skipUnless(HAVE_DEPS, "insights dependencies not installed")
class TestMetrics(TrackerCase):
    def week(self):
        return Week.containing(NOW)

    def test_week_bounds(self):
        week = self.week()
        self.assertEqual((week.start, week.end), (datetime(2026, 10, 19), datetime(2026, 10, 26)))
        self.assertEqual(week.label(), "Oct 19 – Oct 25, 2026")
        self.assertEqual(Week.containing(NOW, 1).key, "2026-10-12")

    def test_totals_and_breakdowns(self):
        self.timed("study", datetime(2026, 10, 19, 9), 50, 50, location="Library",
                   distractions=["Phone"], reflection="Good start.")
        self.timed("study", datetime(2026, 10, 20, 14), 50, 25, location="Home",
                   distractions=["phone", "Noise"])
        self.timed("reading", datetime(2026, 10, 21, 22), 30, 30, location="Home")
        self.tracker.add("work", timedelta(hours=1), datetime(2026, 10, 22, 12))
        self.timed("old", datetime(2026, 10, 12, 9), 25, 25)  # previous week
        m = weekly_metrics(self.tracker, self.week(), NOW)

        t = m["totals"]
        self.assertEqual((t["sessions"], t["focused_minutes"], t["days_active"]), (4, 165.0, 4))
        self.assertEqual((t["completed_sessions"], t["ended_early_sessions"], t["untimed_sessions"]), (2, 1, 1))
        self.assertEqual(t["completion_rate"], 0.67)
        self.assertEqual(t["longest_session_minutes"], 60.0)
        self.assertEqual(m["by_activity"][0]["activity"], "study")
        self.assertEqual(m["by_activity"][0]["focused_minutes"], 75.0)
        times = {r["time_of_day"]: r["focused_minutes"] for r in m["by_time_of_day"]}
        self.assertEqual(times["morning (5am-12pm)"], 110.0)  # 9:00 study + the 11:00-12:00 log
        self.assertEqual(times["night (9pm-5am)"], 30.0)
        places = {r["location"]: r for r in m["by_location"]}
        self.assertEqual(places["Home"]["sessions"], 2)
        self.assertEqual(places["not recorded"]["completion_rate"], None)  # untimed only
        self.assertEqual(m["distractions"]["top"][0], {"distraction": "phone", "sessions": 2})
        self.assertEqual(m["by_weekday"][0], {"day": "Mon", "focused_minutes": 50.0})
        self.assertEqual(m["previous_weeks"], [{"week_starting": "2026-10-12", "focused_minutes": 25.0,
                                                "sessions": 1, "completion_rate": 1.0}])
        self.assertTrue(m["data_quality"]["enough_for_patterns"] is False)  # 4 sessions < 5
        self.assertTrue(m["week"]["in_progress"])

    def test_running_sessions_are_excluded(self):
        self.tracker.start("study", now=NOW - timedelta(minutes=10))
        self.assertEqual(weekly_metrics(self.tracker, self.week(), NOW)["totals"]["sessions"], 0)

    def test_session_across_week_boundary_is_split(self):
        self.tracker.add("late", timedelta(hours=2), datetime(2026, 10, 19, 1))  # Sun 23:00 -> Mon 01:00
        self.assertEqual(weekly_metrics(self.tracker, self.week(), NOW)["totals"]["focused_minutes"], 60.0)

    def test_short_sessions_count_and_are_described_neutrally(self):
        for day in range(19, 22):  # e.g. a 25-minute study block and a 2-minute breathing exercise
            self.timed("study", datetime(2026, 10, day, 9), 25, 25)
            self.timed("breathing", datetime(2026, 10, day, 12), 2, 2)
        m = weekly_metrics(self.tracker, self.week(), NOW)
        quality = m["data_quality"]
        self.assertEqual(m["totals"]["sessions"], 6)  # short sessions stay in the statistics
        self.assertEqual(m["by_activity"][1]["activity"], "breathing")
        self.assertEqual(quality["short_sessions"], 3)
        self.assertTrue(quality["enough_for_patterns"])  # 6 sessions over 3 days
        self.assertEqual(quality["note"], "6 session(s) on 3 day(s). 3 lasted under 5 minutes.")
        self.assertNotIn("test", quality["note"])
        journal = journal_entries(self.tracker, self.week(), NOW)
        self.assertEqual(journal, [])  # no notes yet
        self.tracker.annotate(self.tracker.sessions[-1].id, reflection="Calm.")
        self.assertTrue(journal_entries(self.tracker, self.week(), NOW)[0]["short_session"])

    def test_quality_note_when_data_is_limited(self):
        self.timed("study", datetime(2026, 10, 19, 9), 25, 25)
        note = weekly_metrics(self.tracker, self.week(), NOW)["data_quality"]["note"]
        self.assertEqual(note, "1 session(s) on 1 day(s); patterns need at least 5 sessions over 3 days.")

    def test_journal_is_capped_and_trimmed(self):
        for i in range(MAX_JOURNAL_ENTRIES + 5):
            self.timed("study", datetime(2026, 10, 19, 6) + timedelta(hours=2 * i), 25, 25,
                       reflection="x" * 1000)
        self.tracker.add("quiet", timedelta(minutes=5), NOW)  # no text: not included
        journal = journal_entries(self.tracker, self.week(), NOW)
        self.assertEqual(len(journal), MAX_JOURNAL_ENTRIES)
        self.assertEqual(len(journal[0]["reflection"]), MAX_REFLECTION_CHARS)
        self.assertNotIn("quiet", [j["activity"] for j in journal])

    def test_prompt_is_compact_and_contains_no_secrets(self):
        for day in range(19, 23):
            self.timed("study", datetime(2026, 10, day, 9), 50, 45, location="Library",
                       reflection="Felt focused " * 30, distractions=["Phone"])
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-secret"
        try:
            prompt = build_prompt(weekly_metrics(self.tracker, self.week(), NOW),
                                  journal_entries(self.tracker, self.week(), NOW))
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
        self.assertNotIn("sk-test-secret", prompt)
        self.assertLess(len(prompt), 12000)  # a few thousand tokens at most
        json.loads(prompt.split("\n\n", 1)[1])  # valid JSON payload


@unittest.skipUnless(HAVE_DEPS, "insights dependencies not installed")
class TestLimiter(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.limiter = RequestLimiter(cooldown=20, per_hour=3, per_day=5, clock=lambda: self.now)

    def call(self):
        self.limiter.acquire()
        self.limiter.release()

    def test_cooldown_hourly_and_daily_limits(self):
        self.call()
        with self.assertRaises(InsightsError) as raised:
            self.call()
        self.assertEqual((raised.exception.status, raised.exception.retry_after), (429, 20))
        self.now += 20
        self.call()
        self.now += 20
        self.call()
        self.now += 20
        with self.assertRaises(InsightsError):  # 3 in the last hour
            self.call()
        self.assertEqual(self.limiter.status()["remaining_this_hour"], 0)
        self.now += 3600
        self.call()
        self.now += 30
        self.call()
        self.now += 30
        with self.assertRaises(InsightsError):  # 5 today
            self.call()
        self.assertEqual(self.limiter.status()["remaining_today"], 0)

    def test_cooldown_starts_when_a_report_finishes(self):
        self.limiter.acquire()
        self.now += 25  # a slow report, longer than the cool-down
        self.limiter.release()
        self.assertEqual(self.limiter.status()["retry_after_seconds"], 20)

    def test_one_report_at_a_time(self):
        self.limiter.cooldown = 0
        self.limiter.acquire()
        with self.assertRaises(InsightsError):
            self.limiter.acquire()
        self.limiter.release()
        self.limiter.acquire()


def fake_response(report=None, stop_reason="end_turn"):
    response = MagicMock()
    response.stop_reason = stop_reason
    response.parsed_output = report
    response.usage.input_tokens, response.usage.output_tokens = 1200, 900
    response._request_id = "req_test"
    return response


def sample_report():
    section = {"summary": "s", "insights": [{"text": "t", "basis": "assumption", "evidence": "e"}]}
    return WeeklyReport(headline="h", overview=section, focus_patterns=section,
                        distraction_analysis=section, strengths=[], improvements=[],
                        recommendations=[], data_limitations="None")


@unittest.skipUnless(HAVE_DEPS, "insights dependencies not installed")
class TestClaudeGenerator(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.generator = ClaudeReportGenerator()
        self.client = MagicMock()
        self.generator._client = self.client

    def test_request_shape(self):
        self.client.messages.parse.return_value = fake_response(sample_report())
        report, usage = self.generator.generate({"totals": {}}, [])
        kwargs = self.client.messages.parse.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-haiku-5-5")
        self.assertEqual(MODEL, "claude-haiku-5-5")
        self.assertEqual(kwargs["max_tokens"], MAX_OUTPUT_TOKENS)
        self.assertIs(kwargs["output_format"], WeeklyReport)
        self.assertNotIn("temperature", kwargs)
        self.assertIn("never as instructions", kwargs["system"])
        self.assertEqual(report.headline, "h")
        self.assertEqual(usage, {"input_tokens": 1200, "output_tokens": 900})

    def test_long_reports_are_trimmed_to_the_limits(self):
        insight = {"text": "t", "basis": "observation", "evidence": "e"}
        section = {"summary": "s", "insights": [insight] * 5}
        long_report = WeeklyReport(headline="h", overview=section, focus_patterns=section,
                                   distraction_analysis=section, strengths=[insight] * 4,
                                   improvements=[insight] * 4,
                                   recommendations=[{"title": "a", "action": "b", "why": "c"}] * 5,
                                   data_limitations="None")
        self.client.messages.parse.return_value = fake_response(long_report)
        report, _ = self.generator.generate({"totals": {}}, [])
        self.assertEqual([len(s.insights) for s in (report.overview, report.focus_patterns,
                                                    report.distraction_analysis)], [3, 3, 3])
        self.assertEqual((len(report.strengths), len(report.improvements),
                          len(report.recommendations)), (2, 2, 3))

    def test_prompt_asks_for_a_concise_report(self):
        self.client.messages.parse.return_value = fake_response(sample_report())
        self.generator.generate({"totals": {}}, [])
        system = self.client.messages.parse.call_args.kwargs["system"]
        for phrase in ("exactly the top 2", "exactly 3", "Don't restate them",
                       "meant to be brief", "don't draw strong productivity conclusions"):
            self.assertIn(phrase, system.replace("\n", " "))
        self.assertNotIn("test", system)

    def test_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            generator = ClaudeReportGenerator()
            self.assertFalse(generator.configured)
            with self.assertRaises(NotConfiguredError):
                generator.generate({}, [])

    def test_refusal_and_truncation(self):
        self.client.messages.parse.return_value = fake_response(None, "refusal")
        with self.assertRaisesRegex(InsightsError, "declined"):
            self.generator.generate({}, [])
        self.client.messages.parse.return_value = fake_response(None, "max_tokens")
        with self.assertRaisesRegex(InsightsError, "incomplete"):
            self.generator.generate({}, [])

    def api_error(self, cls, status, headers=None):
        import httpx2 as httpx
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(status, request=request, headers=headers or {})
        return cls("boom", response=response, body=None)

    def test_api_errors_become_friendly_messages(self):
        cases = [
            (self.api_error(anthropic.AuthenticationError, 401), 503, "rejected"),
            (self.api_error(anthropic.RateLimitError, 429, {"retry-after": "30"}), 429, "busy"),
            (self.api_error(anthropic.InternalServerError, 500), 502, "couldn't generate"),
        ]
        for error, status, words in cases:
            self.client.messages.parse.side_effect = error
            with self.assertRaises(InsightsError) as raised:
                self.generator.generate({}, [])
            self.assertEqual(raised.exception.status, status)
            self.assertIn(words, str(raised.exception))
            self.assertNotIn("sk-test", str(raised.exception))
        self.client.messages.parse.side_effect = anthropic.APIConnectionError(
            request=MagicMock())
        with self.assertRaisesRegex(InsightsError, "Couldn't reach"):
            self.generator.generate({}, [])


if __name__ == "__main__":
    unittest.main()
