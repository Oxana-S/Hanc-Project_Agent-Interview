"""
Web server module for Hanc.AI Voice Consultant.

Provides a FastAPI application that serves the consultation frontend
and exposes REST API endpoints for session and anketa management.

Usage:
    from src.web.server import app

    # Run with uvicorn:
    # uvicorn src.web.server:app --host 0.0.0.0 --port 8000
"""

from src.web.server import app

__all__ = ["app"]
