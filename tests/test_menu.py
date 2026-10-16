import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from focus_tracker.menu import BANNER, Menu
from focus_tracker.storage import Storage
from focus_tracker.tracker import Tracker


class MenuTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sessions.json"
        self.tracker = Tracker(Storage(self.path))

    def tearDown(self):
        self.tmp.cleanup()

    def run_menu(self, *inputs: str) -> str:
        """Run the menu with scripted answers; running out of answers acts like Ctrl+D."""
        answers = iter(inputs)
        output: list[str] = []

        def fake_input(prompt: str) -> str:
            output.append(prompt)
            try:
                return next(answers)
            except StopIteration:
                raise EOFError from None

        def fake_print(*args) -> None:
            output.append(" ".join(str(a) for a in args))

        self.assertEqual(Menu(self.tracker, fake_input, fake_print).run(), 0)
        return "\n".join(output)

    def reload(self) -> Tracker:
        return Tracker(Storage(self.path))


class TestMainMenu(MenuTestCase):
    def test_shows_menu_and_exits(self):
        out = self.run_menu("5")
        self.assertIn(BANNER, out)
        for label in ["1. Start Focus Session", "2. View Session History",
                      "3. View Statistics", "4. Manage Activities", "5. Exit"]:
            self.assertIn(label, out)
        self.assertIn("Goodbye", out)

    def test_invalid_input_reprompts(self):
        out = self.run_menu("abc", "9", "0", "", "-1", "5")
        self.assertIn("'abc' is not a valid option. Please enter a number from 1 to 5.", out)
        self.assertIn("'9' is not a valid option", out)
        self.assertIn("'0' is not a valid option", out)
        self.assertIn("'-1' is not a valid option", out)
        self.assertEqual(out.count(BANNER), 1)  # never left the main menu

    def test_end_of_input_exits_cleanly(self):
        self.assertIn("Goodbye", self.run_menu())

    def test_submenu_returns_to_main_menu(self):
        out = self.run_menu("2", "5", "3", "5", "4", "6", "5")
        self.assertEqual(out.count(BANNER), 4)


class TestFocusSession(MenuTestCase):
    def test_first_session_asks_for_activity_name(self):
        out = self.run_menu("1", "studying", "chapter 3", "", "5")
        self.assertIn("Focusing on 'studying'", out)
        self.assertIn("Saved", out)
        [session] = self.reload().sessions
        self.assertEqual((session.activity, session.note), ("studying", "chapter 3"))
        self.assertFalse(session.active)

    def test_pick_existing_activity(self):
        self.tracker.add_activity("work")
        self.tracker.add_activity("meditating")
        self.run_menu("1", "2", "", "", "5")  # activities sort: meditating, work
        self.assertEqual(self.reload().sessions[0].activity, "work")

    def test_new_activity_from_picker(self):
        self.tracker.add_activity("work")
        self.run_menu("1", "2", "reading", "", "", "5")
        self.assertEqual(self.reload().activities(), ["reading", "work"])

    def test_back_from_picker_starts_nothing(self):
        self.tracker.add_activity("work")
        self.run_menu("1", "3", "5")
        self.assertEqual(self.reload().sessions, [])

    def test_cancel_session(self):
        out = self.run_menu("1", "work", "", "huh", "c", "n", "c", "y", "5")
        self.assertIn("Press Enter to stop the session, or type C to cancel it.", out)
        self.assertIn("Still focusing", out)
        self.assertIn("Session discarded", out)
        self.assertEqual(self.reload().sessions, [])

    def test_leftover_running_session_can_be_stopped(self):
        self.tracker.start("work", now=datetime.now() - timedelta(minutes=30))
        out = self.run_menu("1", "2", "5")
        self.assertIn("has been running since", out)
        self.assertIsNone(self.reload().active_session())

    def test_exit_warns_about_running_session(self):
        self.tracker.start("work")
        self.assertIn("still running", self.run_menu("5"))


class TestHistory(MenuTestCase):
    def setUp(self):
        super().setUp()
        self.tracker.add("study", timedelta(minutes=40), note="essay")
        self.tracker.add("work", timedelta(hours=1))

    def test_recent_sessions(self):
        out = self.run_menu("2", "1", "", "5", "5")
        self.assertIn("essay", out)
        self.assertIn("1h 00m", out)

    def test_filter_by_activity(self):
        out = self.run_menu("2", "3", "2", "", "5", "5")
        table = out.split("Which activity?")[1]
        self.assertIn("work", table)
        self.assertNotIn("essay", table)

    def test_delete_session(self):
        self.run_menu("2", "4", "x", "1", "y", "5", "5")
        self.assertEqual([s.id for s in self.reload().sessions], [2])

    def test_delete_unknown_session_shows_error(self):
        out = self.run_menu("2", "4", "42", "5", "5")
        self.assertIn("No session with id 42.", out)
        self.assertEqual(len(self.reload().sessions), 2)


class TestStatistics(MenuTestCase):
    def test_all_time_stats(self):
        self.tracker.add("study", timedelta(minutes=30))
        self.tracker.add("study", timedelta(minutes=90))
        out = self.run_menu("3", "4", "", "5", "5")
        self.assertIn("Sessions:         2", out)
        self.assertIn("Average session:  1h 00m", out)
        self.assertIn("Longest session:  1h 30m", out)
        self.assertIn("Current streak:   1 day", out)

    def test_empty_stats(self):
        self.assertIn("No focus time recorded.", self.run_menu("3", "1", "", "5", "5"))


class TestActivities(MenuTestCase):
    def test_add_rename_delete(self):
        self.run_menu("4", "2", "reading", "5", "5")
        self.assertEqual(self.reload().activities(), ["reading"])

        self.tracker = self.reload()
        self.run_menu("4", "3", "1", "novels", "5", "5")
        self.assertEqual(self.reload().activities(), ["novels"])

        self.tracker = self.reload()
        self.run_menu("4", "4", "1", "y", "5", "5")
        self.assertEqual(self.reload().activities(), [])

    def test_duplicate_activity_shows_error(self):
        self.tracker.add_activity("Work")
        out = self.run_menu("4", "2", "work", "6", "5")
        self.assertIn("Activity 'Work' already exists.", out)

    def test_delete_activity_warns_about_sessions(self):
        self.tracker.add("work", timedelta(hours=1))
        out = self.run_menu("4", "4", "1", "n", "6", "5")
        self.assertIn("its 1 session(s)", out)
        self.assertEqual(len(self.reload().sessions), 1)

    def test_log_past_session_retries_bad_input(self):
        out = self.run_menu("4", "5", "gym", "lots", "1h15m", "yesterday",
                            "2026-10-14 18:30", "leg day", "6", "5")
        self.assertIn("Invalid duration 'lots'", out)
        self.assertIn("'yesterday' isn't a valid time", out)
        [s] = self.reload().sessions
        self.assertEqual((s.activity, s.end, s.duration(), s.note),
                         ("gym", datetime(2026, 10, 14, 18, 30), timedelta(minutes=75), "leg day"))

    def test_view_activities(self):
        self.tracker.add("work", timedelta(hours=2))
        out = self.run_menu("4", "1", "", "6", "5")
        self.assertRegex(out, r"work\s+1\s+2h 00m")


if __name__ == "__main__":
    unittest.main()
