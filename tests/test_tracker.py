import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from focus_tracker.formatting import format_clock, format_duration, parse_duration
from focus_tracker.storage import Storage
from focus_tracker.tracker import Tracker, TrackerError


class TrackerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sessions.json"
        self.tracker = Tracker(Storage(self.path))

    def tearDown(self):
        self.tmp.cleanup()

    def reload(self) -> Tracker:
        return Tracker(Storage(self.path))


class TestTracker(TrackerTestCase):
    def test_start_and_stop_persists(self):
        t0 = datetime(2026, 10, 15, 9, 0)
        self.tracker.start("studying", now=t0)
        self.tracker.stop(now=t0 + timedelta(minutes=50))

        sessions = self.reload().sessions
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].activity, "studying")
        self.assertEqual(sessions[0].duration(), timedelta(minutes=50))

    def test_cannot_start_twice(self):
        self.tracker.start("work")
        with self.assertRaises(TrackerError):
            self.tracker.start("study")

    def test_stop_without_active_session(self):
        with self.assertRaises(TrackerError):
            self.tracker.stop()

    def test_active_session_survives_reload(self):
        self.tracker.start("meditating")
        self.assertEqual(self.reload().active_session().activity, "meditating")

    def test_cancel_discards_session(self):
        self.tracker.start("work")
        self.tracker.cancel()
        self.assertEqual(self.reload().sessions, [])

    def test_add_and_delete(self):
        s = self.tracker.add("reading", timedelta(minutes=30))
        self.assertEqual(s.duration(), timedelta(minutes=30))
        self.tracker.delete(s.id)
        self.assertEqual(self.reload().sessions, [])
        with self.assertRaises(TrackerError):
            self.tracker.delete(999)

    def test_ids_are_unique_after_delete(self):
        a = self.tracker.add("a", timedelta(minutes=1))
        b = self.tracker.add("b", timedelta(minutes=1))
        self.tracker.delete(a.id)
        c = self.tracker.add("c", timedelta(minutes=1))
        self.assertGreater(c.id, b.id)

    def test_empty_activity_rejected(self):
        with self.assertRaises(TrackerError):
            self.tracker.start("   ")

    def test_summary_groups_and_sorts(self):
        end = datetime(2026, 10, 15, 12, 0)
        self.tracker.add("study", timedelta(hours=1), end)
        self.tracker.add("work", timedelta(hours=2), end)
        self.tracker.add("study", timedelta(minutes=30), end)
        totals = self.tracker.summary("all", now=end)
        self.assertEqual(list(totals), ["work", "study"])
        self.assertEqual(totals["study"], timedelta(minutes=90))

    def test_summary_today_clips_sessions_crossing_midnight(self):
        now = datetime(2026, 10, 15, 12, 0)
        # 23:00 yesterday -> 01:00 today: only 1h counts for today.
        self.tracker.add("coding", timedelta(hours=2), datetime(2026, 10, 15, 1, 0))
        self.tracker.add("old", timedelta(hours=1), datetime(2026, 10, 10, 12, 0))
        self.assertEqual(self.tracker.summary("today", now=now), {"coding": timedelta(hours=1)})

    def test_summary_week_starts_monday(self):
        now = datetime(2026, 10, 15, 12, 0)  # Thursday
        self.tracker.add("in", timedelta(hours=1), datetime(2026, 10, 12, 10, 0))  # Monday
        self.tracker.add("out", timedelta(hours=1), datetime(2026, 10, 11, 10, 0))  # Sunday
        self.assertEqual(list(self.tracker.summary("week", now=now)), ["in"])

    def test_history_filters_and_orders(self):
        self.tracker.add("study", timedelta(minutes=5), datetime(2026, 10, 1))
        self.tracker.add("work", timedelta(minutes=5), datetime(2026, 10, 2))
        self.tracker.add("Study", timedelta(minutes=5), datetime(2026, 10, 3))
        result = self.tracker.history("study")
        self.assertEqual([s.end.day for s in result], [3, 1])


