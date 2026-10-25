"""Public demo mode: each visitor's data lives in their own browser.

Turned on with FOCUS_TRACKER_DEMO=1 (the hosted demo on Render). The server
stores no session data. The browser keeps the visitor's sessions, activities
and AI reports in localStorage and sends them with every API call, wrapped in
an envelope posted to /api/demo:

    {"method": "PATCH", "path": "/sessions/3", "query": "", "body": {...},
     "data": {"activities": [...], "sessions": [...]}, "reports": {...},
     "tz_offset": 420}

The data is validated, loaded into an in-memory Storage, and the normal API
route runs against it. The response carries the route's result plus any
changed data for the browser to save:

    {"data": <route result>, "state": <new data, if changed>, "reports": <if changed>}

So visitors are isolated from each other, data survives server restarts, and
every existing route works unchanged. Direct calls to the data routes are
refused in demo mode, so nothing can touch a server-side file.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

from fastapi import APIRouter, Query, Request

from focus_tracker.insights.service import KEEP_REPORTS, RequestLimiter, VisitorLimiter, _env_int
from focus_tracker.models import Session
from focus_tracker.tracker import MAX_DISTRACTIONS, MAX_TEXT, Tracker
from focus_tracker.web.schemas import MAX_MINUTES

ENV_VAR = "FOCUS_TRACKER_DEMO"
ENVELOPE_PATH = "/api/demo"
OPEN_PATHS = {"/api/health", "/api/demo/sample", "/api/demo/whoami", "/api/docs", "/api/openapi.json"}

# Limits on what a browser may send. Generous for a demo, small enough to be cheap.
MAX_BODY_BYTES = 1_000_000
MAX_SESSIONS = 1500
MAX_ACTIVITIES = 200
MAX_PAUSES = 200
MAX_NAME = 100
MAX_TZ_OFFSET = 14 * 60
METHODS = {"GET", "POST", "PATCH", "DELETE"}
SESSION_KEYS = {"id", "activity", "start", "end", "note", "target_seconds", "pauses",
                "location", "distractions", "reflection", "sample"}
WEEK_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def enabled() -> bool:
    return os.environ.get(ENV_VAR, "").strip().lower() in ("1", "true", "yes", "on")


def insights_limiters() -> tuple[RequestLimiter, VisitorLimiter]:
    """Conservative defaults for the public demo; override with environment variables."""
    shared = RequestLimiter(
        cooldown=0,
        per_hour=_env_int("FOCUS_TRACKER_DEMO_GLOBAL_PER_HOUR", 10),
        per_day=_env_int("FOCUS_TRACKER_DEMO_GLOBAL_PER_DAY", 20),
        max_concurrent=_env_int("FOCUS_TRACKER_DEMO_MAX_CONCURRENT", 2) or 1,
        limit_message="The demo has reached its shared AI report limit.",
    )
    per_visitor = VisitorLimiter(
        cooldown=_env_int("FOCUS_TRACKER_DEMO_VISITOR_COOLDOWN", 60),
        per_hour=_env_int("FOCUS_TRACKER_DEMO_VISITOR_PER_HOUR", 2),
        per_day=_env_int("FOCUS_TRACKER_DEMO_VISITOR_PER_DAY", 3),
    )
    return shared, per_visitor


# --- In-memory storage for one request --------------------------------------------


class MemoryReportStore:
    """The visitor's saved AI reports (from their browser), for one request."""

    def __init__(self, reports: dict):
        self.reports = dict(reports)
        self.changed = False

    def get(self, week_key: str) -> dict | None:
        return self.reports.get(week_key)

    def put(self, week_key: str, entry: dict) -> None:
        self.reports[week_key] = entry
        self.reports = dict(sorted(self.reports.items())[-KEEP_REPORTS:])
        self.changed = True


class MemoryStorage:
    """Storage backed by a dict instead of a file (same interface as Storage)."""

    path = None

    def __init__(self, data: dict, reports: dict | None = None):
        self._data = data
        self._version = 0
        self.changed = False
        self.report_store = MemoryReportStore(reports or {})

    def signature(self) -> int:
        return self._version

    @contextmanager
    def lock(self) -> Iterator[None]:
        yield  # each request has its own copy, so there's nothing to lock

    def load(self) -> tuple[list[Session], list[str]]:
        sessions = [Session.from_dict(item) for item in self._data.get("sessions", [])]
        return sessions, [str(name) for name in self._data.get("activities", [])]

    def save(self, sessions: list[Session], activities: list[str]) -> None:
        self._data = {"activities": list(activities), "sessions": [s.to_dict() for s in sessions]}
        self._version += 1
        self.changed = True

    def dump(self) -> dict:
        return self._data


