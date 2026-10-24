"""Starting the web server."""

from __future__ import annotations

import argparse
import webbrowser
from threading import Timer

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True) -> int:
    try:
        import uvicorn

        from focus_tracker.web.app import create_app
    except ImportError:
        print("The web app needs FastAPI and Uvicorn. Install them with:\n"
              '    pip install -e ".[web]"')
        return 1
    url = f"http://{host}:{port}"
    print(f"Focus Tracker is running at {url}  (press Ctrl+C to stop)")
    if open_browser:
        Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="focus web", description="Run the Focus Tracker website.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args(argv)
    return serve(args.host, args.port, not args.no_browser)
