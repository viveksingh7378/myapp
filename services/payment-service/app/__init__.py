"""
payment-service app package.

Exposes the Flask application instance and database helpers so that
test modules can import directly: ``from app.app import app, init_db``.
"""

from .app import app, init_db, get_db  # noqa: F401

__all__ = ["app", "init_db", "get_db"]
