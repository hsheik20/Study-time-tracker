"""JSON file persistence for sessions and activities."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from focus_tracker.models import Session

ENV_VAR = "FOCUS_TRACKER_DATA"


def default_path() -> Path:
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".focus_tracker" / "sessions.json"


class Storage:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()

    def load(self) -> tuple[list[Session], list[str]]:
        if not self.path.exists():
            return [], []
        try:
            with self.path.open(encoding="utf-8") as f:
                data = json.load(f)
            sessions = [Session.from_dict(item) for item in data.get("sessions", [])]
            activities = [str(name) for name in data.get("activities", [])]
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise ValueError(f"Could not read data file {self.path}: {e}") from e
        return sessions, activities

    def save(self, sessions: list[Session], activities: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "activities": activities,
            "sessions": [s.to_dict() for s in sessions],
        }
        # Write to a temp file then rename, so a crash never leaves a half-written file.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            os.unlink(tmp)
            raise
