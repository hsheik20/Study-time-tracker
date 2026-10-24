"""Statistics for a period."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends

from focus_tracker.history_view import status_key
from focus_tracker.tracker import Tracker, period_start
from focus_tracker.web.deps import get_now, get_tracker
from focus_tracker.web.serializers import stats_dict

router = APIRouter(tags=["stats"])


@router.get("/stats")
def stats(
    period: Literal["today", "week", "month", "all"] = "week",
    tracker: Tracker = Depends(get_tracker),
    now: datetime = Depends(get_now),
) -> dict:
    since = period_start(period, now)
    in_period = [s for s in tracker.sessions if since is None or (s.end or now) > since]
    outcomes = {"completed": 0, "ended_early": 0, "untimed": 0}
    for s in in_period:
        key = status_key(s)
        if key in outcomes:
            outcomes[key] += 1
    timed = outcomes["completed"] + outcomes["ended_early"]
    return {
        "period": period,
        **stats_dict(tracker.stats(period, now)),
        "outcomes": outcomes,
        "completion_rate": round(outcomes["completed"] / timed, 3) if timed else None,
        "streak_days": tracker.streak(now),
    }
