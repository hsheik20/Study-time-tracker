"""Session history, the running session, and the focus timer controls."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from focus_tracker.tracker import Tracker
from focus_tracker.web.deps import get_now, get_tracker
from focus_tracker.web.schemas import LogSession, SessionDetails, StartSession
from focus_tracker.web.serializers import seconds, session_dict

router = APIRouter(tags=["sessions"])


def active_payload(tracker: Tracker, now: datetime) -> dict:
    session = tracker.active_session()
    target = tracker.last_target()
    return {
        "session": session_dict(session, now) if session else None,
        "suggested_minutes": int(target.total_seconds() // 60) if target else 25,
        "recent_locations": tracker.recent_locations(),
        "server_time": now.isoformat(timespec="seconds"),
    }


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


@router.post("/sessions", status_code=201)
def log_session(body: LogSession, tracker: Tracker = Depends(get_tracker),
                now: datetime = Depends(get_now)) -> dict:
    """Log a past session that wasn't timed."""
    ended = body.ended_at.replace(tzinfo=None) if body.ended_at else now
    if ended > now + timedelta(minutes=1):
        raise HTTPException(422, "A logged session can't end in the future.")
    session = tracker.add(body.activity, timedelta(minutes=body.minutes), ended,
                          body.note, body.location)
    return {"session": session_dict(session, now)}


# --- The running session --------------------------------------------------
# These are declared before /sessions/{session_id} so "active" isn't read as an id.


@router.get("/sessions/active")
def active_session(tracker: Tracker = Depends(get_tracker),
                   now: datetime = Depends(get_now)) -> dict:
    return active_payload(tracker, now)


@router.post("/sessions/active", status_code=201)
def start_session(body: StartSession, tracker: Tracker = Depends(get_tracker),
                  now: datetime = Depends(get_now)) -> dict:
    tracker.start(body.activity, body.note, now=now, target=timedelta(minutes=body.minutes),
                  location=body.location)
    return active_payload(tracker, now)


@router.post("/sessions/active/pause")
def pause_session(tracker: Tracker = Depends(get_tracker),
                  now: datetime = Depends(get_now)) -> dict:
    tracker.pause(now)
    return active_payload(tracker, now)


@router.post("/sessions/active/resume")
def resume_session(tracker: Tracker = Depends(get_tracker),
                   now: datetime = Depends(get_now)) -> dict:
    tracker.resume(now)
    return active_payload(tracker, now)


@router.post("/sessions/active/stop")
def stop_session(tracker: Tracker = Depends(get_tracker),
                 now: datetime = Depends(get_now)) -> dict:
    """End early, saving the time actually focused."""
    session = tracker.stop(now)
    return {"session": session_dict(session, now)}


@router.post("/sessions/active/cancel")
def cancel_session(tracker: Tracker = Depends(get_tracker),
                   now: datetime = Depends(get_now)) -> dict:
    """Discard the running session without saving it."""
    session = tracker.cancel()
    return {"session": session_dict(session, now)}


# --- One session ------------------------------------------------------------


@router.get("/sessions/{session_id}")
def get_session(session_id: int, tracker: Tracker = Depends(get_tracker),
                now: datetime = Depends(get_now)) -> dict:
    return {"session": session_dict(tracker.find_session(session_id), now)}


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, body: SessionDetails,
                   tracker: Tracker = Depends(get_tracker),
                   now: datetime = Depends(get_now)) -> dict:
    """Save details such as distractions and a reflection."""
    session = tracker.annotate(session_id, **body.model_dump(exclude_none=True))
    return {"session": session_dict(session, now)}


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, tracker: Tracker = Depends(get_tracker)) -> Response:
    if tracker.find_session(session_id).active:
        raise HTTPException(409, "That session is still running. End or cancel it first.")
    tracker.delete(session_id)
    return Response(status_code=204)