class TestActivities(TrackerTestCase):
    def test_activities_persist_without_sessions(self):
        self.tracker.add_activity("reading")
        self.assertEqual(self.reload().activities(), ["reading"])

    def test_sessions_reuse_existing_spelling(self):
        self.tracker.add_activity("Studying")
        s = self.tracker.add("studying", timedelta(minutes=5))
        self.assertEqual(s.activity, "Studying")
        self.assertEqual(self.tracker.activities(), ["Studying"])

    def test_rename_updates_sessions(self):
        self.tracker.add("study", timedelta(minutes=5))
        self.tracker.rename_activity("STUDY", "CSE 373")
        tracker = self.reload()
        self.assertEqual(tracker.activities(), ["CSE 373"])
        self.assertEqual(tracker.sessions[0].activity, "CSE 373")

    def test_rename_to_existing_name_rejected(self):
        self.tracker.add_activity("a")
        self.tracker.add_activity("b")
        with self.assertRaises(TrackerError):
            self.tracker.rename_activity("a", "B")

    def test_delete_activity_removes_its_sessions(self):
        self.tracker.add("a", timedelta(minutes=5))
        self.tracker.add("b", timedelta(minutes=5))
        removed = self.tracker.delete_activity("a")
        self.assertEqual(len(removed), 1)
        tracker = self.reload()
        self.assertEqual(tracker.activities(), ["b"])
        self.assertEqual([s.activity for s in tracker.sessions], ["b"])

    def test_cannot_delete_activity_with_running_session(self):
        self.tracker.start("a")
        with self.assertRaises(TrackerError):
            self.tracker.delete_activity("a")

    def test_legacy_file_without_activity_list(self):
        self.path.write_text(
            '{"sessions": [{"id": 1, "activity": "old", "start": "2026-10-01T10:00:00",'
            ' "end": "2026-10-01T11:00:00"}]}'
        )
        self.assertEqual(self.reload().activities(), ["old"])

    def test_corrupt_file_gives_readable_error(self):
        self.path.write_text("{not json")
        with self.assertRaisesRegex(ValueError, "Could not read data file"):
            self.reload()


class TestStats(TrackerTestCase):
    def test_stats(self):
        end = datetime(2026, 10, 15, 12, 0)
        self.tracker.add("a", timedelta(minutes=30), end)
        self.tracker.add("b", timedelta(minutes=90), end)
        stats = self.tracker.stats("all", now=end)
        self.assertEqual(stats.count, 2)
        self.assertEqual(stats.total, timedelta(hours=2))
        self.assertEqual(stats.average, timedelta(hours=1))
        self.assertEqual(stats.longest, timedelta(minutes=90))

    def test_streak(self):
        now = datetime(2026, 10, 15, 12, 0)
        for day in (15, 14, 13, 11):
            self.tracker.add("a", timedelta(minutes=10), datetime(2026, 10, day, 10, 0))
        self.assertEqual(self.tracker.streak(now), 3)

    def test_streak_counts_from_yesterday_if_nothing_today(self):
        self.tracker.add("a", timedelta(minutes=10), datetime(2026, 10, 14, 10, 0))
        self.assertEqual(self.tracker.streak(datetime(2026, 10, 15, 9, 0)), 1)
        self.assertEqual(self.tracker.streak(datetime(2026, 10, 17, 9, 0)), 0)


