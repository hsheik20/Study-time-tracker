"""Focus Tracker web app: a FastAPI backend serving a dashboard frontend.

Requires the optional web dependencies: pip install -e ".[web]"
"""


def __getattr__(name):
    # Imported lazily so `focus web` can explain how to install FastAPI
    # instead of failing with an ImportError.
    if name == "create_app":
        from focus_tracker.web.app import create_app

        return create_app
    raise AttributeError(name)


__all__ = ["create_app"]
