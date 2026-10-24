"""Run the web app: `python3 -m focus_tracker.web`, `focus web`, or run this
file directly (e.g. VS Code's Run button)."""

if not __package__:
    # Run as a plain file: put the project root on sys.path (see focus_tracker/__main__.py).
    import sys
    from pathlib import Path

    sys.path[0] = str(Path(__file__).resolve().parents[2])

from focus_tracker.web.server import main

raise SystemExit(main())
