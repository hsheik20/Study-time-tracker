"""Launch Focus Tracker.

Works both as `python3 -m focus_tracker` and by running this file directly
(e.g. VS Code's "Run Python File" button).
"""

if not __package__:
    # Run as a plain file, Python puts this package's own folder on sys.path
    # instead of the project root, so `import focus_tracker` would fail.
    # Swap it for the project root.
    import sys
    from pathlib import Path

    sys.path[0] = str(Path(__file__).resolve().parent.parent)

from focus_tracker.cli import main

raise SystemExit(main())
