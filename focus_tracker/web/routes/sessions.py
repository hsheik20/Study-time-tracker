"""Session history and the currently running session."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from focus_tracker.tracker import Tracker
from focus_tracker.web.deps import get_now, get_tracker
from focus_tracker.web.serializers import seconds, session_dict

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
def list_sessions(
    activity: str | None = None,
    limit: int | None = Query(None, ge=1, le=1000),
    tracker: Tracker = Depends(get_tracker),
    now: datetime = Depends(get_now),
) -> dict:
    """Sessions newest first, optionally for one activity."""
    if activity and tracker.find_activity(activity) is None:
        raise HTTPException(404, f"No activity named '{activity}'.")
    matching = tracker.history(activity)
    shown = matching[:limit] if limit else matching
    return {
        "total": len(matching),
        "focused_seconds": seconds(sum((s.duration(now) for s in matching), timedelta())),
        "sessions": [session_dict(s, now) for s in shown],
    }


@router.get("/sessions/active")
def active_session(tracker: Tracker = Depends(get_tracker),
                   now: datetime = Depends(get_now)) -> dict:
    session = tracker.active_session()
    return {"session": session_dict(session, now) if session else None,
            "suggested_minutes": int(tracker.last_target().total_seconds() // 60)
            if tracker.last_target() else 25}
