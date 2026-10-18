import unittest
from datetime import date, datetime, timedelta

from focus_tracker.display import paint
from focus_tracker.history_view import day_label, history_screen, session_status
from focus_tracker.models import Pause, Session

NOW = datetime(2026, 10, 18, 16, 30)  # a Sunday


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute)


def text(lines) -> list[str]:
    return [t for _, t in lines]


class TestStatus(unittest.TestCase):
    def test_statuses(self):
        target = timedelta(minutes=50)
        self.assertEqual(session_status(Session(1, "a", at(18, 9), at(18, 9, 50), target=target)),
                         "✓ Completed")
        self.assertEqual(session_status(Session(1, "a", at(18, 9), at(18, 9, 35), target=target)),
                         "■ Ended at 70%")
        self.assertEqual(session_status(Session(1, "a", at(18, 9), at(18, 10))), "· Untimed")
        self.assertEqual(session_status(Session(1, "a", at(18, 9))), "● Running")
        self.assertEqual(session_status(Session(1, "a", at(18, 9), pauses=[Pause(at(18, 9, 5))])),
                         "‖ Paused")

    def test_completed_tolerates_rounding(self):
        s = Session(1, "a", at(18, 9), at(18, 9, 50) - timedelta(milliseconds=500),
                    target=timedelta(minutes=50))
        self.assertEqual(session_status(s), "✓ Completed")


class TestDayLabels(unittest.TestCase):
    def test_labels(self):
        today = date(2026, 10, 18)
        self.assertEqual(day_label(today, today), "TODAY · Sun, Oct 18")
        self.assertEqual(day_label(date(2026, 10, 17), today), "YESTERDAY · Sat, Oct 17")
        self.assertEqual(day_label(date(2026, 10, 5), today), "MON, OCT 5")
        self.assertEqual(day_label(date(2025, 12, 31), today), "WED, DEC 31, 2025")


class TestHistoryScreen(unittest.TestCase):
    def setUp(self):
        self.sessions = [  # newest first, as Tracker.history returns them
            Session(4, "CSE 373 homework", at(18, 15, 40), None, "problem set 4",
                    timedelta(minutes=50)),
            Session(3, "meditating", at(18, 8, 10), at(18, 8, 30), "morning",
                    timedelta(minutes=20)),
            Session(2, "CSE 373 homework", at(17, 19), at(17, 19, 35), "",
                    timedelta(minutes=50)),
            Session(1, "work", at(13, 13), at(13, 15), ""),
        ]

    def screen(self, **kwargs) -> list[str]:
        return text(history_screen(self.sessions, "Recent sessions", NOW, **kwargs))

    def test_header(self):
        lines = self.screen()
        self.assertTrue(lines[0].startswith("╭"))
        self.assertIn("SESSION HISTORY  ·  Recent sessions", lines[1])
        self.assertTrue(lines[1].endswith("4 sessions │"))

    def test_grouped_by_day_with_totals(self):
        lines = self.screen()
        self.assertTrue(any("TODAY · Sun, Oct 18" in l and l.endswith("1h 10m focused") for l in lines))
        self.assertTrue(any("YESTERDAY · Sat, Oct 17" in l and l.endswith("35m focused") for l in lines))
        self.assertTrue(any("TUE, OCT 13" in l and l.endswith("2h 00m focused") for l in lines))
        # Day headings appear in order, each above its own sessions.
        order = [next(i for i, l in enumerate(lines) if key in l)
                 for key in ("TODAY", "#4", "#3", "YESTERDAY", "#2", "OCT 13", "#1")]
        self.assertEqual(order, sorted(order))

    def test_session_rows(self):
        lines = self.screen()
        row = next(l for l in lines if "#3" in l)
        for part in ("08:10–08:30", "meditating", "20m", "✓ Completed", "morning"):
            self.assertIn(part, row)
        running = next(l for l in lines if "#4" in l)
        self.assertIn("15:40–now", running)
        self.assertIn("● Running", running)

    def test_columns_line_up(self):
        lines = self.screen()
        status_column = next(l for l in lines if "STATUS" in l).index("STATUS")
        rows = [l for l in lines if l.lstrip().startswith("#")]
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertIn(row[status_column], "✓■·●‖", row)

    def test_footer(self):
        # 50m so far (running) + 20m + 35m + 2h
        self.assertEqual(self.screen()[-1], "  4 sessions  ·  3h 45m focused")
        self.assertEqual(self.screen(total_sessions=24)[-1],
                         "  Showing 4 of 24 sessions  ·  3h 45m focused")

    def test_fits_width_and_shortens_long_text(self):
        self.sessions[0].activity = "a very long activity name indeed"
        self.sessions[0].note = "n" * 100
        for width in (78, 70, 60, 50):
            lines = self.screen(width=width)
            self.assertLessEqual(max(len(l) for l in lines), width)
        self.assertIn("a very long activit…", "\n".join(self.screen()))

    def test_notes_dropped_when_too_narrow(self):
        self.assertIn("NOTE", "\n".join(self.screen(width=78)))
        self.assertNotIn("NOTE", "\n".join(self.screen(width=60)))

    def test_empty(self):
        lines = text(history_screen([], "All sessions", NOW))
        self.assertIn("0 sessions", lines[1])
        self.assertIn("No sessions yet", lines[-1])

    def test_status_colors(self):
        row = next(l for l in self.screen() if "#3" in l)
        painted = paint("row", row)
        self.assertIn("\x1b[32m✓ Completed\x1b[0m", painted)
        self.assertIn("\x1b[2m  #3\x1b[0m", painted)

    def test_column_headings_are_bright(self):
        headings = next(l for l in self.screen() if "STATUS" in l)
        self.assertEqual(paint("columns", headings), f"\x1b[1;95m{headings}\x1b[0m")


if __name__ == "__main__":
    unittest.main()
