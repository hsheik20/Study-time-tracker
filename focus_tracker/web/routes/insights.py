"""Claude-powered weekly insights."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from focus_tracker.insights.metrics import Week
from focus_tracker.insights.report import InsightsError
from focus_tracker.insights.service import InsightsService
from focus_tracker.tracker import Tracker
from focus_tracker.web.deps import get_now, get_tracker

router = APIRouter(tags=["insights"])
WeekChoice = Literal["current", "previous"]


class GenerateRequest(BaseModel):
    week: WeekChoice = "current"


def _service(request: Request) -> InsightsService:
    return request.app.state.insights


def _week(choice: WeekChoice, now: datetime) -> Week:
    return Week.containing(now, weeks_back=0 if choice == "current" else 1)


@router.get("/insights")
def insights(week: WeekChoice = "current", tracker: Tracker = Depends(get_tracker),
             now: datetime = Depends(get_now), service: InsightsService = Depends(_service)) -> dict:
    """This week's numbers and the last saved report. Never calls Claude."""
    return service.overview(tracker, _week(week, now), now)


@router.post("/insights")
def generate_insights(body: GenerateRequest, tracker: Tracker = Depends(get_tracker),
                      now: datetime = Depends(get_now),
                      service: InsightsService = Depends(_service)):
    """Generate a fresh report with a real Claude API call (rate limited)."""
    try:
        return service.generate(tracker, _week(body.week, now), now)
    except InsightsError as error:
        headers = {"Retry-After": str(error.retry_after)} if error.retry_after else None
        return JSONResponse({"detail": str(error), "retry_after": error.retry_after},
                            status_code=error.status, headers=headers)
