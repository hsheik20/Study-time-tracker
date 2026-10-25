"""Interactive, menu-driven interface (shown when `focus` runs with no arguments)."""

from __future__ import annotations

import os
import random
import shutil
import sys
from datetime import datetime, timedelta
from typing import Callable

from focus_tracker.formatting import (
    TIME_FMT,
    format_duration,
    parse_duration,
    summary_lines,
)
from focus_tracker.display import FRAME_WIDTH, Line, celebration, paint
from focus_tracker.history_view import history_screen
from focus_tracker.sound import play_chime
from focus_tracker.timer import FocusTimer, LineKeys, TimerResult, terminal_keys
from focus_tracker.tracker import Tracker, TrackerError

BANNER = "========== FOCUS TRACKER =========="
DEFAULT_FOCUS = timedelta(minutes=25)
MAX_FOCUS = timedelta(hours=12)
ENCOURAGEMENTS = [
    "Great work. Keep it going!",
    "Well done. Keep the momentum going!",
    "Another session in the books. Keep it up!",
    "You showed up and did the work. Be proud of that!",
    "Nice focus! Every session adds up.",
]
PERIOD_LABELS = {"today": "Today", "week": "This Week", "month": "This Month", "all": "All Time"}

Action = Callable[[], None]


class Menu:
    def __init__(
        self,
        tracker: Tracker,
        input_fn: Callable[[str], str] | None = None,
        print_fn: Callable[..., None] | None = None,
        live_timer: bool | None = None,
        clock: Callable[[], datetime] = datetime.now,
        chime: Callable[[], None] = play_chime,
    ):
        """`live_timer` enables the single-keypress countdown; by default it's on
        when using the real terminal, and off when input is scripted or piped."""
        self.tracker = tracker
        self.input = input_fn or input
        self.print = print_fn or print
        if live_timer is None:
            live_timer = input_fn is None and sys.stdin.isatty() and sys.stdout.isatty()
        self.live_timer = live_timer
        self.color = live_timer and "NO_COLOR" not in os.environ
        self.clock = clock
        self.chime = chime

    def run(self) -> int:
        actions: list[tuple[str, Action | None]] = [
            ("Start Focus Session", self.start_session),
            ("View Session History", self.history_menu),
            ("View Statistics", self.statistics_menu),
            ("Manage Activities", self.activities_menu),
            ("Exit", None),
        ]
        try:
            self.report_if_completed_while_away()
            while True:
                self.print(f"\n{BANNER}\n")
                action = actions[self.choose([label for label, _ in actions])][1]
                if action is None:
                    break
                self.run_action(action)
        except (KeyboardInterrupt, EOFError):
            self.print()
        current = self.tracker.active_session()
        if current:
            self.print(f"Your '{current.activity}' session is still running. "
                       "Choose 'Start Focus Session' next time to stop it.")
        self.print("Goodbye!")
        return 0

    # --- Input helpers ----------------------------------------------------

    def run_action(self, action: Action) -> None:
        try:
            action()
        except TrackerError as e:
            self.print(f"\n{e}")

    def choose(self, options: list[str]) -> int:
        """Show numbered options and return the 0-based index the user picks."""
        for i, label in enumerate(options, 1):
            self.print(f"{i}. {label}")
        self.print()
        while True:
            raw = self.input("Select an option: ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return int(raw) - 1
            shown = f"'{raw}' is not a valid option. " if raw else ""
            self.print(f"{shown}Please enter a number from 1 to {len(options)}.")

    def submenu(self, title: str, items: list[tuple[str, Action]]) -> None:
        labels = [label for label, _ in items] + ["Back to Main Menu"]
        while True:
            self.print(f"\n--- {title} ---\n")
            choice = self.choose(labels)
            if choice == len(items):
                return
            self.run_action(items[choice][1])

    def confirm(self, question: str) -> bool:
        while True:
            answer = self.input(f"{question} (y/n): ").strip().lower()
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            self.print("Please answer y or n.")

    def pause(self) -> None:
        self.input("\nPress Enter to continue...")

    def ask_text(self, prompt: str) -> str | None:
        """Ask for free text; an empty answer means 'go back' and returns None."""
        return self.input(f"{prompt} (press Enter to go back): ").strip() or None

    def ask_duration(self) -> timedelta | None:
        while True:
            raw = self.ask_text("Duration, e.g. 45m, 2h, 1h30m")
            if raw is None:
                return None
            try:
                return parse_duration(raw)
            except ValueError as e:
                self.print(e)

    def ask_focus_length(self) -> timedelta:
        default = self.tracker.last_target() or DEFAULT_FOCUS
        while True:
            raw = self.input(
                f"Focus duration in minutes (press Enter for {format_duration(default)}): "
            ).strip()
            if not raw:
                return default
            try:
                length = parse_duration(raw)
            except ValueError:
                self.print(f"'{raw}' isn't a valid duration. Enter minutes like 25, or 1h30m.")
                continue
            if not timedelta() < length <= MAX_FOCUS:
                self.print(f"Please choose between 1 minute and {format_duration(MAX_FOCUS)}.")
                continue
            return length

    def ask_end_time(self) -> datetime | None:
        while True:
            raw = self.input("When did it end? YYYY-MM-DD HH:MM (press Enter for now): ").strip()
            if not raw:
                return datetime.now()
            try:
                return datetime.strptime(raw, TIME_FMT)
            except ValueError:
                self.print(f"'{raw}' isn't a valid time. Example: 2026-10-14 18:30")

    def ask_session_id(self) -> int | None:
        while True:
            raw = self.ask_text("Session ID")
            if raw is None:
                return None
            if raw.isdigit():
                return int(raw)
            self.print("Please enter the numeric ID shown in the history table.")

    def pick_activity(self, prompt: str, allow_new: bool = False) -> str | None:
        activities = self.tracker.activities()
        if not activities:
            if not allow_new:
                self.print("\nNo activities yet. Add one first.")
                return None
            return self.ask_text("\nWhat are you focusing on? Activity name")
        self.print(f"\n{prompt}\n")
        extra = ["New activity..."] if allow_new else []
        choice = self.choose(activities + extra + ["Back"])
        if choice < len(activities):
            return activities[choice]
        if extra and choice == len(activities):
            return self.ask_text("Activity name")
        return None

    # --- 1. Focus sessions ------------------------------------------------

    def start_session(self) -> None:
        if self.report_if_completed_while_away():
            return
        current = self.tracker.active_session()
        if current:
            state = "paused" if current.paused else "running"
            self.print(
                f"\nYour '{current.activity}' session from {current.start:%a %H:%M} is "
                f"{state} ({format_duration(current.duration())} focused so far).\n"
            )
            choice = self.choose(
                ["Continue this session", "End and save it", "Discard it", "Back to Main Menu"]
            )
            if choice == 0:
                self.run_timer()
            elif choice == 1:
                self.report_saved(self.tracker.stop())
            elif choice == 2 and self.confirm("Discard this session?"):
                self.tracker.cancel()
                self.print("Session discarded.")
            return

        activity = self.pick_activity("What are you focusing on?", allow_new=True)
        if activity is None:
            return
        length = self.ask_focus_length()
        note = self.input("Note (optional, press Enter to skip): ").strip()
        self.tracker.start(activity, note, now=self.clock(), target=length)
        self.run_timer()

    def run_timer(self) -> None:
        session = self.tracker.active_session()
        length = f"{format_duration(session.target)} " if session.target else ""
        self.print(f"\nStarting a {length}focus session on '{session.activity}'. Good luck!")
        if self.live_timer:
            def write(text: str) -> None:
                sys.stdout.write(text)
                sys.stdout.flush()
            keys = terminal_keys()
        else:
            def write(text: str) -> None:
                self.print(text, end="")
            keys = LineKeys(self.input)
        with keys:
            result = FocusTimer(self.tracker, keys, write, self.live_timer, self.clock,
                                color=self.color).run()
        self.report_result(result)

    def report_result(self, result: TimerResult) -> None:
        if result.elsewhere:
            self.print({"completed": "This session finished while open on the website.",
                        "ended": "This session was ended from the website.",
                        "cancelled": "This session was cancelled from the website."}[result.outcome])
        if result.outcome == "cancelled":
            self.print("Session discarded.")
            return
        if result.outcome == "completed":
            # Only a session that ran its full length earns the chime.
            self.chime()
            self.celebrate(result.session)
            return
        if result.session.target:
            self.print("Session ended early.")
        self.report_saved(result.session)

    def celebrate(self, session) -> None:
        stats = self.tracker.stats("today", now=self.clock())
        count = f"{stats.count} session{'s' if stats.count != 1 else ''}"
        today = f"Today: {format_duration(stats.total)} of focus across {count}."
        width = min(FRAME_WIDTH, shutil.get_terminal_size().columns - 1)
        lines = celebration(session.activity, format_duration(session.duration()),
                            random.choice(ENCOURAGEMENTS), today, width)
        self.show_lines(lines)

    def report_if_completed_while_away(self) -> bool:
        """Save a timed session whose countdown ran out while the app was closed."""
        session = self.tracker.complete_if_due(self.clock())
        if session:
            self.print(f"\nYour {format_duration(session.target)} '{session.activity}' "
                       "session finished while you were away and has been saved.")
        return session is not None

    def report_saved(self, session) -> None:
        today = self.tracker.summary("today", now=self.clock()).get(session.activity)
        self.print(f"\nSaved {format_duration(session.duration())} of '{session.activity}'.")
        if today:
            self.print(f"Today's total for '{session.activity}': {format_duration(today)}.")

    # --- 2. History -------------------------------------------------------

    def history_menu(self) -> None:
        self.submenu("Session History", [
            ("Recent Sessions", lambda: self.show_sessions(
                self.tracker.history(limit=10), "Recent sessions", len(self.tracker.sessions))),
            ("All Sessions", lambda: self.show_sessions(self.tracker.history(), "All sessions")),
            ("Sessions for an Activity", self.show_activity_sessions),
            ("Delete a Session", self.delete_session),
        ])

    def show_lines(self, lines: list[Line]) -> None:
        for style, text in lines:
            self.print(paint(style, text) if self.color else text)

    def show_history(self, sessions, title: str, total: int | None = None) -> None:
        """`total` is how many sessions exist when only the latest few are shown."""
        width = shutil.get_terminal_size().columns - 1
        self.print()
        self.show_lines(history_screen(sessions, title, self.clock(), width, total))

    def show_sessions(self, sessions, title: str, total: int | None = None) -> None:
        self.show_history(sessions, title, total)
        self.pause()

    def show_activity_sessions(self) -> None:
        activity = self.pick_activity("Which activity?")
        if activity:
            self.show_sessions(self.tracker.history(activity), activity)

    def delete_session(self) -> None:
        recent = self.tracker.history(limit=10)
        if not recent:
            self.print("\nNo sessions to delete.")
            return
        self.show_history(recent, "Choose a session to delete", len(self.tracker.sessions))
        self.print()
        session_id = self.ask_session_id()
        if session_id is None:
            return
        s = self.tracker.find_session(session_id)
        if s.active:
            raise TrackerError("That session is still running. Stop or discard it first.")
        question = (f"Delete session {s.id} ({s.activity}, {format_duration(s.duration())}, "
                    f"{s.start:{TIME_FMT}})?")
        if self.confirm(question):
            self.tracker.delete(s.id)
            self.print("Session deleted.")

    # --- 3. Statistics ----------------------------------------------------

    def statistics_menu(self) -> None:
        self.submenu("Statistics", [
            (label, lambda period=period: self.show_stats(period))
            for period, label in PERIOD_LABELS.items()
        ])

    def show_stats(self, period: str) -> None:
        stats = self.tracker.stats(period)
        self.print(f"\n{PERIOD_LABELS[period]}\n")
        if not stats.count:
            self.print("No focus time recorded.")
        else:
            for line in summary_lines(stats.totals):
                self.print(f"  {line}")
            self.print()
            self.print(f"  Sessions:         {stats.count}")
            self.print(f"  Average session:  {format_duration(stats.average)}")
            self.print(f"  Longest session:  {format_duration(stats.longest)}")
        streak = self.tracker.streak()
        self.print(f"  Current streak:   {streak} day{'s' if streak != 1 else ''}")
        self.pause()

    # --- 4. Activities ----------------------------------------------------

    def activities_menu(self) -> None:
        self.submenu("Manage Activities", [
            ("View Activities", self.show_activities),
            ("Add Activity", self.add_activity),
            ("Rename Activity", self.rename_activity),
            ("Delete Activity", self.delete_activity),
            ("Log a Past Session", self.log_past_session),
        ])

    def show_activities(self) -> None:
        overview = self.tracker.activity_overview()
        self.print()
        if not overview:
            self.print("No activities yet.")
        else:
            width = max([len("Activity"), *(len(a.name) for a in overview)])
            self.print(f"{'Activity':<{width}}  {'Sessions':>8}  {'Total':>8}")
            for a in overview:
                self.print(f"{a.name:<{width}}  {a.sessions:>8}  {format_duration(a.total):>8}")
        self.pause()

    def add_activity(self) -> None:
        name = self.ask_text("\nNew activity name")
        if name:
            self.print(f"Added '{self.tracker.add_activity(name)}'.")

    def rename_activity(self) -> None:
        old = self.pick_activity("Which activity do you want to rename?")
        if not old:
            return
        new = self.ask_text(f"New name for '{old}'")
        if new:
            self.print(f"Renamed '{old}' to '{self.tracker.rename_activity(old, new)}'.")

    def delete_activity(self) -> None:
        name = self.pick_activity("Which activity do you want to delete?")
        if not name:
            return
        sessions = self.tracker.history(name)
        question = f"Delete '{name}'?"
        if sessions:
            question = f"Delete '{name}' and its {len(sessions)} session(s)? This can't be undone."
        if self.confirm(question):
            self.tracker.delete_activity(name)
            self.print(f"Deleted '{name}'.")

    def log_past_session(self) -> None:
        activity = self.pick_activity("Which activity was it?", allow_new=True)
        if not activity:
            return
        duration = self.ask_duration()
        if duration is None:
            return
        end = self.ask_end_time()
        note = self.input("Note (optional, press Enter to skip): ").strip()
        s = self.tracker.add(activity, duration, end, note)
        self.print(f"Logged {format_duration(s.duration())} of '{s.activity}'.")
