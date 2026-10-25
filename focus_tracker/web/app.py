"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from focus_tracker import __version__
from focus_tracker.insights.report import ClaudeReportGenerator, load_env
from focus_tracker.insights.service import InsightsService
from focus_tracker.storage import Storage
from focus_tracker.tracker import NotFoundError, TrackerError
from focus_tracker.web.routes import activities, dashboard, insights, sessions, stats

STATIC_DIR = Path(__file__).parent / "static"


def create_app(storage_factory: Callable[[], Storage] = Storage,
               insights_service: InsightsService | None = None) -> FastAPI:
    """Build the app. `storage_factory` picks the data file (tests pass a temp one);
    by default it's the same file the CLI uses. `insights_service` defaults to real Claude
    calls, with the API key loaded from .env."""
    app = FastAPI(title="Focus Tracker", version=__version__, docs_url="/api/docs",
                  redoc_url=None, openapi_url="/api/openapi.json")
    app.state.storage_factory = storage_factory
    if insights_service is None:
        load_env()
        insights_service = InsightsService(ClaudeReportGenerator())
    app.state.insights = insights_service

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

    # Make browsers revalidate the page and its JS/CSS on every load (unchanged files
    # still come back as a cheap 304). Without this they may keep running an old cached
    # module against a newer API after an update.
    @app.middleware("http")
    async def revalidate_static(request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
