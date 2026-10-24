"""Shared request dependencies."""

from __future__ import annotations

from datetime import datetime

from fastapi import Depends, Request

from focus_tracker.tracker import Tracker


def get_now() -> datetime:
    return datetime.now()


def get_tracker(request: Request, now: datetime = Depends(get_now)) -> Tracker:
    """A fresh Tracker per request, so changes made from the CLI show up
    immediately. Like the CLI, it first saves any timed session whose
    countdown has run out."""
    tracker = Tracker(request.app.state.storage_factory())
    tracker.complete_if_due(now)
    return tracker
