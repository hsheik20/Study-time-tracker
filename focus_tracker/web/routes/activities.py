"""Activities with their totals, plus create / rename / delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from focus_tracker.tracker import Tracker
from focus_tracker.web.deps import get_tracker
from focus_tracker.web.schemas import ActivityName
from focus_tracker.web.serializers import activity_dict

router = APIRouter(tags=["activities"])
# Routes use {name:path} so names containing "/" (e.g. "C++ / data") still match.


@router.get("/activities")
def list_activities(tracker: Tracker = Depends(get_tracker)) -> dict:
    overview = tracker.activity_overview()
    activities = [activity_dict(info, next(iter(tracker.history(info.name, limit=1)), None))
                  for info in overview]
    activities.sort(key=lambda a: a["focused_seconds"], reverse=True)
    return {"activities": activities}


@router.post("/activities", status_code=201)
def create_activity(body: ActivityName, tracker: Tracker = Depends(get_tracker)) -> dict:
    return {"name": tracker.add_activity(body.name)}


@router.patch("/activities/{name:path}")
def rename_activity(name: str, body: ActivityName,
                    tracker: Tracker = Depends(get_tracker)) -> dict:
    """Rename an activity; its past sessions are renamed too."""
    return {"name": tracker.rename_activity(name, body.name)}


@router.delete("/activities/{name:path}")
def delete_activity(name: str, tracker: Tracker = Depends(get_tracker)) -> dict:
    """Delete an activity and all of its sessions."""
    removed = tracker.delete_activity(name)
    return {"deleted": name, "sessions_deleted": len(removed)}
