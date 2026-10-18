"""Drawing the live focus-session screen.

The screen is a fixed-height block of lines that is redrawn in place with ANSI
cursor movement (supported by VS Code's terminal and modern terminals).
Every character used is one column wide, so widths can be computed with len().
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

# --- Pieces -----------------------------------------------------------------

CAR = "o=o>"
ROAD = "·"
FINISH = "|▚▞"

FRAME_WIDTH = 64  # preferred screen width
MIN_FRAME_WIDTH = 44  # below this, fall back to a single status line

# 3x5 digit font; each cell is drawn two columns wide so digits look square.
_GLYPHS = {
    "0": ["###", "# #", "# #", "# #", "###"],
    "1": [" # ", "## ", " # ", " # ", "###"],
    "2": ["###", "  #", "###", "#  ", "###"],
    "3": ["###", "  #", " ##", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"],
    "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"],
    "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"],
    "9": ["###", "# #", "###", "  #", "###"],
    ":": [" ", "#", " ", "#", " "],
}
BIG_HEIGHT = 5


def big_text(text: str) -> list[str]:
    """Render digits and colons as large block characters (5 rows)."""
    return [
        " ".join(
            "".join("██" if cell == "#" else "  " for cell in _GLYPHS[ch][row]) for ch in text
        )
        for row in range(BIG_HEIGHT)
    ]


# 5x5 block letters for the completion banner.
_LETTERS = {
    "W": ["█   █", "█   █", "█ █ █", "██ ██", "█   █"],
    "E": ["█████", "█    ", "████ ", "█    ", "█████"],
    "L": ["█    ", "█    ", "█    ", "█    ", "█████"],
    "D": ["████ ", "█   █", "█   █", "█   █", "████ "],
    "O": [" ███ ", "█   █", "█   █", "█   █", " ███ "],
    "N": ["█   █", "██  █", "█ █ █", "█  ██", "█   █"],
    "!": ["█", "█", "█", " ", "█"],
    " ": ["  "] * 5,
}


def banner_text(text: str) -> list[str]:
    """Render a word in large block letters (5 rows)."""
    return [" ".join(_LETTERS[ch][row] for ch in text) for row in range(5)]


def race_track(percent: int, width: int = 32) -> str:
    """The car `percent` of the way along the road; its nose reaches the finish
    line at 100%. Position comes only from progress, so the car stays put while
    the session is paused."""
    room = width - len(CAR)
    position = room * min(max(percent, 0), 100) // 100
    return ROAD * position + CAR + ROAD * (room - position) + FINISH


def progress_bar(percent: int, width: int) -> str:
    filled = width * min(max(percent, 0), 100) // 100
    return "█" * filled + "░" * (width - filled)


# --- Layout -----------------------------------------------------------------


@dataclass
class ScreenState:
    activity: str
    status: str  # e.g. "● ACTIVE", "‖ PAUSED", "✓ COMPLETE"
    clock: str  # "24:59"
    caption: str  # shown under the clock
    percent: int | None  # None for open-ended sessions
    focused: str  # "6m 15s"
    controls: str  # bottom line: key help, a y/n question, or empty
    notice: str = ""


Line = tuple[str, str]  # (style, text)


def _center(text: str, width: int) -> str:
    return text.center(width).rstrip()


def fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def build_screen(state: ScreenState, width: int, big_clock: bool = True) -> list[Line]:
    inner = width - 4
    title = fit(f"FOCUS SESSION  ·  {state.activity}", inner - len(state.status) - 2)
    header = title + " " * (inner - len(title) - len(state.status)) + state.status

    lines: list[Line] = [
        ("border", "╭" + "─" * (width - 2) + "╮"),
        ("header", f"│ {header} │"),
        ("border", "╰" + "─" * (width - 2) + "╯"),
        ("", ""),
    ]

    clock_rows = big_text(state.clock) if big_clock else [state.clock]
    lines += [("clock", _center(row, width)) for row in clock_rows]
    lines += [("caption", _center(state.caption, width)), ("", "")]

    if state.percent is not None:
        track = race_track(state.percent, width - 8 - len(FINISH))
        # The bar plus "  NNN%" is exactly as wide as the track, so they line up.
        bar = f"{progress_bar(state.percent, len(track) - 6)}  {state.percent:3d}%"
        lines += [("track", _center(track, width)), ("bar", _center(bar, width))]
    else:
        lines += [
            ("caption", _center("Open-ended session: no finish line", width)),
            ("caption", _center(f"{state.focused} focused", width)),
        ]

    lines += [
        ("", ""),
        ("rule", "─" * width),
        ("controls", _center(state.controls, width)),
        ("notice", _center(state.notice, width)),
    ]
    return lines


def celebration(activity: str, focused: str, encouragement: str, today: str,
                width: int) -> list[Line]:
    """The "session complete" message shown after the chime."""
    banner = banner_text("WELL DONE!")
    if len(banner[0]) > width:  # too narrow for block letters
        banner = ["★  WELL DONE!  ★"]
    title = "✓  SESSION COMPLETE"
    return [
        ("", ""),
        ("celebrate-border", "╭" + "─" * (width - 2) + "╮"),
        ("celebrate-title", "│" + title.center(width - 2) + "│"),
        ("celebrate-border", "╰" + "─" * (width - 2) + "╯"),
        ("", ""),
        *[("celebrate", _center(row, width)) for row in banner],
        ("", ""),
        ("header", _center(fit(f"You focused on {activity} for {focused}.", width), width)),
        ("celebrate-text", _center(encouragement, width)),
        ("caption", _center(today, width)),
        ("", ""),
    ]


def screen_height(big_clock: bool) -> int:
    return 12 + (BIG_HEIGHT if big_clock else 1)


# --- Drawing ----------------------------------------------------------------

_RESET = "\x1b[0m"
_STYLES = {
    "border": "\x1b[36m",  # cyan
    "header": "\x1b[1m",  # bold
    "clock": "\x1b[1;36m",  # bold cyan
    "clock-paused": "\x1b[1;33m",  # bold yellow
    "caption": "\x1b[2m",  # dim
    "rule": "\x1b[2m",
    "notice": "\x1b[33m",  # yellow
    "celebrate": "\x1b[1;32m",  # bold green
    "celebrate-border": "\x1b[32m",
    "celebrate-title": "\x1b[1;32m",
    "celebrate-text": "\x1b[1;33m",  # bold yellow
    "day": "\x1b[1;36m",  # bold cyan
    "columns": "\x1b[1;95m",  # bold bright magenta: history column headings
    "footer": "\x1b[2m",
}
# Session statuses in the history table.
_ROW_STATUSES = [
    (r"✓ Completed", "\x1b[32m"),  # green
    (r"■ Ended at \d+%", "\x1b[33m"),  # yellow
    (r"● Running", "\x1b[1;36m"),
    (r"‖ Paused", "\x1b[1;33m"),
    (r"· Untimed", "\x1b[2m"),
]
_STATUS_COLORS = {"ACTIVE": "\x1b[1;32m", "PAUSED": "\x1b[1;33m"}


def paint(style: str, text: str, paused: bool = False) -> str:
    """Add ANSI colors to one line of the screen."""
    if not text:
        return text
    if style == "clock" and paused:
        style = "clock-paused"
    if style == "header":
        for word, color in _STATUS_COLORS.items():
            text = re.sub(rf"\S {word}", lambda m, c=color: f"{c}{m[0]}{_RESET}\x1b[1m", text)
    elif style == "track":
        text = text.replace(CAR, f"\x1b[1;31m{CAR}{_RESET}").replace(FINISH, f"\x1b[1m{FINISH}{_RESET}")
        return text
    elif style == "bar":
        text = re.sub(r"(█+)", f"\x1b[32m\\1{_RESET}", text)
        return re.sub(r"(░+)", f"\x1b[2m\\1{_RESET}", text)
    elif style == "row":
        text = re.sub(r"^(\s*#\d+)", f"\x1b[2m\\1{_RESET}", text)  # dim session id
        for pattern, color in _ROW_STATUSES:
            text = re.sub(pattern, lambda m, c=color: f"{c}{m[0]}{_RESET}", text)
        return text
    elif style == "controls":
        return re.sub(r"(\[[^\]]+\])", f"\x1b[1;36m\\1{_RESET}", text)
    prefix = _STYLES.get(style)
    return f"{prefix}{text}{_RESET}" if prefix else text


class LiveScreen:
    """Redraws a block of lines in place, only when something changed."""

    HIDE_CURSOR = "\x1b[?25l"
    SHOW_CURSOR = "\x1b[?25h"

    def __init__(self, write: Callable[[str], None], color: bool = True):
        self.write = write
        self.color = color
        self.height = 0
        self.last: list[str] | None = None

    def draw(self, lines: list[Line], paused: bool = False) -> None:
        rendered = [paint(style, text, paused) if self.color else text for style, text in lines]
        if rendered == self.last:
            return
        if self.height == 0:
            out = self.HIDE_CURSOR
        elif self.height == 1:
            out = "\r"
        else:  # back to the top-left of the previous drawing
            out = f"\r\x1b[{self.height - 1}A"
        out += "\n".join("\x1b[2K" + line for line in rendered)
        out += "\x1b[J"  # clear anything left below (e.g. after a resize)
        self.write(out)
        self.height = len(rendered)
        self.last = rendered

    def close(self) -> None:
        self.write("\n" + self.SHOW_CURSOR)
