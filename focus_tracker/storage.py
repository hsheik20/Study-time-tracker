"""JSON file persistence for sessions and activities."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

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
        self._lock_depth = 0
        self._lock_file = None

    def signature(self) -> tuple[int, int] | None:
        """Changes whenever the file is rewritten, so readers can cheaply tell
        whether another process (the CLI or the website) saved something."""
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return stat.st_mtime_ns, stat.st_size

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Hold an exclusive lock across a read-modify-write, so the CLI and the
        website can't overwrite each other's changes. Re-entrant per instance."""
        if self._lock_depth:
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(self.path.name + ".lock")
        with open(lock_path, "a+") as handle:
            _acquire(handle)
            self._lock_depth = 1
            try:
                yield
            finally:
                self._lock_depth = 0
                _release(handle)

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


def _acquire(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(handle, fcntl.LOCK_EX)


def _release(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle, fcntl.LOCK_UN)
