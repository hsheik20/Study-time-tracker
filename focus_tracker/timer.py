"""The live focus timer: countdown display plus pause / end early / cancel controls."""

from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from focus_tracker.display import (
    FINISH,
    FRAME_WIDTH,
    MIN_FRAME_WIDTH,
    Line,
    LiveScreen,
    ScreenState,
    build_screen,
    race_track,
    screen_height,
)
from focus_tracker.formatting import format_clock, format_duration
from focus_tracker.models import Session
from focus_tracker.tracker import Tracker

# Track size for the single-line fallback display.
COMPACT_TRACK_WIDTH = 32
MIN_COMPACT_TRACK_WIDTH = 12

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
        color: bool = False,
        terminal_size: Callable[[], os.terminal_size] = shutil.get_terminal_size,
    ):
        """`live` draws a full-screen display that updates in place; otherwise
        each update is printed as one status line (for non-interactive output)."""
        self.tracker = tracker
        self.keys = keys
        self.write = write
        self.live = live
        self.clock = clock
        self.terminal_size = terminal_size
        self.screen = LiveScreen(write, color) if live else None
        self.pending: str | None = None  # "end" or "cancel" awaiting y/n
        self.notice = ""

    def run(self) -> TimerResult:
        session = self.tracker.active_session()
        if not self.live:
            self.write("Controls (type a letter and press Enter): "
                       "P = pause/resume, E = end early, C = cancel\n\n")
        try:
            try:
                result = self._loop(session)
            except KeyboardInterrupt:
                # Ctrl+C means "I'm done": keep the time focused so far.
                self.tracker.stop(self.clock())
                result = TimerResult("ended", session)
            if self.live:
                self.pending, self.notice = None, ""
                self._render(session, session.end or self.clock(), result.outcome)
        finally:
            if self.screen:
                self.screen.close()  # also restores the cursor after errors
        return result

    def _loop(self, session: Session) -> TimerResult:
        while True:
            now = self.clock()
            if self.tracker.complete_if_due(now):
                return TimerResult("completed", session)
            self._render(session, now)
            key = self.keys.read_key(self.TICK)
            if key is not None:
                result = self._handle(key.lower(), session)
                if result:
                    return result

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

    # --- Full-screen display ---------------------------------------------

    FINAL_STATUS = {"completed": "✓ COMPLETE", "ended": "■ ENDED", "cancelled": "✕ DISCARDED"}

    def screen_state(self, session: Session, now: datetime, outcome: str | None = None) -> ScreenState:
        focused = session.duration(now)
        if session.target:
            clock = format_clock(session.remaining(now), round_up=True)
            caption = f"remaining of {format_duration(session.target)}"
            # Round down so 100% only shows once the time is really up.
            percent = min(100, int(focused / session.target * 100))
        else:
            clock, caption, percent = format_clock(focused), "elapsed", None
        if session.paused and not outcome:
            caption = "paused · press P to resume"

        if outcome:
            status, controls = self.FINAL_STATUS[outcome], ""
        else:
            status = "‖ PAUSED" if session.paused else "● ACTIVE"
            if self.pending == "end":
                controls = f"End now and save {format_duration(focused)}?   [Y] Yes   [N] No"
            elif self.pending == "cancel":
                controls = "Discard this session?   [Y] Yes   [N] No"
            else:
                pause = "Resume" if session.paused else "Pause"
                controls = f"[P] {pause}     [E] End early     [C] Cancel"
        return ScreenState(session.activity, status, clock, caption, percent,
                           format_duration(focused), controls, self.notice)

    def screen_lines(self, session: Session, now: datetime, outcome: str | None = None) -> list[Line]:
        """The full display, sized to the terminal; a single status line if it
        can't fit (very narrow or short terminals)."""
        columns, rows = self.terminal_size()
        width = min(FRAME_WIDTH, columns - 1)
        if width >= MIN_FRAME_WIDTH:
            state = self.screen_state(session, now, outcome)
            for big_clock in (True, False):
                if screen_height(big_clock) < rows:
                    return build_screen(state, width, big_clock)
        line = self.status_line(session, now, self._track_width(columns))
        return [("", line[: columns - 1])]

    # --- Single-line display ---------------------------------------------

    def status_line(self, session: Session, now: datetime,
                    track_width: int = COMPACT_TRACK_WIDTH) -> str:
        state = "PAUSED " if session.paused else "FOCUS  "
        focused = session.duration(now)
        if session.target:
            remaining = format_clock(session.remaining(now), round_up=True)
            line = f"{state} {remaining} remaining"
        else:
            line = f"{state} {format_clock(focused)} elapsed"

        # Prompts replace the track so the line fits an 80-column terminal.
        if self.pending == "end":
            return f"{line}   End now and save {format_duration(focused)}? (y/n)"
        if self.pending == "cancel":
            return f"{line}   Discard this session? (y/n)"
        if self.notice:
            return f"{line}   {self.notice}"
        if session.target:
            percent = min(100, int(focused / session.target * 100))
            line += f"  {race_track(percent, track_width)} {percent:3d}%"
        return line

    @staticmethod
    def _track_width(columns: int) -> int:
        """Shrink the one-line track on narrow terminals so the line fits."""
        # "FOCUS   25:00 remaining  " + track + finish + " 100%", plus a spare column.
        fixed = 25 + len(FINISH) + 5 + 1
        return max(MIN_COMPACT_TRACK_WIDTH, min(COMPACT_TRACK_WIDTH, columns - fixed))

    def _render(self, session: Session, now: datetime, outcome: str | None = None) -> None:
        if self.live:
            self.screen.draw(self.screen_lines(session, now, outcome),
                             paused=session.paused and not outcome)
        else:
            self.write(self.status_line(session, now) + "\n")
