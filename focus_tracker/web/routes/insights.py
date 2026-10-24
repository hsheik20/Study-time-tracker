"""Placeholder for Claude-powered weekly insights (a later phase).

The frontend already has an "AI Insights" page that calls this endpoint, so
the feature can be added here without touching the rest of the app.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["insights"])


@router.get("/insights")
def insights() -> dict:
    return {
        "available": False,
        "message": "Weekly AI insights are coming in a future update.",
        "planned": [
            "A weekly summary of where your focus time went",
            "Patterns in when you focus best",
            "Suggestions for session lengths and goals",
        ],
    }
