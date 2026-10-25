"""Core data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Pause:
    start: datetime
    end: datetime | None = None  # None while the session is paused


@dataclass
class Session:
    id: int
    activity: str
    start: datetime
    end: datetime | None = None
    note: str = ""
    target: timedelta | None = None  # planned length for timed sessions
    pauses: list[Pause] = field(default_factory=list)
    # Optional details, recorded for later review and AI analysis.
    location: str = ""
    distractions: list[str] = field(default_factory=list)
    reflection: str = ""  # what went well / what was hard
    sample: bool = False  # example data preloaded in the public demo

    @property
    def active(self) -> bool:
        return self.end is None

    @property
    def paused(self) -> bool:
        return bool(self.pauses) and self.pauses[-1].end is None

    def duration(self, now: datetime | None = None) -> timedelta:
        """Time actually spent focusing: wall-clock time minus pauses."""
        return self.focused_within(None, now)

    def focused_within(self, since: datetime | None, now: datetime | None = None) -> timedelta:
        """Focused time from `since` (or the session start) until the end (or now)."""
        end = self.end or now or datetime.now()
        start = max(self.start, since) if since else self.start
        if end <= start:
            return timedelta()
        total = end - start
        for pause in self.pauses:
            overlap = min(pause.end or end, end) - max(pause.start, start)
            if overlap > timedelta():
                total -= overlap
        return total

    def remaining(self, now: datetime | None = None) -> timedelta | None:
        if self.target is None:
            return None
        return self.target - self.duration(now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "activity": self.activity,
            "start": _iso(self.start),
            "end": _iso(self.end),
            "note": self.note,
            "target_seconds": int(self.target.total_seconds()) if self.target else None,
            "pauses": [[_iso(p.start), _iso(p.end)] for p in self.pauses],
            "location": self.location,
            "distractions": list(self.distractions),
            "reflection": self.reflection,
            # Only written when set, so local data files are unchanged.
            **({"sample": True} if self.sample else {}),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        target = data.get("target_seconds")
        return cls(
            id=data["id"],
            activity=data["activity"],
            start=datetime.fromisoformat(data["start"]),
            end=_parse(data.get("end")),
            note=data.get("note", ""),
            target=timedelta(seconds=target) if target else None,
            pauses=[Pause(_parse(s), _parse(e)) for s, e in data.get("pauses", [])],
            # Sessions saved before these fields existed load with empty values.
            location=data.get("location") or "",
            distractions=[str(d) for d in data.get("distractions") or []],
            reflection=data.get("reflection") or "",
            sample=bool(data.get("sample", False)),
        )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
