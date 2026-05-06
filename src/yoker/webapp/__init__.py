"""Webapp module for Yoker Quart application.

Provides WebSocket-based chat interface for real-time streaming.
"""

from yoker.webapp.app import create_app

# Create default app for uvicorn
# This allows: uv run uvicorn yoker.webapp:app
app = create_app()

__all__ = ["create_app", "app"]