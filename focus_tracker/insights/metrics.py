"""Weekly numbers for the AI insights, computed entirely in Python.

Claude only interprets these numbers; it never does the arithmetic. The
summary is also deliberately compact (aggregates plus a capped, trimmed set of
notes and reflections) to keep each API call small and cheap.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from focus_tracker.history_view import status_key
from focus_tracker.models import Session
from focus_tracker.tracker import Tracker

TIME_OF_DAY = [  # (label, first hour, last hour exclusive)
    ("morning (5am-12pm)", 5, 12),
    ("afternoon (12-5pm)", 12, 17),
    ("evening (5-9pm)", 17, 21),
    ("night (9pm-5am)", 21, 29),  # wraps past midnight
]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MAX_JOURNAL_ENTRIES = 25   # notes/reflections sent to Claude
MAX_NOTE_CHARS = 200
MAX_REFLECTION_CHARS = 400
COMPARISON_WEEKS = 4
MIN_SESSIONS_FOR_PATTERNS = 5
MIN_DAYS_FOR_PATTERNS = 3
SHORT_SESSION_MINUTES = 5  # shorter sessions are counted, but too brief to show much on their own


@dataclass(frozen=True)
class Week:
    start: datetime  # Monday 00:00
    end: datetime    # the next Monday 00:00

    @classmethod
    def containing(cls, moment: datetime, weeks_back: int = 0) -> Week:
        midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        start = midnight - timedelta(days=moment.weekday(), weeks=weeks_back)
        return cls(start, start + timedelta(days=7))

    def previous(self, weeks: int = 1) -> Week:
        return Week(self.start - timedelta(weeks=weeks), self.end - timedelta(weeks=weeks))

    @property
    def key(self) -> str:
        return self.start.date().isoformat()

    def label(self) -> str:
        last = self.end - timedelta(days=1)
        return f"{self.start:%b} {self.start.day} – {last:%b} {last.day}, {last.year}"


def _minutes(delta: timedelta) -> float:
    return round(delta.total_seconds() / 60, 1)


def _focused_in(session: Session, week: Week, now: datetime) -> timedelta:
    """Focused time inside the week (sessions spanning a boundary are split)."""
    return session.focused_within(week.start, now) - session.focused_within(week.end, now)


def _bucket(hour: int) -> str:
    for label, first, last in TIME_OF_DAY:
        if first <= hour < last or first <= hour + 24 < last:
            return label
    return TIME_OF_DAY[-1][0]


def _rate(completed: int, ended_early: int) -> float | None:
    timed = completed + ended_early
    return round(completed / timed, 2) if timed else None


class _Group:
    """Running totals for one slice of sessions (an activity, a location, ...)."""

    def __init__(self) -> None:
        self.focused = timedelta()
        self.sessions = 0
        self.outcomes: Counter[str] = Counter()

    def add(self, session: Session, focused: timedelta) -> None:
        self.focused += focused
        self.sessions += 1
        self.outcomes[status_key(session)] += 1

    def summary(self) -> dict:
        return {
            "sessions": self.sessions,
            "focused_minutes": _minutes(self.focused),
            "avg_session_minutes": _minutes(self.focused / self.sessions) if self.sessions else 0,
            "completion_rate": _rate(self.outcomes["completed"], self.outcomes["ended_early"]),
        }


def _week_sessions(tracker: Tracker, week: Week, now: datetime) -> list[tuple[Session, timedelta]]:
    result = []
    for s in tracker.sessions:
        if s.active:
            continue  # only finished sessions are analysed
        focused = _focused_in(s, week, now)
        if focused > timedelta():
            result.append((s, focused))
    return sorted(result, key=lambda pair: pair[0].start)


def _headline_numbers(pairs: list[tuple[Session, timedelta]]) -> dict:
    total = _Group()
    longest = timedelta()
    for s, focused in pairs:
        total.add(s, focused)
        longest = max(longest, focused)
    return {
        **total.summary(),
        "longest_session_minutes": _minutes(longest),
        "completed_sessions": total.outcomes["completed"],
        "ended_early_sessions": total.outcomes["ended_early"],
        "untimed_sessions": total.outcomes["untimed"],
    }


def _quality_note(sessions: int, days: int, short: int, enough: bool) -> str:
    """A neutral description of how much data there is (no guesses about intent)."""
    note = (f"{sessions} session(s) on {days} day(s)"
            + ("." if enough else f"; patterns need at least {MIN_SESSIONS_FOR_PATTERNS} sessions "
                                  f"over {MIN_DAYS_FOR_PATTERNS} days."))
    if short:
        note += f" {short} lasted under {SHORT_SESSION_MINUTES} minutes."
    return note


def weekly_metrics(tracker: Tracker, week: Week, now: datetime) -> dict:
    """Everything the report needs about `week`, as JSON-friendly values."""
    pairs = _week_sessions(tracker, week, now)
    headline = _headline_numbers(pairs)

    by_activity: dict[str, _Group] = defaultdict(_Group)
    by_time: dict[str, _Group] = defaultdict(_Group)
    by_location: dict[str, _Group] = defaultdict(_Group)
    by_day = [timedelta()] * 7
    distractions: Counter[str] = Counter()
    pauses = with_distractions = with_reflection = short = 0
    days_active: set = set()

    for s, focused in pairs:
        by_activity[s.activity].add(s, focused)
        by_time[_bucket(s.start.hour)].add(s, focused)
        by_location[s.location or "not recorded"].add(s, focused)
        by_day[s.start.weekday()] += focused
        days_active.add(s.start.date())
        pauses += len(s.pauses)
        if s.distractions:
            with_distractions += 1
            distractions.update(d.strip().lower() for d in s.distractions)
        if s.reflection:
            with_reflection += 1
        if focused < timedelta(minutes=SHORT_SESSION_MINUTES):
            short += 1

    total_minutes = headline["focused_minutes"] or 1

    def ranked(groups: dict[str, _Group], key: str) -> list[dict]:
        rows = [{key: name, **g.summary(),
                 "share_of_focus": round(_minutes(g.focused) / total_minutes, 2)}
                for name, g in groups.items()]
        return sorted(rows, key=lambda r: r["focused_minutes"], reverse=True)

    previous = []
    for back in range(1, COMPARISON_WEEKS + 1):
        earlier = week.previous(back)
        numbers = _headline_numbers(_week_sessions(tracker, earlier, now))
        if numbers["sessions"]:
            previous.append({"week_starting": earlier.key, "focused_minutes": numbers["focused_minutes"],
                             "sessions": numbers["sessions"],
                             "completion_rate": numbers["completion_rate"]})

    in_progress = week.start <= now < week.end
    elapsed_days = min(7, (now - week.start).days + 1) if in_progress else 7
    enough = headline["sessions"] >= MIN_SESSIONS_FOR_PATTERNS and len(days_active) >= MIN_DAYS_FOR_PATTERNS

    return {
        "week": {"start": week.key, "label": week.label(), "in_progress": in_progress,
                 "days_elapsed": elapsed_days},
        "totals": {**headline, "focused_hours": round(headline["focused_minutes"] / 60, 2),
                   "days_active": len(days_active), "pauses": pauses},
        "by_activity": ranked(by_activity, "activity"),
        "by_time_of_day": ranked(by_time, "time_of_day"),
        "by_location": ranked(by_location, "location"),
        "by_weekday": [{"day": WEEKDAYS[i], "focused_minutes": _minutes(by_day[i])} for i in range(7)],
        "distractions": {
            "sessions_reporting_any": with_distractions,
            "top": [{"distraction": name, "sessions": count} for name, count in distractions.most_common(8)],
        },
        "reflections_recorded": with_reflection,
        "previous_weeks": previous,
        "data_quality": {
            "enough_for_patterns": enough,
            "short_sessions": short,
            "short_session_minutes": SHORT_SESSION_MINUTES,
            "note": _quality_note(headline["sessions"], len(days_active), short, enough),
            "has_previous_weeks": bool(previous),
        },
    }


def journal_entries(tracker: Tracker, week: Week, now: datetime) -> list[dict]:
    """The week's notes, distractions and reflections: newest first, capped and trimmed."""
    entries = []
    for s, focused in reversed(_week_sessions(tracker, week, now)):
        if not (s.note or s.reflection or s.distractions):
            continue
        entries.append({
            "when": f"{WEEKDAYS[s.start.weekday()]} {s.start:%H:%M}",
            "activity": s.activity,
            "outcome": status_key(s),
            "focused_minutes": _minutes(focused),
            "location": s.location or None,
            "note": s.note[:MAX_NOTE_CHARS] or None,
            "distractions": s.distractions[:8] or None,
            "reflection": s.reflection[:MAX_REFLECTION_CHARS] or None,
            "short_session": focused < timedelta(minutes=SHORT_SESSION_MINUTES) or None,
        })
        if len(entries) == MAX_JOURNAL_ENTRIES:
            break
    return entries
