import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from focus_tracker.cli import main
from focus_tracker.storage import Storage


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "sessions.json")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv), storage=self.storage)
        return code, out.getvalue(), err.getvalue()

    def test_full_flow(self):
        self.assertEqual(self.run_cli("start", "studying")[0], 0)
        code, out, _ = self.run_cli("status")
        self.assertIn("studying", out)
        self.assertEqual(self.run_cli("stop")[0], 0)
        self.run_cli("add", "work", "1h30m", "--ended", "2026-10-14 18:30", "-n", "report")

        code, out, _ = self.run_cli("log")
        self.assertIn("work", out)
        self.assertIn("report", out)

        code, out, _ = self.run_cli("summary", "all")
        self.assertIn("1h 30m", out)
        self.assertIn("Total", out)

    def test_errors_return_nonzero(self):
        code, _, err = self.run_cli("stop")
        self.assertEqual(code, 1)
        self.assertIn("No session", err)

        code, _, err = self.run_cli("add", "work", "lots")
        self.assertEqual(code, 1)
        self.assertIn("Invalid duration", err)

        code, _, err = self.run_cli("add", "work", "1h", "--ended", "yesterday")
        self.assertEqual(code, 1)

    def test_no_arguments_opens_menu(self):
        with patch("builtins.input", side_effect=["5"]):
            code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("FOCUS TRACKER", out)

    def test_empty_states(self):
        self.assertIn("No sessions", self.run_cli("log")[1])
        self.assertIn("No focus time", self.run_cli("summary")[1])
        self.assertIn("Not tracking", self.run_cli("status")[1])


if __name__ == "__main__":
    unittest.main()
