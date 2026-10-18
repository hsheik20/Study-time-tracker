"""Parsing and display helpers for durations."""

from __future__ import annotations

import math
import re
from datetime import timedelta

from focus_tracker.models import Session

_DURATION_RE = re.compile(r"^(?:(\d+)h)?\s*(?:(\d+)m)?$")


def parse_duration(text: str) -> timedelta:
    """Parse '1h30m', '2h', '45m', or a bare number of minutes like '90'."""
    text = text.strip().lower().replace(" ", "")
    if text.isdigit():
        return timedelta(minutes=int(text))
    match = _DURATION_RE.match(text)
    if not text or not match or not any(match.groups()):
        raise ValueError(f"Invalid duration '{text}'. Use e.g. 90, 45m, 2h, or 1h30m.")
    hours, minutes = (int(g) if g else 0 for g in match.groups())
    return timedelta(hours=hours, minutes=minutes)


def format_duration(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s" if minutes < 10 and seconds else f"{minutes}m"
    return f"{seconds}s"


def format_clock(delta: timedelta, round_up: bool = False) -> str:
    """Timer-style display: '04:05' or '1:02:03'. Countdowns round up, so the
    display reads 25:00 at the start and 00:01 in the final second."""
    seconds = max(0.0, delta.total_seconds())
    total = math.ceil(seconds) if round_up else int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


TIME_FMT = "%Y-%m-%d %H:%M"


def session_table(sessions: list[Session]) -> list[str]:
    width = max([len("Activity"), *(len(s.activity) for s in sessions)])
    lines = [f"{'ID':>4}  {'Started':<16}  {'Activity':<{width}}  {'Duration':>9}  Note"]
    for s in sessions:
        duration = format_duration(s.duration()) + ("*" if s.active else "")
        lines.append(
            f"{s.id:>4}  {s.start:{TIME_FMT}}  {s.activity:<{width}}  {duration:>9}  {s.note}"
            .rstrip()
        )
    if any(s.active for s in sessions):
        lines.append("* still running")
    return lines


def summary_lines(totals: dict[str, timedelta]) -> list[str]:
    """Per-activity totals with a proportional bar, followed by a grand total."""
    grand = sum(totals.values(), timedelta())
    width = max([len("Total"), *(len(a) for a in totals)])
    lines = []
    for activity, total in totals.items():
        bar = "█" * round(total / grand * 20) if grand else ""
        lines.append(f"{activity:<{width}}  {format_duration(total):>8}  {bar}")
    lines.append(f"{'Total':<{width}}  {format_duration(grand):>8}")
    return lines
