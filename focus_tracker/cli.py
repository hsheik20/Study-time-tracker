"""Command-line interface for Focus Tracker."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime

from focus_tracker import __version__
from focus_tracker.formatting import (
    TIME_FMT,
    format_clock,
    format_duration,
    parse_duration,
    summary_lines,
)
from focus_tracker.history_view import history_screen
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
    p.add_argument("-m", "--minutes", help="session length (e.g. 25 or 1h30m); "
                   "the session saves itself when time is up. Omit for an open-ended session")
    p.add_argument("-n", "--note", default="", help="optional note")

    sub.add_parser("pause", help="pause the current session")
    sub.add_parser("resume", help="resume a paused session")
    sub.add_parser("stop", help="stop the current session, saving the time focused")
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

    p = sub.add_parser("web", help="open the Focus Tracker website in your browser")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")

    return parser


def main(argv: list[str] | None = None, storage: Storage | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv) if argv else None
    if args and args.command == "web":
        from focus_tracker.web.server import serve  # only needs FastAPI when used

        return serve(port=args.port, open_browser=not args.no_browser)
    try:
        tracker = Tracker(storage or Storage())
        if args is None:
            return Menu(tracker).run()
        done = tracker.complete_if_due()
        if done:
            print(f"Your {format_duration(done.target)} '{done.activity}' session "
                  "finished and has been saved.")
        return COMMANDS[args.command](tracker, args)
    except (TrackerError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_start(tracker: Tracker, args) -> int:
    target = parse_duration(args.minutes) if args.minutes else None
    s = tracker.start(args.activity, args.note, target=target)
    length = f" for {format_duration(target)}" if target else ""
    print(f"Started '{s.activity}'{length} at {s.start:%H:%M}. "
          "Run 'focus stop' to end early, or 'focus' for the live timer.")
    return 0


def cmd_pause(tracker: Tracker, args) -> int:
    s = tracker.pause()
    print(f"Paused '{s.activity}' at {format_duration(s.duration())}. Run 'focus resume' to continue.")
    return 0


def cmd_resume(tracker: Tracker, args) -> int:
    s = tracker.resume()
    print(f"Resumed '{s.activity}'.")
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
        return 0
    state = "Paused on" if s.paused else "Focusing on"
    line = f"{state} '{s.activity}' since {s.start:%H:%M}: {format_duration(s.duration())} focused"
    if s.target:
        line += f", {format_clock(s.remaining(), round_up=True)} remaining"
    print(line + ".")
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
    title = args.activity or ("All sessions" if not args.limit else "Recent sessions")
    width = shutil.get_terminal_size().columns - 1
    total = len(tracker.history(args.activity))
    lines = history_screen(sessions, title, datetime.now(), width, total)
    print("\n".join(text for _, text in lines))
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
    "pause": cmd_pause,
    "resume": cmd_resume,
    "stop": cmd_stop,
    "cancel": cmd_cancel,
    "status": cmd_status,
    "add": cmd_add,
    "log": cmd_log,
    "summary": cmd_summary,
    "delete": cmd_delete,
}
