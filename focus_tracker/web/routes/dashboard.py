"""Everything the dashboard page needs, in one request."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from focus_tracker.tracker import Tracker
from focus_tracker.web.deps import get_now, get_tracker
from focus_tracker.web.serializers import seconds, session_dict, stats_dict

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(tracker: Tracker = Depends(get_tracker), now: datetime = Depends(get_now)) -> dict:
    active = tracker.active_session()
    return {
        "now": now.isoformat(timespec="seconds"),
        "today": stats_dict(tracker.stats("today", now)),
        "week": stats_dict(tracker.stats("week", now)),
        "all_time": stats_dict(tracker.stats("all", now)),
        "streak_days": tracker.streak(now),
        "last_7_days": [{"date": day.date().isoformat(), "focused_seconds": seconds(total)}
                        for day, total in tracker.daily_totals(7, now)],
        "active_session": session_dict(active, now) if active else None,
        "recent_sessions": [session_dict(s, now) for s in tracker.history(limit=5)],
        "activity_count": len(tracker.activities()),
    }
