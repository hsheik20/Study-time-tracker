"""Business logic: sessions, activities, summaries and statistics."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator

from focus_tracker.models import Pause, Session
from focus_tracker.storage import Storage


class TrackerError(Exception):
    """A user-facing error (e.g. starting a session while one is running)."""


PERIODS = ("today", "week", "month", "all")


@dataclass
class Stats:
    totals: dict[str, timedelta]  # per activity, largest first
    count: int
    longest: timedelta

    @property
    def total(self) -> timedelta:
        return sum(self.totals.values(), timedelta())

    @property
    def average(self) -> timedelta:
        return self.total / self.count if self.count else timedelta()


@dataclass
class ActivityInfo:
    name: str
    sessions: int
    total: timedelta


class Tracker:
    def __init__(self, storage: Storage):
        self.storage = storage
        self.sessions, saved_activities = storage.load()
        self._activities: list[str] = []
        # Activities used by older data files only exist on sessions; pick them up too.
        for name in saved_activities + [s.activity for s in self.sessions]:
            if self.find_activity(name) is None:
                self._activities.append(name)

    def _save(self) -> None:
        self.storage.save(self.sessions, self._activities)

    def _next_id(self) -> int:
        return max((s.id for s in self.sessions), default=0) + 1

    # --- Activities -------------------------------------------------------

    def activities(self) -> list[str]:
        return sorted(self._activities, key=str.lower)

    def find_activity(self, name: str) -> str | None:
        """Return the stored spelling of an activity, matching case-insensitively."""
        key = name.strip().lower()
        return next((a for a in self._activities if a.lower() == key), None)

    def _register(self, name: str) -> str:
        name = name.strip()
        if not name:
            raise TrackerError("Activity name cannot be empty.")
        existing = self.find_activity(name)
        if existing:
            return existing
        self._activities.append(name)
        return name

    def _require_activity(self, name: str) -> str:
        existing = self.find_activity(name)
        if existing is None:
            raise TrackerError(f"No activity named '{name}'.")
        return existing

    def _sessions_for(self, activity: str) -> list[Session]:
        return [s for s in self.sessions if s.activity.lower() == activity.lower()]

    def add_activity(self, name: str) -> str:
        if self.find_activity(name):
            raise TrackerError(f"Activity '{self.find_activity(name)}' already exists.")
        name = self._register(name)
        self._save()
        return name

    def rename_activity(self, old: str, new: str) -> str:
        old = self._require_activity(old)
        new = new.strip()
        if not new:
            raise TrackerError("Activity name cannot be empty.")
        clash = self.find_activity(new)
        if clash and clash != old:
            raise TrackerError(f"Activity '{clash}' already exists.")
        self._activities[self._activities.index(old)] = new
        for s in self._sessions_for(old):
            s.activity = new
        self._save()
        return new

    def delete_activity(self, name: str) -> list[Session]:
        """Delete an activity and all of its sessions; returns the removed sessions."""
        name = self._require_activity(name)
        current = self.active_session()
        if current and current.activity.lower() == name.lower():
            raise TrackerError(f"'{name}' has a session running. Stop it first.")
        removed = self._sessions_for(name)
        self.sessions = [s for s in self.sessions if s not in removed]
        self._activities.remove(name)
        self._save()
        return removed

    def activity_overview(self) -> list[ActivityInfo]:
        return [
            ActivityInfo(
                name,
                len(sessions := self._sessions_for(name)),
                sum((s.duration() for s in sessions), timedelta()),
            )
            for name in self.activities()
        ]

    # --- Sessions ---------------------------------------------------------

    def active_session(self) -> Session | None:
        return next((s for s in self.sessions if s.active), None)

    def find_session(self, session_id: int) -> Session:
        for s in self.sessions:
            if s.id == session_id:
                return s
        raise TrackerError(f"No session with id {session_id}.")

    def _require_active(self) -> Session:
        current = self.active_session()
        if not current:
            raise TrackerError("No session is currently running.")
        return current

    def start(
        self,
        activity: str,
        note: str = "",
        now: datetime | None = None,
        target: timedelta | None = None,
    ) -> Session:
        """Start a session; with a target it becomes a countdown of that length."""
        current = self.active_session()
        if current:
            raise TrackerError(
                f"Already tracking '{current.activity}'. Stop that session first."
            )
        if target is not None and target <= timedelta(0):
            raise TrackerError("Focus duration must be positive.")
        activity = self._register(activity)
        session = Session(self._next_id(), activity, now or datetime.now(), note=note,
                          target=target)
        self.sessions.append(session)
        self._save()
        return session

    def pause(self, now: datetime | None = None) -> Session:
        current = self._require_active()
        if current.paused:
            raise TrackerError("The session is already paused.")
        current.pauses.append(Pause(now or datetime.now()))
        self._save()
        return current

    def resume(self, now: datetime | None = None) -> Session:
        current = self._require_active()
        if not current.paused:
            raise TrackerError("The session isn't paused.")
        current.pauses[-1].end = now or datetime.now()
        self._save()
        return current

    def stop(self, now: datetime | None = None) -> Session:
        """End the running session, recording the time actually focused so far."""
        current = self._require_active()
        now = now or datetime.now()
        if current.paused:
            current.pauses[-1].end = now
        current.end = now
        self._save()
        return current

    def complete_if_due(self, now: datetime | None = None) -> Session | None:
        """Save a timed session whose countdown has run out.

        The end time is set to the moment the countdown hit zero, so the recorded
        duration equals the target even if this is called late (e.g. after the
        app was closed mid-session).
        """
        current = self.active_session()
        if not current or current.target is None or current.paused:
            return None
        now = now or datetime.now()
        remaining = current.remaining(now)
        if remaining > timedelta():
            return None
        current.end = now + remaining
        self._save()
        return current

    def last_target(self) -> timedelta | None:
        """The planned length of the most recent timed session, if any."""
        timed = [s for s in self.sessions if s.target]
        return max(timed, key=lambda s: s.start).target if timed else None

    def cancel(self) -> Session:
        current = self._require_active()
        self.sessions.remove(current)
        self._save()
        return current

    def add(
        self,
        activity: str,
        duration: timedelta,
        end: datetime | None = None,
        note: str = "",
    ) -> Session:
        if duration <= timedelta(0):
            raise TrackerError("Duration must be positive.")
        activity = self._register(activity)
        end = end or datetime.now()
        session = Session(self._next_id(), activity, end - duration, end, note)
        self.sessions.append(session)
        self._save()
        return session

    def delete(self, session_id: int) -> Session:
        session = self.find_session(session_id)
        self.sessions.remove(session)
        self._save()
        return session

    def history(self, activity: str | None = None, limit: int | None = None) -> list[Session]:
        result = self._sessions_for(activity) if activity else list(self.sessions)
        result.sort(key=lambda s: s.start, reverse=True)
        return result[:limit] if limit else result

    # --- Reporting --------------------------------------------------------

    def _clipped(self, period: str, now: datetime) -> Iterator[tuple[Session, timedelta]]:
        """Yield each session with the focused time that falls inside the period."""
        since = period_start(period, now)
        for s in self.sessions:
            focused = s.focused_within(since, now)
            if focused > timedelta():
                yield s, focused

    def summary(self, period: str = "all", now: datetime | None = None) -> dict[str, timedelta]:
        """Total focus time per activity within the period, largest first.

        Sessions overlapping the period boundary only count the overlapping part.
        """
        return self.stats(period, now).totals

    def stats(self, period: str = "all", now: datetime | None = None) -> Stats:
        now = now or datetime.now()
        totals: dict[str, timedelta] = defaultdict(timedelta)
        count, longest = 0, timedelta()
        for s, duration in self._clipped(period, now):
            totals[s.activity] += duration
            count += 1
            longest = max(longest, duration)
        ordered = dict(sorted(totals.items(), key=lambda kv: kv[1], reverse=True))
        return Stats(ordered, count, longest)

    def daily_totals(self, days: int = 7, now: datetime | None = None) -> list[tuple[datetime, timedelta]]:
        """Focused time on each of the last `days` days (oldest first), as
        (midnight, total) pairs. Sessions spanning midnight are split."""
        now = now or datetime.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        result = []
        for back in range(days - 1, -1, -1):
            start = midnight - timedelta(days=back)
            end = start + timedelta(days=1)
            # Focus from `start` onwards, minus focus from `end` onwards.
            total = sum((s.focused_within(start, now) - s.focused_within(end, now)
                         for s in self.sessions), timedelta())
            result.append((start, total))
        return result

    def streak(self, now: datetime | None = None) -> int:
        """Consecutive days with at least one session, ending today (or yesterday)."""
        days = {s.start.date() for s in self.sessions}
        day = (now or datetime.now()).date()
        if day not in days:
            day -= timedelta(days=1)
        count = 0
        while day in days:
            count += 1
            day -= timedelta(days=1)
        return count


def period_start(period: str, now: datetime) -> datetime | None:
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        return midnight
    if period == "week":
        return midnight - timedelta(days=now.weekday())  # Monday
    if period == "month":
        return midnight.replace(day=1)
    if period == "all":
        return None
    raise TrackerError(f"Unknown period '{period}'. Choose from: {', '.join(PERIODS)}.")
