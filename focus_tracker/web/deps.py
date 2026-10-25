"""Shared request dependencies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request

from focus_tracker.tracker import Tracker


def get_now(request: Request) -> datetime:
    """Local time. In the public demo the server runs in UTC, so it's the
    visitor's local time, from the time zone offset their browser sent."""
    offset = getattr(request.state, "demo_utc_offset", None)
    if offset is None:
        return datetime.now()
    return (datetime.now(timezone.utc) - timedelta(minutes=offset)).replace(tzinfo=None)


def get_tracker(request: Request, now: datetime = Depends(get_now)) -> Tracker:
    """A fresh Tracker per request, so changes made from the CLI show up
    immediately. Like the CLI, it first saves any timed session whose
    countdown has run out. In the demo it uses the visitor's data from the request."""
    storage = getattr(request.state, "demo_storage", None)
    tracker = Tracker(storage if storage is not None else request.app.state.storage_factory())
    tracker.complete_if_due(now)
    return tracker
