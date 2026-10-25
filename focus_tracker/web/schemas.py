"""Request bodies for the API, validated by FastAPI/pydantic."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from focus_tracker.tracker import MAX_DISTRACTIONS, MAX_TEXT

MAX_MINUTES = 12 * 60
Name = Field(min_length=1, max_length=100)


class StartSession(BaseModel):
    activity: str = Name
    minutes: float = Field(gt=0, le=MAX_MINUTES)
    note: str = Field("", max_length=MAX_TEXT["note"])
    location: str = Field("", max_length=MAX_TEXT["location"])


class LogSession(BaseModel):
    """A past session the user forgot to time."""

    activity: str = Name
    minutes: float = Field(gt=0, le=MAX_MINUTES)
    ended_at: datetime | None = None  # local time; defaults to now
    note: str = Field("", max_length=MAX_TEXT["note"])
    location: str = Field("", max_length=MAX_TEXT["location"])


class SessionDetails(BaseModel):
    """Fields to update; anything left out is unchanged."""

    note: str | None = Field(None, max_length=MAX_TEXT["note"])
    location: str | None = Field(None, max_length=MAX_TEXT["location"])
    distractions: list[str] | None = Field(None, max_length=MAX_DISTRACTIONS)
    reflection: str | None = Field(None, max_length=MAX_TEXT["reflection"])


class ActivityName(BaseModel):
    name: str = Name
