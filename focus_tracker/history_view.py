"""The session history screen: sessions grouped by day with statuses and totals."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from itertools import groupby

from focus_tracker.display import Line, fit
from focus_tracker.formatting import format_duration
from focus_tracker.models import Session

HISTORY_WIDTH = 78
MIN_NOTE_WIDTH = 6  # below this the note column is dropped
STATUS_WIDTH = 14


def status_key(session: Session) -> str:
    """One of: running, paused, completed, ended_early, untimed."""
    if session.active:
        return "paused" if session.paused else "running"
    if session.target:
        # Allow a second of rounding from timestamps saved by older versions.
        if session.duration() >= session.target - timedelta(seconds=1):
            return "completed"
        return "ended_early"
    return "untimed"  # logged manually or open-ended


def session_status(session: Session) -> str:
    key = status_key(session)
    if key == "ended_early":
        percent = min(99, int(session.duration() / session.target * 100))
        return f"■ Ended at {percent}%"
    return {"running": "● Running", "paused": "‖ Paused", "completed": "✓ Completed",
            "untimed": "· Untimed"}[key]


def day_label(day: date, today: date) -> str:
    name = f"{day:%a}, {day:%b} {day.day}"
    if day.year != today.year:
        name += f", {day.year}"
    if day == today:
        return f"TODAY · {name}"
    if day == today - timedelta(days=1):
        return f"YESTERDAY · {name}"
    return name.upper()


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _spread(left: str, right: str, width: int) -> str:
    """`left` and `right` at opposite ends of a line `width` wide."""
    left = fit(left, width - len(right) - 2)
    return left + " " * (width - len(left) - len(right)) + right


def history_screen(
    sessions: list[Session],
    title: str,
    now: datetime,
    width: int = HISTORY_WIDTH,
    total_sessions: int | None = None,
) -> list[Line]:
    """Sessions (newest first) grouped by the day they started.

    `total_sessions` is how many exist in all, when `sessions` is only the most
    recent few; the footer then says "Showing 10 of 24".
    """
    width = min(width, HISTORY_WIDTH)
    inner = width - 4
    count = _plural(len(sessions), "session")
    lines: list[Line] = [
        ("border", "╭" + "─" * (width - 2) + "╮"),
        ("header", f"│ {_spread(f'SESSION HISTORY  ·  {title}', count, inner)} │"),
        ("border", "╰" + "─" * (width - 2) + "╯"),
    ]
    if not sessions:
        return lines + [("", ""), ("caption", "  No sessions yet. Start one from the main menu.")]

    # Column widths: the activity column fits the longest name (8-20 chars, less
    # on narrow terminals), and the note gets whatever room is left.
    other_columns = 2 + 5 + 1 + 11 + 2 + 2 + 7 + 2 + STATUS_WIDTH
    longest = max(len(s.activity) for s in sessions)
    activity_width = max(8, min(20, longest, width - other_columns))
    note_width = width - other_columns - activity_width - 2
    show_notes = note_width >= MIN_NOTE_WIDTH and any(s.note for s in sessions)

    def row(id_: str, time: str, activity: str, focused: str, status: str, note: str) -> str:
        text = (f"  {id_:<5} {time:<11}  {fit(activity, activity_width):<{activity_width}}  "
                f"{focused:>7}  {status:<{STATUS_WIDTH}}")
        if show_notes and note:
            text += "  " + fit(note, note_width)
        return text.rstrip()[:width]

    lines += [("", ""), ("columns", row("ID", "TIME", "ACTIVITY", "FOCUSED", "STATUS",
                                       "NOTE" if show_notes else ""))]

    today = now.date()
    for day, group in groupby(sessions, key=lambda s: s.start.date()):
        group = list(group)
        day_total = sum((s.duration(now) for s in group), timedelta())
        lines += [
            ("", ""),
            ("day", _spread(f"  {day_label(day, today)}", f"{format_duration(day_total)} focused",
                            width)),
            ("rule", "  " + "─" * (width - 2)),
        ]
        for s in group:
            end = f"{s.end:%H:%M}" if s.end else "now"
            lines.append(("row", row(f"#{s.id}", f"{s.start:%H:%M}–{end}", s.activity,
                                     format_duration(s.duration(now)), session_status(s),
                                     s.note)))

    total = sum((s.duration(now) for s in sessions), timedelta())
    shown = (f"Showing {len(sessions)} of {total_sessions} sessions"
             if total_sessions and total_sessions > len(sessions) else count)
    lines += [
        ("", ""),
        ("rule", "─" * width),
        ("footer", f"  {shown}  ·  {format_duration(total)} focused"),
    ]
    return lines
