"""
Session management module for voice consultations.

Provides SQLite-based persistence for consultation sessions,
including dialogue history, anketa data, and session lifecycle.

Usage:
    from src.session import SessionManager, ConsultationSession

    mgr = SessionManager()
    session = mgr.create_session(room_name="my-room")
    print(session.session_id, session.unique_link)
"""

from src.session.models import ConsultationSession, VALID_STATUSES
from src.session.manager import SessionManager

__all__ = [
    "SessionManager",
    "ConsultationSession",
    "VALID_STATUSES",
]
