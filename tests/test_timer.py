import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from focus_tracker.storage import Storage
from focus_tracker.timer import FocusTimer
from focus_tracker.tracker import Tracker

START = datetime(2026, 10, 15, 9, 0)


class FakeClock:
    def __init__(self):
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class ScriptedKeys:
    """Presses keys at given offsets (seconds from START); time passes while waiting."""

    def __init__(self, clock: FakeClock, presses: list[tuple[float, str]]):
        self.clock = clock
        self.presses = list(presses)

    def read_key(self, timeout: float) -> str | None:
        if self.presses:
            at, key = self.presses[0]
            due = START + timedelta(seconds=at)
            if due <= self.clock.now + timedelta(seconds=timeout):
                self.presses.pop(0)
                self.clock.now = max(self.clock.now, due)
                if key == "^C":
                    raise KeyboardInterrupt
                return key
        self.clock.now += timedelta(seconds=timeout)
        return None


class TimerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sessions.json"
        self.tracker = Tracker(Storage(self.path))
        self.clock = FakeClock()
        self.screen: list[str] = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_timer(self, minutes: float | None, presses=()):
        target = timedelta(minutes=minutes) if minutes else None
        self.tracker.start("study", now=START, target=target)
        keys = ScriptedKeys(self.clock, presses)
        timer = FocusTimer(self.tracker, keys, self.screen.append, live=True, clock=self.clock)
        return timer.run()

    @property
    def output(self) -> str:
        return "".join(self.screen)

    def saved(self):
        [session] = Tracker(Storage(self.path)).sessions
        return session


class TestCountdown(TimerTestCase):
    def test_completes_and_saves_at_zero(self):
        result = self.run_timer(1)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(self.saved().duration(), timedelta(minutes=1))
        self.assertEqual(self.saved().end, START + timedelta(minutes=1))
        self.assertIn("\a", self.output)

    def test_live_countdown_display(self):
        self.run_timer(1)
        self.assertIn("\rFOCUS   01:00 remaining", self.output)
        self.assertIn("00:30 remaining", self.output)
        self.assertIn("00:01 remaining  ███████████████████░  99%", self.output)
        self.assertIn("00:00 remaining  ████████████████████ 100%", self.output)

    def test_pause_and_resume_keep_progress(self):
        # Pause 10s in, resume at 40s: 30s paused, so a 1-minute session ends at 90s.
        result = self.run_timer(1, [(10, "p"), (40, "p")])
        self.assertEqual(result.outcome, "completed")
        session = self.saved()
        self.assertEqual(session.duration(), timedelta(minutes=1))
        self.assertEqual(session.end, START + timedelta(seconds=90))
        self.assertEqual(len(session.pauses), 1)
        self.assertIn("PAUSED  00:50 remaining", self.output)

    def test_space_also_toggles_pause(self):
        self.run_timer(1, [(10, " "), (20, " ")])
        self.assertEqual(self.saved().end, START + timedelta(seconds=70))

    def test_end_early_records_actual_time(self):
        result = self.run_timer(25, [(5 * 60, "e"), (5 * 60 + 2, "y")])
        self.assertEqual(result.outcome, "ended")
        self.assertEqual(self.saved().duration(), timedelta(minutes=5, seconds=2))
        self.assertIn("End now and save 5m? (y/n)", self.output)

    def test_end_early_while_paused_excludes_pause(self):
        self.run_timer(25, [(60, "p"), (600, "e"), (601, "y")])
        self.assertEqual(self.saved().duration(), timedelta(minutes=1))

    def test_declining_confirmation_continues(self):
        result = self.run_timer(1, [(10, "e"), (11, "n"), (12, "c"), (13, "x")])
        self.assertEqual(result.outcome, "completed")

    def test_cancel_discards(self):
        result = self.run_timer(1, [(10, "c"), (11, "y")])
        self.assertEqual(result.outcome, "cancelled")
        self.assertEqual(Tracker(Storage(self.path)).sessions, [])

    def test_ctrl_c_ends_and_saves(self):
        result = self.run_timer(1, [(15, "^C")])
        self.assertEqual(result.outcome, "ended")
        self.assertEqual(self.saved().duration(), timedelta(seconds=15))

    def test_unknown_key_shows_hint(self):
        self.run_timer(1, [(5, "z")])
        self.assertIn("Use P, E or C.", self.output)

    def test_untimed_session_counts_up(self):
        result = self.run_timer(None, [(125, "e"), (126, "y")])
        self.assertEqual(result.outcome, "ended")
        self.assertIn("02:05 elapsed", self.output)


if __name__ == "__main__":
    unittest.main()
