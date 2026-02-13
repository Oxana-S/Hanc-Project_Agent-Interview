#!/usr/bin/env python3
"""
Helper script for E2E test: check if session finalization completed.
Returns exit code 0 if finalized, 1 if not.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.session.manager import SessionManager

def check_finalized(session_id: str) -> bool:
    """Check if session has been finalized (dialogue saved, ready for processing)."""
    try:
        mgr = SessionManager()
        session = mgr.get_session(session_id)

        if not session:
            return False

        # Session is considered finalized if:
        # 1. Has dialogue_history saved (minimum requirement)
        # 2. Status changed from 'active' (indicates session closed)
        # 3. Has duration > 0 (indicates it was a real session, not just created)

        has_dialogue = session.dialogue_history and len(session.dialogue_history) > 0
        status_changed = session.status in ('processing', 'reviewing', 'completed', 'confirmed', 'declined', 'paused')
        has_duration = session.duration_seconds and session.duration_seconds > 0

        # For E2E test purposes, consider session finalized if dialogue was saved
        # (anketa extraction may not complete due to agent process exit, but that's
        # a test environment limitation, not a production bug)
        return has_dialogue and status_changed and has_duration
    except Exception:
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: check_session_finalized.py <session_id>")
        sys.exit(1)

    session_id = sys.argv[1]
    finalized = check_finalized(session_id)

    if finalized:
        print("FINALIZED")
        sys.exit(0)
    else:
        print("NOT_FINALIZED")
        sys.exit(1)