def no_server_storage():
    raise RuntimeError("Demo mode keeps no data on the server.")


# --- Validating what the browser sends ------------------------------------------


class DemoDataError(ValueError):
    """The browser sent data that isn't valid; shown to the visitor."""


def _text(value, field: str, limit: int, required: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise DemoDataError(f"Invalid {field}.")
    return value


def _time(value, field: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise DemoDataError(f"Invalid {field}.")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise DemoDataError(f"Invalid {field}.") from None
    if moment.tzinfo is not None or not 2000 <= moment.year <= 2100:
        raise DemoDataError(f"Invalid {field}.")
    return moment


def _session(raw) -> dict:
    if not isinstance(raw, dict) or not set(raw) <= SESSION_KEYS:
        raise DemoDataError("Invalid session.")
    if not isinstance(raw.get("id"), int) or isinstance(raw["id"], bool) or not 0 < raw["id"] < 10**9:
        raise DemoDataError("Invalid session id.")
    _text(raw.get("activity"), "activity name", MAX_NAME, required=True)
    start = _time(raw.get("start"), "session start")
    if raw.get("end") is not None and _time(raw["end"], "session end") < start:
        raise DemoDataError("A session can't end before it starts.")
    for field in ("note", "location", "reflection"):
        _text(raw.get(field, ""), field, MAX_TEXT[field])
    target = raw.get("target_seconds")
    if target is not None and (not isinstance(target, int) or isinstance(target, bool)
                               or not 0 < target <= MAX_MINUTES * 60):
        raise DemoDataError("Invalid session length.")
    pauses = raw.get("pauses", [])
    if not isinstance(pauses, list) or len(pauses) > MAX_PAUSES:
        raise DemoDataError("Invalid pauses.")
    for pause in pauses:
        if not isinstance(pause, list) or len(pause) != 2:
            raise DemoDataError("Invalid pause.")
        begin = _time(pause[0], "pause start")
        if pause[1] is not None and _time(pause[1], "pause end") < begin:
            raise DemoDataError("Invalid pause.")
    distractions = raw.get("distractions", [])
    if not isinstance(distractions, list) or len(distractions) > MAX_DISTRACTIONS:
        raise DemoDataError("Invalid distractions.")
    for item in distractions:
        _text(item, "distraction", MAX_TEXT["distraction"])
    if not isinstance(raw.get("sample", False), bool):
        raise DemoDataError("Invalid session.")
    return raw


def validate_data(data) -> dict:
    """Check the visitor's data strictly before it is used (or sent to Claude)."""
    if data is None:
        return {"activities": [], "sessions": []}
    if not isinstance(data, dict) or not set(data) <= {"activities", "sessions"}:
        raise DemoDataError("Invalid demo data.")
    activities = data.get("activities", [])
    sessions = data.get("sessions", [])
    if not isinstance(activities, list) or len(activities) > MAX_ACTIVITIES:
        raise DemoDataError("Too many activities.")
    if not isinstance(sessions, list) or len(sessions) > MAX_SESSIONS:
        raise DemoDataError("Too many sessions.")
    for name in activities:
        _text(name, "activity name", MAX_NAME, required=True)
    ids = [_session(raw)["id"] for raw in sessions]
    if len(ids) != len(set(ids)):
        raise DemoDataError("Duplicate session ids.")
    if sum(1 for raw in sessions if raw.get("end") is None) > 1:
        raise DemoDataError("Only one session can be running.")
    return {"activities": activities, "sessions": sessions}


def validate_reports(reports) -> dict:
    """Saved reports only come back to the same browser, but must still be well-formed."""
    if reports is None:
        return {}
    if (not isinstance(reports, dict) or len(reports) > KEEP_REPORTS
            or not all(isinstance(k, str) and WEEK_KEY.match(k) and isinstance(v, dict)
                       for k, v in reports.items())):
        raise DemoDataError("Invalid saved reports.")
    return reports


# --- Who is asking (for per-visitor limits) --------------------------------------


def _ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _visitor_key(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """One key per visitor. An IPv6 user can switch between the many addresses
    in their /64 network, so the whole network counts as one visitor."""
    if ip.version == 4:
        return str(ip)
    if ip.ipv4_mapped:  # ::ffff:1.2.3.4 is just an IPv4 address
        return str(ip.ipv4_mapped)
    return str(ipaddress.IPv6Network(f"{ip}/64", strict=False))


def identify_visitor(scope: dict) -> tuple[str, str]:
    """The visitor's IP-based key and where it came from, for per-visitor limits.

    Render serves apps through Cloudflare, which sets CF-Connecting-IP to the
    address that connected to it, replacing any value the client sent. That is
    the only header trusted as-is. X-Forwarded-For is *appended to* by each
    proxy, so its left end is whatever the client wrote; only its right-most
    entry (added by the nearest proxy) is used, as a fallback. Values that
    aren't valid IP addresses are ignored. Never consulted: True-Client-IP
    (on Cloudflare it's Enterprise-only, so elsewhere it could be client-set)."""
    headers: dict[str, str] = {}
    for key, value in scope.get("headers", []):
        name = key.decode("latin-1").lower()
        if name not in headers:  # a repeated header can't override the first one
            headers[name] = value.decode("latin-1")
    cloudflare = _ip(headers.get("cf-connecting-ip", ""))
    if cloudflare:
        return _visitor_key(cloudflare), "cf-connecting-ip"
    hops = [hop for hop in headers.get("x-forwarded-for", "").split(",") if hop.strip()]
    nearest = _ip(hops[-1]) if hops else None
    if nearest:
        return _visitor_key(nearest), "x-forwarded-for (right-most)"
    client = scope.get("client")
    direct = _ip(client[0]) if client else None
    return (_visitor_key(direct) if direct else "unknown"), "connection"


def client_ip(scope: dict) -> str:
    return identify_visitor(scope)[0]


# --- The envelope middleware --------------------------------------------------------


class DemoMiddleware:
    """Unwraps /api/demo envelopes and runs the real route against the visitor's data."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        if scope["path"] == ENVELOPE_PATH and scope["method"] == "POST":
            return await self._envelope(scope, receive, send)
        if scope["path"] in OPEN_PATHS:
            return await self.app(scope, receive, send)
        await _json(send, 404, {"detail": "In the demo, your data is sent from your browser."})

    async def _envelope(self, scope, receive, send):
        try:
            envelope = json.loads(await _read_body(receive))
            if not isinstance(envelope, dict):
                raise DemoDataError("Invalid request.")
            method, path = envelope.get("method"), envelope.get("path")
            query = envelope.get("query") or ""
            if (method not in METHODS or not isinstance(path, str) or not path.startswith("/")
                    or len(path) > 200 or "?" in path or path.startswith("/demo")
                    or not isinstance(query, str) or len(query) > 500):
                raise DemoDataError("Invalid request.")
            offset = envelope.get("tz_offset", 0)
            if not isinstance(offset, int) or isinstance(offset, bool) or abs(offset) > MAX_TZ_OFFSET:
                raise DemoDataError("Invalid time zone.")
            storage = MemoryStorage(validate_data(envelope.get("data")),
                                    validate_reports(envelope.get("reports")))
            body = envelope.get("body")
            inner_body = b"" if body is None else json.dumps(body).encode()
        except _TooLarge:
            return await _json(send, 413, {"detail": "Your demo data is too large."})
        except (ValueError, UnicodeDecodeError) as error:  # DemoDataError and bad JSON
            message = str(error) if isinstance(error, DemoDataError) else "Invalid request."
            return await _json(send, 400, {"detail": message})

        state = dict(scope.get("state") or {})
        state.update(demo_storage=storage, demo_utc_offset=offset, demo_visitor=client_ip(scope))
        inner_scope = {
            **scope,
            "method": method,
            "path": "/api" + path,
            "raw_path": ("/api" + path).encode(),
            "query_string": query.encode(),
            "headers": [(b"content-type", b"application/json"), (b"accept", b"application/json"),
                        (b"content-length", str(len(inner_body)).encode())],
            "state": state,
        }
        response = {"status": 500, "headers": [], "body": bytearray()}
        finished = asyncio.Event()
        delivered = False

        async def inner_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": inner_body, "more_body": False}
            await finished.wait()  # like a real connection: idle until the response is done
            return {"type": "http.disconnect"}

        async def inner_send(message):
            if message["type"] == "http.response.start":
                response["status"] = message["status"]
                response["headers"] = message.get("headers", [])
            elif message["type"] == "http.response.body":
                response["body"] += message.get("body", b"")
                if not message.get("more_body"):
                    finished.set()

        try:
            await self.app(inner_scope, inner_receive, inner_send)
        finally:
            finished.set()

        try:
            result = json.loads(response["body"]) if response["body"] else None
        except ValueError:
            result = None
        payload: dict = {"data": result}
        if storage.changed:
            payload["state"] = storage.dump()
        if storage.report_store.changed:
            payload["reports"] = storage.report_store.reports
        extra = [(k, v) for k, v in response["headers"] if k.lower() == b"retry-after"]
        status = 200 if response["status"] == 204 else response["status"]
        await _json(send, status, payload, extra)


class _TooLarge(Exception):
    pass


async def _read_body(receive) -> bytes:
    body = bytearray()
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        body += message.get("body", b"")
        if len(body) > MAX_BODY_BYTES:
            raise _TooLarge
        if not message.get("more_body"):
            break
    return bytes(body)


async def _json(send, status: int, payload: dict, extra_headers: list | None = None) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"cache-control", b"no-store"), *(extra_headers or [])]})
    await send({"type": "http.response.body", "body": body})


# --- Sample data for new visitors -------------------------------------------------

router = APIRouter(tags=["demo"])

# (days ago, start hour, activity, planned minutes, focused minutes, location,
#  distractions, reflection, note). focused=None logs an untimed session.
SAMPLE_PLAN = [
    (13, 9.0, "CSE 373 homework", 50, 50, "Library", [], "Got through the heap problems.", "HW 4"),
    (12, 14.5, "Reading", 30, 30, "Home", [], "", "Atomic Habits ch. 3"),
    (11, 10.0, "Portfolio project", 60, 38, "Café", ["Group chat", "Noise"],
     "Too loud to concentrate after the lunch rush.", "Navbar layout"),
    (10, 7.5, "Meditation", 10, 10, "Home", [], "Calm start to the day.", ""),
    (9, 19.0, "Spanish practice", 25, 25, "Home", ["Phone notifications"], "", "Duolingo + flashcards"),
    (8, 9.5, "CSE 373 homework", 50, 50, "Library", [], "Mornings at the library work well.", "HW 4 graphs"),
    (7, 21.0, "Portfolio project", None, 45, "Home", [], "", "Logged afterwards"),
    (6, 9.0, "CSE 373 homework", 50, 50, "Library", ["Email"], "Finished HW 4 early.", "HW 4 final"),
    (6, 13.0, "Meditation", 5, 5, "Library", [], "", "Breathing exercise"),
    (5, 15.0, "Reading", 30, 21, "Home", ["Phone notifications", "Hunger"],
     "Should have eaten first.", "Atomic Habits ch. 5"),
    (4, 10.0, "Portfolio project", 90, 90, "Library", [], "Deep work block, shipped the about page.",
     "About page"),
    (3, 20.0, "Spanish practice", 25, 14, "Home", ["Group chat"], "", "Listening practice"),
    (2, 9.0, "CSE 373 homework", 50, 50, "Library", [], "Started HW 5 strong.", "HW 5"),
    (2, 16.0, "Meditation", 10, 10, "Home", [], "", ""),
    (1, 11.0, "Portfolio project", 60, 47, "Café", ["Noise", "Phone notifications"],
     "Café again; noise cut it short.", "Contact form"),
    (1, 18.5, "Reading", 30, 30, "Home", [], "", "Atomic Habits ch. 6"),
    (0, 8.0, "Meditation", 10, 10, "Home", [], "", ""),
]


def build_sample_data(now: datetime) -> dict:
    """Realistic example sessions from the last two weeks, ending before `now`."""
    storage = MemoryStorage({"activities": [], "sessions": []})
    tracker = Tracker(storage)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for days, hour, activity, planned, focused, location, distractions, reflection, note in SAMPLE_PLAN:
        start = midnight - timedelta(days=days) + timedelta(hours=hour)
        pause = 5 if planned and focused < planned else 0  # sessions ended early had a break
        end = start + timedelta(minutes=focused + pause)
        if end > now - timedelta(minutes=5):
            continue  # keep everything in the past
        if planned is None:
            session = tracker.add(activity, timedelta(minutes=focused), end, note, location)
        else:
            session = tracker.start(activity, note, now=start, target=timedelta(minutes=planned),
                                    location=location)
            if pause:
                tracker.pause(start + timedelta(minutes=focused // 2))
                tracker.resume(start + timedelta(minutes=focused // 2 + pause))
            tracker.stop(end)
        if distractions or reflection:
            tracker.annotate(session.id, distractions=distractions or None, reflection=reflection or None)
    data = storage.dump()
    for session in data["sessions"]:
        session["sample"] = True
    return {"data": data, "sample_activities": list(data["activities"])}


@router.get("/demo/whoami")
def whoami(request: Request) -> dict:
    """Which visitor key the demo's AI limits would use for this request.
    For checking after deployment that spoofed headers are ignored; it only
    ever shows a visitor their own address."""
    visitor, source = identify_visitor(request.scope)
    return {"visitor": visitor, "source": source}


@router.get("/demo/sample")
def sample(tz_offset: int = Query(0, ge=-MAX_TZ_OFFSET, le=MAX_TZ_OFFSET)) -> dict:
    """Starter data for a new visitor, in their local time."""
    now = (datetime.now(timezone.utc) - timedelta(minutes=tz_offset)).replace(tzinfo=None)
    return build_sample_data(now)
