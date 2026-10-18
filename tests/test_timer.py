import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from focus_tracker.storage import Storage
from focus_tracker.display import CAR, FINISH, big_text, race_track
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


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class TimerTestCase(unittest.TestCase):
    COLUMNS, ROWS = 80, 30

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sessions.json"
        self.tracker = Tracker(Storage(self.path))
        self.clock = FakeClock()
        self.screen: list[str] = []

    def tearDown(self):
        self.tmp.cleanup()

    def make_timer(self, keys=None, color=False) -> FocusTimer:
        size = os.terminal_size((self.COLUMNS, self.ROWS))
        return FocusTimer(self.tracker, keys, self.screen.append, live=True,
                          clock=self.clock, color=color, terminal_size=lambda: size)

    def run_timer(self, minutes: float | None, presses=(), color=False):
        target = timedelta(minutes=minutes) if minutes else None
        self.tracker.start("study", now=START, target=target)
        return self.make_timer(ScriptedKeys(self.clock, presses), color).run()

    @property
    def output(self) -> str:
        return "".join(self.screen)

    def frames(self) -> list[list[str]]:
        """Every redraw of the screen, as plain-text lines."""
        return [ANSI.sub("", write).split("\n") for write in self.screen if "\x1b[2K" in write]

    def saved(self):
        [session] = Tracker(Storage(self.path)).sessions
        return session


def find(frame: list[str], text: str) -> str:
    return next(line for line in frame if text in line)


class TestCountdown(TimerTestCase):
    def test_completes_and_saves_at_zero(self):
        result = self.run_timer(1)
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(self.saved().duration(), timedelta(minutes=1))
        self.assertEqual(self.saved().end, START + timedelta(minutes=1))
        self.assertIn("✓ COMPLETE", self.frames()[-1][1])

    def test_countdown_ticks_down_in_big_digits(self):
        self.run_timer(1)
        frames = self.frames()
        clocks = ["\n".join(f[4:9]) for f in frames]
        for shown in ("01:00", "00:30", "00:01", "00:00"):
            big = "\n".join(row.center(64).rstrip() for row in big_text(shown))
            self.assertIn(big, clocks, shown)

    def test_pause_and_resume_keep_progress(self):
        # Pause 10s in, resume at 40s: 30s paused, so a 1-minute session ends at 90s.
        result = self.run_timer(1, [(10, "p"), (40, "p")])
        self.assertEqual(result.outcome, "completed")
        session = self.saved()
        self.assertEqual(session.duration(), timedelta(minutes=1))
        self.assertEqual(session.end, START + timedelta(seconds=90))
        self.assertEqual(len(session.pauses), 1)
        paused = [f for f in self.frames() if "‖ PAUSED" in f[1]]
        self.assertTrue(paused)
        self.assertIn("paused · press P to resume", paused[0][9])
        self.assertIn("[P] Resume", find(paused[0], "[P]"))

    def test_space_also_toggles_pause(self):
        self.run_timer(1, [(10, " "), (20, " ")])
        self.assertEqual(self.saved().end, START + timedelta(seconds=70))

    def test_end_early_records_actual_time(self):
        result = self.run_timer(25, [(5 * 60, "e"), (5 * 60 + 2, "y")])
        self.assertEqual(result.outcome, "ended")
        self.assertEqual(self.saved().duration(), timedelta(minutes=5, seconds=2))
        self.assertIn("End now and save 5m?   [Y] Yes   [N] No", self.output)
        self.assertIn("■ ENDED", self.frames()[-1][1])

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
        self.assertIn("✕ DISCARDED", self.frames()[-1][1])

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
        frame = self.frames()[-1]
        self.assertEqual(frame[4].strip(), big_text("02:05")[0].strip())
        self.assertIn("elapsed", frame[9])
        self.assertIn("Open-ended session", self.output)