class TestTimedSessions(TrackerTestCase):
    T0 = datetime(2026, 10, 15, 9, 0)

    def at(self, minutes: float) -> datetime:
        return self.T0 + timedelta(minutes=minutes)

    def test_pauses_are_excluded_and_persisted(self):
        self.tracker.start("study", now=self.T0, target=timedelta(minutes=25))
        self.tracker.pause(now=self.at(10))
        tracker = self.reload()
        session = tracker.active_session()
        self.assertTrue(session.paused)
        # Progress is frozen while paused, even across a restart.
        self.assertEqual(session.duration(self.at(30)), timedelta(minutes=10))
        self.assertEqual(session.remaining(self.at(30)), timedelta(minutes=15))
        tracker.resume(now=self.at(30))
        tracker.stop(now=self.at(35))
        self.assertEqual(self.reload().sessions[0].duration(), timedelta(minutes=15))

    def test_stop_while_paused_closes_the_pause(self):
        self.tracker.start("study", now=self.T0)
        self.tracker.pause(now=self.at(5))
        session = self.tracker.stop(now=self.at(20))
        self.assertFalse(session.paused)
        self.assertEqual(session.duration(), timedelta(minutes=5))

    def test_pause_errors(self):
        with self.assertRaises(TrackerError):
            self.tracker.pause()
        self.tracker.start("study")
        with self.assertRaises(TrackerError):
            self.tracker.resume()
        self.tracker.pause()
        with self.assertRaises(TrackerError):
            self.tracker.pause()

    def test_invalid_target_rejected(self):
        with self.assertRaises(TrackerError):
            self.tracker.start("study", target=timedelta(0))

    def test_complete_if_due_uses_exact_end_time(self):
        self.tracker.start("study", now=self.T0, target=timedelta(minutes=25))
        self.tracker.pause(now=self.at(5))
        self.tracker.resume(now=self.at(15))
        self.assertIsNone(self.tracker.complete_if_due(now=self.at(30)))
        session = self.tracker.complete_if_due(now=self.at(90))  # checked long after
        self.assertEqual(session.end, self.at(35))
        self.assertEqual(self.reload().sessions[0].duration(), timedelta(minutes=25))

    def test_complete_if_due_ignores_paused_and_untimed(self):
        self.tracker.start("study", now=self.T0)
        self.assertIsNone(self.tracker.complete_if_due(now=self.at(600)))
        self.tracker.stop(now=self.at(1))
        self.tracker.start("study", now=self.at(2), target=timedelta(minutes=1))
        self.tracker.pause(now=self.at(2.5))
        self.assertIsNone(self.tracker.complete_if_due(now=self.at(600)))

    def test_summary_excludes_paused_time_and_clips(self):
        # 23:30 -> 00:30 with a 23:50-00:10 pause: 10m of focus falls on each day.
        start = datetime(2026, 10, 14, 23, 30)
        self.tracker.start("study", now=start)
        self.tracker.pause(now=start + timedelta(minutes=20))
        self.tracker.resume(now=start + timedelta(minutes=40))
        self.tracker.stop(now=start + timedelta(minutes=60))
        now = datetime(2026, 10, 15, 12, 0)
        self.assertEqual(self.tracker.summary("today", now=now)["study"], timedelta(minutes=20))
        self.assertEqual(self.tracker.summary("all", now=now)["study"], timedelta(minutes=40))

    def test_last_target(self):
        self.assertIsNone(self.tracker.last_target())
        self.tracker.start("a", now=self.T0, target=timedelta(minutes=50))
        self.tracker.stop(now=self.at(1))
        self.tracker.add("b", timedelta(minutes=5))  # untimed, ignored
        self.assertEqual(self.tracker.last_target(), timedelta(minutes=50))


class TestFormatting(unittest.TestCase):
    def test_parse_duration(self):
        cases = {
            "90": timedelta(minutes=90),
            "45m": timedelta(minutes=45),
            "2h": timedelta(hours=2),
            "1h30m": timedelta(hours=1, minutes=30),
            "1h 30m": timedelta(hours=1, minutes=30),
        }
        for text, expected in cases.items():
            self.assertEqual(parse_duration(text), expected, text)

    def test_parse_duration_invalid(self):
        for text in ["", "abc", "1.5h", "m", "30s"]:
            with self.assertRaises(ValueError, msg=text):
                parse_duration(text)

    def test_format_duration(self):
        self.assertEqual(format_duration(timedelta(seconds=42)), "42s")
        self.assertEqual(format_duration(timedelta(minutes=5, seconds=3)), "5m 03s")
        self.assertEqual(format_duration(timedelta(minutes=45)), "45m")
        self.assertEqual(format_duration(timedelta(minutes=1)), "1m")
        self.assertEqual(format_duration(timedelta(hours=2, minutes=5)), "2h 05m")

    def test_format_clock(self):
        self.assertEqual(format_clock(timedelta(minutes=25)), "25:00")
        self.assertEqual(format_clock(timedelta(seconds=59.2), round_up=True), "01:00")
        self.assertEqual(format_clock(timedelta(seconds=59.8)), "00:59")
        self.assertEqual(format_clock(timedelta(hours=1, seconds=3)), "1:00:03")
        self.assertEqual(format_clock(timedelta(seconds=-5)), "00:00")


if __name__ == "__main__":
    unittest.main()
