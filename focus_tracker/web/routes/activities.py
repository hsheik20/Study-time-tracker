"""Activities with their totals."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from focus_tracker.tracker import Tracker
from focus_tracker.web.deps import get_tracker
from focus_tracker.web.serializers import activity_dict

router = APIRouter(tags=["activities"])


@router.get("/activities")
def list_activities(tracker: Tracker = Depends(get_tracker)) -> dict:
    overview = tracker.activity_overview()
    activities = [activity_dict(info, next(iter(tracker.history(info.name, limit=1)), None))
                  for info in overview]
    activities.sort(key=lambda a: a["focused_seconds"], reverse=True)
    return {"activities": activities}
