"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from focus_tracker import __version__
from focus_tracker.storage import Storage
from focus_tracker.tracker import NotFoundError, TrackerError
from focus_tracker.web.routes import activities, dashboard, insights, sessions, stats

STATIC_DIR = Path(__file__).parent / "static"


def create_app(storage_factory: Callable[[], Storage] = Storage) -> FastAPI:
    """Build the app. `storage_factory` picks the data file (tests pass a temp one);
    by default it's the same file the CLI uses."""
    app = FastAPI(title="Focus Tracker", version=__version__, docs_url="/api/docs",
                  redoc_url=None, openapi_url="/api/openapi.json")
    app.state.storage_factory = storage_factory

    for module in (dashboard, sessions, activities, stats, insights):
        app.include_router(module.router, prefix="/api")

    # The tracker's own error messages are written for users, so pass them on.
    @app.exception_handler(TrackerError)
    def tracker_error(request: Request, error: TrackerError) -> JSONResponse:
        status = 404 if isinstance(error, NotFoundError) else 409
        return JSONResponse({"detail": str(error)}, status_code=status)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
