"""The live focus timer: countdown display plus pause / end early / cancel controls."""

from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from focus_tracker.formatting import format_clock, format_duration
from focus_tracker.models import Session
from focus_tracker.tracker import Tracker

BAR_WIDTH = 20


# --- Key readers ------------------------------------------------------------
#
# A key reader is a context manager with `read_key(timeout)`, which returns one
# key ("\n" for Enter) or None if nothing was pressed within `timeout` seconds.


class LineKeys:
    """Fallback when there's no interactive terminal (piped input, tests).

    Reads a whole line per command, so it blocks instead of ticking; the timer
    still checks the countdown after every command.
    """

    def __init__(self, input_fn: Callable[[str], str]):
        self.input = input_fn

    def __enter__(self) -> LineKeys:
        return self

    def __exit__(self, *exc) -> None:
        pass

    def read_key(self, timeout: float) -> str | None:
        return self.input("> ").strip().lower()[:1] or "\n"


class PosixKeys:
    """Single keypresses on macOS/Linux, without waiting for Enter or echoing."""

    def __enter__(self) -> PosixKeys:
        import termios
        import tty

        self.fd = sys.stdin.fileno()
        self.saved = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)  # keeps Ctrl+C working as KeyboardInterrupt
        return self

    def __exit__(self, *exc) -> None:
        import termios

        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)

    def read_key(self, timeout: float) -> str | None:
        import select

        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return None
        return os.read(self.fd, 1).decode(errors="ignore") or None


class WindowsKeys:
    """Single keypresses on Windows."""

    def __enter__(self) -> WindowsKeys:
        return self

    def __exit__(self, *exc) -> None:
        pass

    def read_key(self, timeout: float) -> str | None:
        import msvcrt

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ("\x00", "\xe0"):  # arrow/function keys send two codes
                    msvcrt.getwch()
                    continue
                if key == "\x03":
                    raise KeyboardInterrupt
                return key
            time.sleep(0.02)
        return None


def terminal_keys() -> PosixKeys | WindowsKeys:
    return WindowsKeys() if os.name == "nt" else PosixKeys()


# --- Timer ------------------------------------------------------------------


@dataclass
class TimerResult:
    outcome: str  # "completed", "ended" (stopped early) or "cancelled"
    session: Session


class FocusTimer:
    TICK = 0.25  # seconds between screen refreshes

    def __init__(
        self,
        tracker: Tracker,
        keys,
        write: Callable[[str], None],
        live: bool = True,
        clock: Callable[[], datetime] = datetime.now,
    ):
        """`live` redraws one status line in place; otherwise each update is
        printed on its own line (for non-interactive output)."""
        self.tracker = tracker
        self.keys = keys
        self.write = write
        self.live = live
        self.clock = clock
        self.pending: str | None = None  # "end" or "cancel" awaiting y/n
        self.notice = ""
        self._last_line = ""

    def run(self) -> TimerResult:
        session = self.tracker.active_session()
        how = "press" if self.live else "type a letter and press Enter:"
        self.write(f"Controls ({how}): P = pause/resume, E = end early, C = cancel\n\n")
        try:
            while True:
                now = self.clock()
                if self.tracker.complete_if_due(now):
                    return self._finish(TimerResult("completed", session))
                self._render(session, now)
                key = self.keys.read_key(self.TICK)
                if key is not None:
                    result = self._handle(key.lower(), session)
                    if result:
                        return self._finish(result)
        except KeyboardInterrupt:
            # Ctrl+C means "I'm done": keep the time focused so far.
            self.tracker.stop(self.clock())
            return self._finish(TimerResult("ended", session))

    def _handle(self, key: str, session: Session) -> TimerResult | None:
        now = self.clock()
        self.notice = ""
        if self.pending:
            action, self.pending = self.pending, None
            if key != "y":
                return None
            if action == "end":
                self.tracker.stop(now)
                return TimerResult("ended", session)
            self.tracker.cancel()
            return TimerResult("cancelled", session)

        if key in ("p", " "):
            if session.paused:
                self.tracker.resume(now)
            else:
                self.tracker.pause(now)
        elif key in ("e", "\n", "\r"):
            self.pending = "end"
        elif key == "c":
            self.pending = "cancel"
        else:
            self.notice = "Use P, E or C."
        return None

    def status_line(self, session: Session, now: datetime) -> str:
        state = "PAUSED " if session.paused else "FOCUS  "
        focused = session.duration(now)
        if session.target:
            remaining = format_clock(session.remaining(now), round_up=True)
            line = f"{state} {remaining} remaining"
        else:
            line = f"{state} {format_clock(focused)} elapsed"

        # Prompts replace the progress bar so the line fits an 80-column terminal.
        if self.pending == "end":
            return f"{line}   End now and save {format_duration(focused)}? (y/n)"
        if self.pending == "cancel":
            return f"{line}   Discard this session? (y/n)"
        if self.notice:
            return f"{line}   {self.notice}"
        if session.target:
            # Round down so 100% only shows once the time is really up.
            percent = min(100, int(focused / session.target * 100))
            filled = percent * BAR_WIDTH // 100
            line += f"  {'█' * filled}{'░' * (BAR_WIDTH - filled)} {percent:3d}%"
        return line

    def _render(self, session: Session, now: datetime) -> None:
        line = self.status_line(session, now)
        if not self.live:
            self.write(line + "\n")
            return
        if line == self._last_line:
            return
        # Stay within one terminal row so "\r" can redraw the line in place.
        line = line[: shutil.get_terminal_size().columns - 1]
        self.write("\r" + line.ljust(len(self._last_line)))
        self._last_line = line

    def _finish(self, result: TimerResult) -> TimerResult:
        if self.live:
            if result.outcome == "completed":
                self._render(result.session, result.session.end)
            self.write("\n")
        if result.outcome == "completed":
            self.write("\a")  # terminal bell
        return result
