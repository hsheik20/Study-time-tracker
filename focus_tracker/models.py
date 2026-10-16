"""Core data types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Session:
    id: int
    activity: str
    start: datetime
    end: datetime | None = None
    note: str = ""

    @property
    def active(self) -> bool:
        return self.end is None

    def duration(self, now: datetime | None = None) -> timedelta:
        end = self.end or now or datetime.now()
        return end - self.start

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "activity": self.activity,
            "start": self.start.isoformat(timespec="seconds"),
            "end": self.end.isoformat(timespec="seconds") if self.end else None,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        return cls(
            id=data["id"],
            activity=data["activity"],
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]) if data.get("end") else None,
            note=data.get("note", ""),
        )
