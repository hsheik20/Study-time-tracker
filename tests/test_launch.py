"""End-to-end checks that both ways of launching the app open the main menu."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN_FILE = PROJECT_ROOT / "focus_tracker" / "__main__.py"


class TestLaunch(unittest.TestCase):
    def launch(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "FOCUS_TRACKER_DATA": str(Path(tmp) / "data.json")}
            env.pop("PYTHONPATH", None)
            return subprocess.run(
                [sys.executable, *args], cwd=cwd, env=env, input="5\n",
                capture_output=True, text=True, timeout=30,
            )

    def assert_menu_shown(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FOCUS TRACKER", result.stdout)
        self.assertIn("Goodbye", result.stdout)

    def test_run_file_directly(self):
        # Like VS Code's Run button: run the file by path, from outside the project.
        with tempfile.TemporaryDirectory() as elsewhere:
            self.assert_menu_shown(self.launch([str(MAIN_FILE)], Path(elsewhere)))

    def test_run_as_module(self):
        self.assert_menu_shown(self.launch(["-m", "focus_tracker"], PROJECT_ROOT))

    def test_run_file_directly_with_command(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            result = self.launch([str(MAIN_FILE), "summary", "all"], Path(elsewhere))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("All time", result.stdout)


if __name__ == "__main__":
    unittest.main()