class TestScreenLayout(TimerTestCase):
    def first_frame(self) -> list[str]:
        self.run_timer(25, [(0, "c"), (0, "y")])
        return self.frames()[0]

    def test_sections_in_order(self):
        frame = self.first_frame()
        self.assertTrue(frame[0].startswith("╭") and frame[2].startswith("╰"))
        self.assertIn("FOCUS SESSION  ·  study", frame[1])
        self.assertTrue(frame[1].rstrip(" │").endswith("● ACTIVE"))
        self.assertEqual([r.strip() for r in frame[4:9]], [r.strip() for r in big_text("25:00")])
        self.assertIn("remaining of 25m", frame[9])
        self.assertIn(race_track(0, 53), frame[11])  # car at the start line
        self.assertIn("░" * 47 + "    0%", frame[12])
        self.assertTrue(set(frame[14]) == {"─"})
        self.assertIn("[P] Pause     [E] End early     [C] Cancel", frame[15])

    def test_car_and_bar_line_up(self):
        frame = self.first_frame()
        self.assertEqual(len(frame[11]), len(frame[12]))
        self.assertEqual(len(frame[11]) - len(frame[11].lstrip()),
                         len(frame[12]) - len(frame[12].lstrip()))

    def test_every_frame_has_same_height_and_fits(self):
        self.run_timer(1, [(10, "p"), (20, "z"), (30, "p"), (40, "e"), (41, "n")])
        heights = {len(f) for f in self.frames()}
        self.assertEqual(heights, {17})
        self.assertLessEqual(max(len(line) for f in self.frames() for line in f), 79)

    def test_long_activity_name_is_shortened(self):
        self.tracker.start("a" * 100, now=START, target=timedelta(minutes=5))
        self.make_timer(ScriptedKeys(self.clock, [(0, "c"), (0, "y")])).run()
        header = self.frames()[0][1]
        self.assertEqual(len(header), 64)
        self.assertIn("…", header)

    def test_colors_only_when_enabled(self):
        self.run_timer(1, [(0, "c"), (0, "y")])
        self.assertNotIn("\x1b[1;3", self.output)
        self.screen.clear()
        self.tracker = Tracker(Storage(self.path))
        self.run_timer(1, [(0, "c"), (0, "y")], color=True)
        self.assertIn("\x1b[1;31m" + CAR, self.output)

    def test_cursor_hidden_then_restored(self):
        self.run_timer(1, [(5, "^C")])
        self.assertTrue(self.screen[0].startswith("\x1b[?25l"))
        self.assertTrue(self.output.endswith("\x1b[?25h"))

    def test_redraws_in_place(self):
        self.run_timer(1, [(5, "^C")])
        self.assertIn("\x1b[16A", self.screen[1])  # back up over the 17-line screen


class TestSmallTerminals(TimerTestCase):
    def test_short_terminal_uses_one_line_clock(self):
        self.ROWS = 15
        self.run_timer(25, [(0, "c"), (0, "y")])
        frame = self.frames()[0]
        self.assertEqual(len(frame), 13)
        self.assertEqual(frame[4].strip(), "25:00")

    def test_tiny_terminal_falls_back_to_status_line(self):
        self.ROWS = 8
        self.run_timer(25, [(0, "c"), (0, "y")])
        frame = self.frames()[0]
        self.assertEqual(len(frame), 1)
        self.assertIn("25:00 remaining", frame[0])

    def test_narrow_terminal_falls_back_to_status_line(self):
        self.COLUMNS = 40
        self.run_timer(25, [(0, "c"), (0, "y")])
        self.assertLessEqual(len(self.frames()[0][0]), 39)


class TestRaceTrack(TimerTestCase):
    def test_car_drives_from_start_to_finish(self):
        self.assertTrue(race_track(0).startswith(CAR))
        self.assertTrue(race_track(100).endswith(CAR + FINISH))
        positions = [race_track(p).index(CAR) for p in range(0, 101, 10)]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len({len(race_track(p)) for p in range(101)}), 1)  # fixed width

    def test_out_of_range_percent_is_clamped(self):
        self.assertEqual(race_track(-5), race_track(0))
        self.assertEqual(race_track(150), race_track(100))

    def test_car_moves_during_session(self):
        self.run_timer(1)
        tracks = [find(f, CAR) for f in self.frames()]
        positions = [t.index(CAR) for t in tracks]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(positions[0], positions[-1])
        self.assertIn(CAR + FINISH, tracks[-1])
        self.assertIn("100%", find(self.frames()[-1], "%"))

    def test_car_stays_still_while_paused(self):
        self.run_timer(1, [(30, "p"), (50, "p")])
        paused = [f for f in self.frames() if "PAUSED" in f[1]]
        self.assertTrue(paused)
        self.assertEqual(len({find(f, CAR).index(CAR) for f in paused}), 1)
        self.assertIn(race_track(50, 53), find(paused[0], CAR))

    def test_compact_track_shrinks_on_narrow_terminals(self):
        self.assertEqual(FocusTimer._track_width(200), 32)
        self.assertLess(FocusTimer._track_width(60), 32)
        self.assertEqual(FocusTimer._track_width(20), 12)


if __name__ == "__main__":
    unittest.main()
