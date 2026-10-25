"""Turn tracker objects into JSON-friendly dicts.

Times are local ISO-8601 strings without a timezone (the same local time the
CLI shows); durations are whole seconds.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from focus_tracker.history_view import status_key
from focus_tracker.models import Session
from focus_tracker.tracker import ActivityInfo, Stats


def iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def seconds(value: timedelta | None) -> int | None:
    return None if value is None else int(value.total_seconds())


def session_dict(session: Session, now: datetime) -> dict:
    focused = session.duration(now)
    percent = None
    if session.target:
        percent = min(100, int(focused / session.target * 100))
    return {
        "id": session.id,
        "activity": session.activity,
        "start": iso(session.start),
        "end": iso(session.end),
        "note": session.note,
        "status": status_key(session),
        "focused_seconds": seconds(focused),
        "target_seconds": seconds(session.target),
        "remaining_seconds": seconds(max(session.remaining(now), timedelta()))
        if session.target else None,
        "percent": percent,
        "paused": session.paused,
        "pause_count": len(session.pauses),
        "paused_seconds": seconds(sum(
            ((p.end or now) - p.start for p in session.pauses), timedelta())),
        "location": session.location,
        "distractions": list(session.distractions),
        "reflection": session.reflection,
        "sample": session.sample,
    }


def stats_dict(stats: Stats) -> dict:
    return {
        "focused_seconds": seconds(stats.total),
        "sessions": stats.count,
        "average_seconds": seconds(stats.average),
        "longest_seconds": seconds(stats.longest),
        "by_activity": [{"name": name, "focused_seconds": seconds(total)}
                        for name, total in stats.totals.items()],
    }


def activity_dict(info: ActivityInfo, last_session: Session | None) -> dict:
    return {
        "name": info.name,
        "sessions": info.sessions,
        "focused_seconds": seconds(info.total),
        "last_session": iso(last_session.start) if last_session else None,
    }
