"""Generating, limiting and remembering weekly reports."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from focus_tracker.insights.metrics import Week, journal_entries, weekly_metrics
from focus_tracker.insights.report import (
    NOT_CONFIGURED,
    InsightsError,
    NotConfiguredError,
    ReportGenerator,
)
from focus_tracker.tracker import Tracker

KEEP_REPORTS = 12  # most recent weeks kept on disk


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except ValueError:
        return default


class RequestLimiter:
    """Server-side caps on Claude calls: a cool-down between reports, plus hourly
    and daily maximums. One report is generated at a time."""

    def __init__(self, cooldown: int | None = None, per_hour: int | None = None,
                 per_day: int | None = None, clock=time.monotonic):
        self.cooldown = _env_int("FOCUS_TRACKER_INSIGHTS_COOLDOWN", 20) if cooldown is None else cooldown
        self.per_hour = _env_int("FOCUS_TRACKER_INSIGHTS_PER_HOUR", 10) if per_hour is None else per_hour
        self.per_day = _env_int("FOCUS_TRACKER_INSIGHTS_PER_DAY", 30) if per_day is None else per_day
        self.clock = clock
        self._calls: deque[float] = deque()  # start times, for the hourly/daily caps
        self._last_finished: float | None = None  # the cool-down runs from here
        self._lock = threading.Lock()
        self._busy = False

    def _prune(self, now: float) -> None:
        while self._calls and now - self._calls[0] >= 86400:
            self._calls.popleft()

    def status(self) -> dict:
        with self._lock:
            now = self.clock()
            self._prune(now)
            last_hour = sum(1 for t in self._calls if now - t < 3600)
            wait = 0.0
            if self._last_finished is not None and now - self._last_finished < self.cooldown:
                wait = self.cooldown - (now - self._last_finished)
            if last_hour >= self.per_hour:
                wait = max(wait, 3600 - (now - next(t for t in self._calls if now - t < 3600)))
            if len(self._calls) >= self.per_day:
                wait = max(wait, 86400 - (now - self._calls[0]))
            return {
                "remaining_this_hour": max(0, self.per_hour - last_hour),
                "remaining_today": max(0, self.per_day - len(self._calls)),
                "retry_after_seconds": int(wait + 0.999) if wait > 0 else 0,
                "busy": self._busy,
            }

    def acquire(self) -> None:
        """Reserve a call or raise a 429 InsightsError explaining when to retry."""
        status = self.status()
        with self._lock:
            if self._busy:
                raise InsightsError("A report is already being generated.", 429, retry_after=5)
            if status["retry_after_seconds"]:
                wait = status["retry_after_seconds"]
                when = f"{wait} seconds" if wait < 120 else f"{round(wait / 60)} minutes"
                raise InsightsError(f"Report limit reached. You can generate another in {when}.",
                                    429, retry_after=wait)
            self._busy = True
            self._calls.append(self.clock())

    def release(self) -> None:
        with self._lock:
            self._busy = False
            self._last_finished = self.clock()


class ReportStore:
    """The latest report per week, saved next to the session data file."""

    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("reports", {})
        except (OSError, ValueError, AttributeError):
            return {}

    def get(self, week_key: str) -> dict | None:
        return self._read().get(week_key)

    def put(self, week_key: str, entry: dict) -> None:
        reports = self._read()
        reports[week_key] = entry
        kept = dict(sorted(reports.items())[-KEEP_REPORTS:])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"reports": kept}, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except BaseException:
            os.unlink(tmp)
            raise


class InsightsService:
    def __init__(self, generator: ReportGenerator, limiter: RequestLimiter | None = None):
        self.generator = generator
        self.limiter = limiter or RequestLimiter()

    @staticmethod
    def store_for(tracker: Tracker) -> ReportStore:
        data = tracker.storage.path
        return ReportStore(data.with_name("insights.json"))

    def overview(self, tracker: Tracker, week: Week, now: datetime) -> dict:
        """The numbers and any saved report for a week. Makes no API call."""
        return {
            "configured": self.generator.configured,
            "model": self.generator.model,
            "metrics": weekly_metrics(tracker, week, now),
            "report": self.store_for(tracker).get(week.key),
            "limits": self.limiter.status(),
        }

    def generate(self, tracker: Tracker, week: Week, now: datetime) -> dict:
        """Make a real Claude API call and save the resulting report."""
        if not self.generator.configured:
            raise NotConfiguredError(NOT_CONFIGURED)
        metrics = weekly_metrics(tracker, week, now)
        if not metrics["totals"]["sessions"]:
            raise InsightsError("There are no finished sessions this week yet. Complete a "
                                "session, then generate your insights.", 422)
        journal = journal_entries(tracker, week, now)
        self.limiter.acquire()
        try:
            report, usage = self.generator.generate(metrics, journal)
        finally:
            self.limiter.release()
        entry = {
            "generated_at": now.isoformat(timespec="seconds"),
            "model": self.generator.model,
            "usage": usage,
            "sessions_analysed": metrics["totals"]["sessions"],
            **report.model_dump(),
        }
        self.store_for(tracker).put(week.key, entry)
        return {**self.overview(tracker, week, now), "report": entry}
