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
    and daily maximums. By default one report is generated at a time."""

    def __init__(self, cooldown: int | None = None, per_hour: int | None = None,
                 per_day: int | None = None, clock=time.monotonic, max_concurrent: int = 1,
                 limit_message: str = "Report limit reached."):
        self.cooldown = _env_int("FOCUS_TRACKER_INSIGHTS_COOLDOWN", 20) if cooldown is None else cooldown
        self.per_hour = _env_int("FOCUS_TRACKER_INSIGHTS_PER_HOUR", 10) if per_hour is None else per_hour
        self.per_day = _env_int("FOCUS_TRACKER_INSIGHTS_PER_DAY", 30) if per_day is None else per_day
        self.clock = clock
        self.max_concurrent = max_concurrent
        self.limit_message = limit_message
        self._calls: deque[float] = deque()  # start times, for the hourly/daily caps
        self._last_finished: float | None = None  # the cool-down runs from here
        self._lock = threading.Lock()
        self._in_flight = 0

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
                "busy": self._in_flight >= self.max_concurrent,
            }

    def acquire(self) -> None:
        """Reserve a call or raise a 429 InsightsError explaining when to retry."""
        status = self.status()
        with self._lock:
            if self._in_flight >= self.max_concurrent:
                raise InsightsError("A report is already being generated.", 429, retry_after=5)
            if status["retry_after_seconds"]:
                wait = status["retry_after_seconds"]
                when = f"{wait} seconds" if wait < 120 else f"{round(wait / 60)} minutes"
                raise InsightsError(f"{self.limit_message} You can generate another in {when}.",
                                    429, retry_after=wait)
            self._in_flight += 1
            self._calls.append(self.clock())

    def release(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._last_finished = self.clock()

    def cancel(self) -> None:
        """Undo an acquire() whose report never started (it doesn't count)."""
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            if self._calls:
                self._calls.pop()

    @property
    def idle(self) -> bool:
        """No calls in the last day and none running: safe to forget."""
        with self._lock:
            self._prune(self.clock())
            return not self._calls and not self._in_flight


class VisitorLimiter:
    """Per-visitor caps for the public demo, layered on top of the global limiter."""

    MAX_TRACKED = 5000

    def __init__(self, cooldown: int, per_hour: int, per_day: int, clock=time.monotonic):
        self._settings = dict(cooldown=cooldown, per_hour=per_hour, per_day=per_day, clock=clock,
                              limit_message="You've reached the demo's report limit.")
        self._visitors: dict[str, RequestLimiter] = {}
        self._lock = threading.Lock()

    def for_visitor(self, key: str) -> RequestLimiter:
        with self._lock:
            limiter = self._visitors.get(key)
            if limiter is None:
                if len(self._visitors) >= self.MAX_TRACKED:  # forget visitors with no recent calls
                    self._visitors = {k: v for k, v in self._visitors.items() if not v.idle}
                limiter = self._visitors[key] = RequestLimiter(**self._settings)
            return limiter


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
    def __init__(self, generator: ReportGenerator, limiter: RequestLimiter | None = None,
                 visitor_limiter: VisitorLimiter | None = None):
        self.generator = generator
        self.limiter = limiter or RequestLimiter()
        self.visitor_limiter = visitor_limiter  # the public demo also limits each visitor

    @staticmethod
    def store_for(tracker: Tracker) -> ReportStore:
        # The demo keeps reports in the visitor's browser, passed in with each request.
        in_memory = getattr(tracker.storage, "report_store", None)
        if in_memory is not None:
            return in_memory
        data = tracker.storage.path
        return ReportStore(data.with_name("insights.json"))

    def _limiters(self, visitor: str | None) -> list[RequestLimiter]:
        own = [self.visitor_limiter.for_visitor(visitor or "unknown")] if self.visitor_limiter else []
        return own + [self.limiter]

    def limits(self, visitor: str | None = None) -> dict:
        """What the most restrictive limiter allows right now."""
        statuses = [limiter.status() for limiter in self._limiters(visitor)]
        return {
            "remaining_this_hour": min(s["remaining_this_hour"] for s in statuses),
            "remaining_today": min(s["remaining_today"] for s in statuses),
            "retry_after_seconds": max(s["retry_after_seconds"] for s in statuses),
            "busy": any(s["busy"] for s in statuses),
        }

    def overview(self, tracker: Tracker, week: Week, now: datetime,
                 visitor: str | None = None) -> dict:
        """The numbers and any saved report for a week. Makes no API call."""
        return {
            "configured": self.generator.configured,
            "model": self.generator.model,
            "metrics": weekly_metrics(tracker, week, now),
            "report": self.store_for(tracker).get(week.key),
            "limits": self.limits(visitor),
        }

    def generate(self, tracker: Tracker, week: Week, now: datetime,
                 visitor: str | None = None) -> dict:
        """Make a real Claude API call and save the resulting report."""
        if not self.generator.configured:
            raise NotConfiguredError(NOT_CONFIGURED)
        metrics = weekly_metrics(tracker, week, now)
        if not metrics["totals"]["sessions"]:
            raise InsightsError("There are no finished sessions this week yet. Complete a "
                                "session, then generate your insights.", 422)
        journal = journal_entries(tracker, week, now)
        acquired: list[RequestLimiter] = []
        try:
            for limiter in self._limiters(visitor):  # the visitor's own limit first, then the global one
                limiter.acquire()
                acquired.append(limiter)
        except InsightsError:
            for limiter in acquired:
                limiter.cancel()
            raise
        try:
            report, usage = self.generator.generate(metrics, journal)
        finally:
            for limiter in acquired:
                limiter.release()
        entry = {
            "generated_at": now.isoformat(timespec="seconds"),
            "model": self.generator.model,
            "usage": usage,
            "sessions_analysed": metrics["totals"]["sessions"],
            **report.model_dump(),
        }
        self.store_for(tracker).put(week.key, entry)
        return {**self.overview(tracker, week, now, visitor), "report": entry}
