"""
SessionManager - SQLite-based session storage for consultation sessions.

Uses the standard library sqlite3 module for zero-dependency persistence.
Stores dialogue_history and anketa_data as JSON text in SQLite columns.
Thread-safe with check_same_thread=False.
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import structlog

from src.session.models import ConsultationSession, VALID_STATUSES

logger = structlog.get_logger("session")


class SessionManager:
    """
    Manages consultation sessions using SQLite.

    Provides CRUD operations for ConsultationSession objects,
    with JSON serialization for complex fields (dialogue_history, anketa_data).
    """

    def __init__(self, db_path: str = "data/sessions.db"):
        """
        Initialize SessionManager with SQLite database.

        Args:
            db_path: Path to SQLite database file. Parent directories
                     are created automatically if they don't exist.
        """
        self.db_path = db_path

        # Ensure parent directory exists
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # Connect to SQLite (thread-safe)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Create table if not exists
        self._create_table()

        logger.info("session_manager_initialized", db_path=db_path)

    def _create_table(self):
        """Create the sessions table if it doesn't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                room_name TEXT NOT NULL DEFAULT '',
                unique_link TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                dialogue_history TEXT NOT NULL DEFAULT '[]',
                anketa_data TEXT,
                anketa_md TEXT,
                company_name TEXT,
                contact_name TEXT,
                duration_seconds REAL NOT NULL DEFAULT 0.0,
                output_dir TEXT
            )
        """)
        self._conn.commit()
        logger.debug("sessions_table_ensured")

    def _session_from_row(self, row: sqlite3.Row) -> ConsultationSession:
        """
        Deserialize a database row into a ConsultationSession.

        Args:
            row: SQLite Row object.

        Returns:
            ConsultationSession instance.
        """
        return ConsultationSession(
            session_id=row["session_id"],
            room_name=row["room_name"],
            unique_link=row["unique_link"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            dialogue_history=json.loads(row["dialogue_history"]),
            anketa_data=json.loads(row["anketa_data"]) if row["anketa_data"] else None,
            anketa_md=row["anketa_md"],
            company_name=row["company_name"],
            contact_name=row["contact_name"],
            duration_seconds=row["duration_seconds"],
            output_dir=row["output_dir"],
        )

    def create_session(self, room_name: str = "") -> ConsultationSession:
        """
        Create a new consultation session.

        Generates a short session_id (uuid4[:8]) and a full UUID unique_link.

        Args:
            room_name: LiveKit room name (optional).

        Returns:
            Newly created ConsultationSession.
        """
        now = datetime.now()
        session = ConsultationSession(
            session_id=str(uuid.uuid4())[:8],
            room_name=room_name,
            unique_link=str(uuid.uuid4()),
            status="active",
            created_at=now,
            updated_at=now,
        )

        self._conn.execute(
            """
            INSERT INTO sessions (
                session_id, room_name, unique_link, status,
                created_at, updated_at, dialogue_history,
                anketa_data, anketa_md, company_name, contact_name,
                duration_seconds, output_dir
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_id,
                session.room_name,
                session.unique_link,
                session.status,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                json.dumps(session.dialogue_history, ensure_ascii=False),
                None,  # anketa_data
                None,  # anketa_md
                None,  # company_name
                None,  # contact_name
                session.duration_seconds,
                None,  # output_dir
            ),
        )
        self._conn.commit()

        logger.info(
            "session_created",
            session_id=session.session_id,
            room_name=room_name,
            unique_link=session.unique_link,
        )

        return session

    def get_session(self, session_id: str) -> Optional[ConsultationSession]:
        """
        Retrieve a session by its session_id.

        Args:
            session_id: Short session identifier (8 chars).

        Returns:
            ConsultationSession if found, None otherwise.
        """
        cursor = self._conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()

        if row is None:
            logger.warning("session_not_found", session_id=session_id)
            return None

        session = self._session_from_row(row)
        logger.debug("session_loaded", session_id=session_id)
        return session

    def get_session_by_link(self, unique_link: str) -> Optional[ConsultationSession]:
        """
        Retrieve a session by its unique link.

        Args:
            unique_link: Full UUID unique link.

        Returns:
            ConsultationSession if found, None otherwise.
        """
        cursor = self._conn.execute(
            "SELECT * FROM sessions WHERE unique_link = ?",
            (unique_link,),
        )
        row = cursor.fetchone()

        if row is None:
            logger.warning("session_not_found_by_link", unique_link=unique_link)
            return None

        session = self._session_from_row(row)
        logger.debug("session_loaded_by_link", session_id=session.session_id)
        return session

    def update_session(self, session: ConsultationSession) -> bool:
        """
        Update all fields of an existing session.

        Serializes dialogue_history and anketa_data as JSON text.

        Args:
            session: ConsultationSession with updated fields.

        Returns:
            True if the session was found and updated, False otherwise.
        """
        session.updated_at = datetime.now()

        cursor = self._conn.execute(
            """
            UPDATE sessions SET
                room_name = ?,
                unique_link = ?,
                status = ?,
                updated_at = ?,
                dialogue_history = ?,
                anketa_data = ?,
                anketa_md = ?,
                company_name = ?,
                contact_name = ?,
                duration_seconds = ?,
                output_dir = ?
            WHERE session_id = ?
            """,
            (
                session.room_name,
                session.unique_link,
                session.status,
                session.updated_at.isoformat(),
                json.dumps(session.dialogue_history, ensure_ascii=False),
                json.dumps(session.anketa_data, ensure_ascii=False) if session.anketa_data else None,
                session.anketa_md,
                session.company_name,
                session.contact_name,
                session.duration_seconds,
                session.output_dir,
                session.session_id,
            ),
        )
        self._conn.commit()

        if cursor.rowcount == 0:
            logger.warning("session_update_no_rows", session_id=session.session_id)
            return False

        logger.info("session_updated", session_id=session.session_id)
        return True

    def update_anketa(self, session_id: str, anketa_data: dict, anketa_md: str = None) -> bool:
        """
        Update only the anketa-related fields of a session.

        Args:
            session_id: Short session identifier.
            anketa_data: Anketa data as dict (e.g. from FinalAnketa.model_dump()).
            anketa_md: Anketa rendered as Markdown (optional).

        Returns:
            True if the session was found and updated, False otherwise.
        """
        now = datetime.now()

        cursor = self._conn.execute(
            """
            UPDATE sessions SET
                anketa_data = ?,
                anketa_md = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(anketa_data, ensure_ascii=False),
                anketa_md,
                now.isoformat(),
                session_id,
            ),
        )
        self._conn.commit()

        if cursor.rowcount == 0:
            logger.warning("session_anketa_update_no_rows", session_id=session_id)
            return False

        logger.info("session_anketa_updated", session_id=session_id)
        return True

    def update_status(self, session_id: str, status: str) -> bool:
        """
        Update only the status of a session.

        Args:
            session_id: Short session identifier.
            status: New status (must be one of: active, paused, reviewing, confirmed, declined).

        Returns:
            True if the session was found and updated, False otherwise.

        Raises:
            ValueError: If the status is not valid.
        """
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )

        now = datetime.now()

        cursor = self._conn.execute(
            """
            UPDATE sessions SET
                status = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                status,
                now.isoformat(),
                session_id,
            ),
        )
        self._conn.commit()

        if cursor.rowcount == 0:
            logger.warning("session_status_update_no_rows", session_id=session_id)
            return False

        logger.info("session_status_updated", session_id=session_id, status=status)
        return True

    def list_sessions(self, status: str = None) -> List[ConsultationSession]:
        """
        List all sessions, optionally filtered by status.

        Args:
            status: Filter by status (optional). If None, returns all sessions.

        Returns:
            List of ConsultationSession objects ordered by created_at descending.
        """
        if status is not None:
            cursor = self._conn.execute(
                "SELECT * FROM sessions WHERE status = ? ORDER BY created_at DESC",
                (status,),
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC"
            )

        rows = cursor.fetchall()
        sessions = [self._session_from_row(row) for row in rows]

        logger.debug(
            "sessions_listed",
            count=len(sessions),
            status_filter=status,
        )

        return sessions

    def close(self):
        """Close the SQLite connection."""
        self._conn.close()
        logger.info("session_manager_closed")
