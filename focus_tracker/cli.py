"""Command-line interface for Focus Tracker."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from focus_tracker import __version__
from focus_tracker.formatting import (
    TIME_FMT,
    format_duration,
    parse_duration,
    session_table,
    summary_lines,
)
from focus_tracker.menu import Menu
from focus_tracker.storage import Storage
from focus_tracker.tracker import PERIODS, Tracker, TrackerError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="focus",
        description="Track how much time you spend focusing on different activities. "
        "Run with no arguments for the interactive menu.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start", help="start a focus session")
    p.add_argument("activity", help="what you're focusing on, e.g. studying")
    p.add_argument("-n", "--note", default="", help="optional note")

    sub.add_parser("stop", help="stop the current session")
    sub.add_parser("cancel", help="discard the current session without saving it")
    sub.add_parser("status", help="show the current session")

    p = sub.add_parser("add", help="log a past session manually")
    p.add_argument("activity")
    p.add_argument("duration", help="e.g. 90, 45m, 2h, 1h30m")
    p.add_argument(
        "--ended",
        help="when the session ended, as 'YYYY-MM-DD HH:MM' (default: now)",
    )
    p.add_argument("-n", "--note", default="")

    p = sub.add_parser("log", help="list past sessions")
    p.add_argument("-a", "--activity", help="only show this activity")
    p.add_argument("-l", "--limit", type=int, default=10, help="max rows (0 = all)")

    p = sub.add_parser("summary", help="total time per activity")
    p.add_argument("period", nargs="?", default="week", choices=PERIODS)

    p = sub.add_parser("delete", help="delete a session by id")
    p.add_argument("id", type=int)

    return parser


def main(argv: list[str] | None = None, storage: Storage | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv) if argv else None
    try:
        tracker = Tracker(storage or Storage())
        if args is None:
            return Menu(tracker).run()
        return COMMANDS[args.command](tracker, args)
    except (TrackerError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_start(tracker: Tracker, args) -> int:
    s = tracker.start(args.activity, args.note)
    print(f"Started '{s.activity}' at {s.start:%H:%M}. Run 'focus stop' when you're done.")
    return 0


def cmd_stop(tracker: Tracker, args) -> int:
    s = tracker.stop()
    print(f"Stopped '{s.activity}' after {format_duration(s.duration())}.")
    return 0


def cmd_cancel(tracker: Tracker, args) -> int:
    s = tracker.cancel()
    print(f"Discarded '{s.activity}' session.")
    return 0


def cmd_status(tracker: Tracker, args) -> int:
    s = tracker.active_session()
    if not s:
        print("Not tracking anything. Start with: focus start <activity>")
    else:
        print(
            f"Focusing on '{s.activity}' since {s.start:%H:%M} "
            f"({format_duration(s.duration())} so far)."
        )
    return 0


def cmd_add(tracker: Tracker, args) -> int:
    ended = datetime.strptime(args.ended, TIME_FMT) if args.ended else None
    s = tracker.add(args.activity, parse_duration(args.duration), ended, args.note)
    print(f"Logged {format_duration(s.duration())} of '{s.activity}' (id {s.id}).")
    return 0


def cmd_log(tracker: Tracker, args) -> int:
    sessions = tracker.history(args.activity, args.limit or None)
    if not sessions:
        print("No sessions recorded yet.")
        return 0
    print("\n".join(session_table(sessions)))
    return 0


def cmd_summary(tracker: Tracker, args) -> int:
    totals = tracker.summary(args.period)
    label = {"today": "Today", "week": "This week", "month": "This month", "all": "All time"}
    print(f"{label[args.period]}:")
    if not totals:
        print("  No focus time recorded.")
        return 0
    for line in summary_lines(totals):
        print(f"  {line}")
    return 0


def cmd_delete(tracker: Tracker, args) -> int:
    s = tracker.delete(args.id)
    print(f"Deleted session {s.id} ('{s.activity}').")
    return 0


COMMANDS = {
    "start": cmd_start,
    "stop": cmd_stop,
    "cancel": cmd_cancel,
    "status": cmd_status,
    "add": cmd_add,
    "log": cmd_log,
    "summary": cmd_summary,
    "delete": cmd_delete,
}
