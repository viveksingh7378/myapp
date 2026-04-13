"""
Root app package (demo/core Flask service).

Exposes the Flask application instance and helpers used by the root-level
test suite (``tests/test_core.py``).

Usage:
    from app.app import app, get_initial_items
"""

from .app import app, get_initial_items  # noqa: F401

__all__ = ["app", "get_initial_items"]
