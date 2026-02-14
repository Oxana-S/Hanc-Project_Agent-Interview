"""
SessionManager - SQLite-based session storage for consultation sessions.

Uses the standard library sqlite3 module for zero-dependency persistence.
Stores dialogue_history and anketa_data as JSON text in SQLite columns.
Thread-safe with check_same_thread=False.
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import structlog

from src.session.models import ConsultationSession, SessionStatus, VALID_STATUSES
from src.session.status import validate_transition
from src.session.exceptions import InvalidTransitionError

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

        # Connect to SQLite + thread lock for concurrent access safety (R5-04)
        # R15-06: RLock allows get_session() to be called from within locked contexts
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Enable WAL mode for safe multi-process access (web + agent containers)
        self._conn.execute("PRAGMA journal_mode=WAL")

        # Create table if not exists
        self._create_table()

        # Run database migrations
        self._run_migrations()

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

        # Migration: add document_context column for existing DBs
        try:
            self._conn.execute("SELECT document_context FROM sessions LIMIT 1")
        except sqlite3.OperationalError as e:
            if "no such column" in str(e).lower():
                self._conn.execute("ALTER TABLE sessions ADD COLUMN document_context TEXT")
                self._conn.commit()
                logger.info("migration_added_document_context_column")
            else:
                raise

        # Migration: add voice_config column for existing DBs
        try:
            self._conn.execute("SELECT voice_config FROM sessions LIMIT 1")
        except sqlite3.OperationalError as e:
            if "no such column" in str(e).lower():
                self._conn.execute("ALTER TABLE sessions ADD COLUMN voice_config TEXT")
                self._conn.commit()
                logger.info("migration_added_voice_config_column")
            else:
                raise

        logger.debug("sessions_table_ensured")

    def _run_migrations(self):
        """Run database migrations for status normalization and schema updates."""
        try:
            from migrations import run_all_migrations
            run_all_migrations(self._conn)
        except Exception as e:
            logger.warning("migration_failed", error=str(e), error_type=type(e).__name__)

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
            document_context=json.loads(row["document_context"]) if row["document_context"] else None,
            voice_config=json.loads(row["voice_config"]) if row["voice_config"] else None,
            company_name=row["company_name"],
            contact_name=row["contact_name"],
            duration_seconds=row["duration_seconds"],
            output_dir=row["output_dir"],
        )

    def create_session(self, room_name: str = "", voice_config: dict = None) -> ConsultationSession:
        """
        Create a new consultation session.

        Generates a short session_id (uuid4[:8]) and a full UUID unique_link.
        Retries up to 3 times on ID collision (R4-12).

        Args:
            room_name: LiveKit room name (optional).
            voice_config: Voice agent settings (silence_duration_ms, etc.).

        Returns:
            Newly created ConsultationSession.
        """
        max_retries = 3
        for attempt in range(max_retries):
            now = datetime.now(timezone.utc)
            session = ConsultationSession(
                session_id=str(uuid.uuid4())[:8],
                room_name=room_name,
                unique_link=str(uuid.uuid4()),
                status="active",
                created_at=now,
                updated_at=now,
                voice_config=voice_config,
            )

            try:
                # R11-03: Lock for thread safety (consistent with all other write methods)
                with self._lock:
                    self._conn.execute(
                        """
                        INSERT INTO sessions (
                            session_id, room_name, unique_link, status,
                            created_at, updated_at, dialogue_history,
                            anketa_data, anketa_md, company_name, contact_name,
                            duration_seconds, output_dir, voice_config
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            json.dumps(voice_config, ensure_ascii=False) if voice_config else None,
                        ),
                    )
                    self._conn.commit()
            except sqlite3.IntegrityError:
                if attempt < max_retries - 1:
                    logger.warning("session_id_collision", session_id=session.session_id, attempt=attempt + 1)
                    continue
                raise

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
        # R19-04: Lock reads to prevent concurrent access on shared connection
        with self._lock:
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
        # R19-04: Lock reads to prevent concurrent access on shared connection
        with self._lock:
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
        # R9-12: Lock for thread safety
        with self._lock:
            return self._update_session_locked(session)

    def _update_session_locked(self, session: ConsultationSession) -> bool:
        """Internal locked implementation of update_session."""
        # R10-14: Validate status transition if status changed
        existing = self.get_session(session.session_id)
        if existing and existing.status != session.status:
            try:
                current = SessionStatus(existing.status)
                target = SessionStatus(session.status)
                validate_transition(current, target)
            except (ValueError, InvalidTransitionError):
                logger.warning("update_session_invalid_transition",
                               session_id=session.session_id,
                               current=existing.status, target=session.status)
                session.status = existing.status  # Keep current status

        session.updated_at = datetime.now(timezone.utc)

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
                document_context = ?,
                company_name = ?,
                contact_name = ?,
                duration_seconds = ?,
                output_dir = ?,
                voice_config = ?
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
                json.dumps(session.document_context, ensure_ascii=False) if session.document_context else None,
                session.company_name,
                session.contact_name,
                session.duration_seconds,
                session.output_dir,
                json.dumps(session.voice_config, ensure_ascii=False) if session.voice_config else None,
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

        IMPORTANT: This method now does a MERGE, not a REPLACE. It reads existing
        anketa_data, merges new fields, and writes back. This prevents client edits
        from erasing LLM-extracted data.

        Args:
            session_id: Short session identifier.
            anketa_data: Anketa data as dict (e.g. from FinalAnketa.model_dump()).
                         New fields will be merged into existing data.
            anketa_md: Anketa rendered as Markdown (optional).

        Returns:
            True if the session was found and updated, False otherwise.
        """
        # R5-04: Lock the entire read-modify-write cycle to prevent data races
        with self._lock:
            return self._update_anketa_locked(session_id, anketa_data, anketa_md)

    @staticmethod
    def _deep_merge(base: dict, override: dict, _depth: int = 0) -> dict:
        """Recursively merge override into base. Lists and scalars overwrite.

        None values are only skipped when a non-None value already exists in base
        (prevents LLM extraction from erasing user-edited fields).
        R16-12: Depth limit prevents stack overflow from crafted payloads.
        """
        if _depth > 20:
            return override  # Prevent stack overflow
        for key, val in override.items():
            if val is None and key in base and base[key] is not None:
                continue  # Don't overwrite existing data with None
            if isinstance(val, dict) and isinstance(base.get(key), dict):
                base[key] = SessionManager._deep_merge(base[key], val, _depth + 1)
            else:
                base[key] = val
        return base

    def _update_anketa_locked(self, session_id: str, anketa_data: dict, anketa_md: str = None) -> bool:
        """Internal locked implementation of update_anketa."""
        # 1. Read existing anketa to preserve LLM-extracted data
        session = self.get_session(session_id)
        if not session:
            logger.warning("session_not_found_for_anketa_update", session_id=session_id)
            return False

        # 2. Deep merge: new values overwrite old, nested dicts are merged recursively (R4-13)
        # R6-11: Copy existing data to avoid mutating the in-memory session object
        import copy
        existing_anketa = copy.deepcopy(session.anketa_data) if session.anketa_data else {}
        self._deep_merge(existing_anketa, anketa_data)

        # 3. Update database with merged data
        # R4-14: Only overwrite anketa_md if a new value is provided
        now = datetime.now(timezone.utc)
        if anketa_md is not None:
            cursor = self._conn.execute(
                """
                UPDATE sessions SET
                    anketa_data = ?,
                    anketa_md = ?,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (
                    json.dumps(existing_anketa, ensure_ascii=False),
                    anketa_md,
                    now.isoformat(),
                    session_id,
                ),
            )
        else:
            cursor = self._conn.execute(
                """
                UPDATE sessions SET
                    anketa_data = ?,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (
                    json.dumps(existing_anketa, ensure_ascii=False),
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

    def update_document_context(self, session_id: str, document_context: dict) -> bool:
        """
        Update only the document_context field of a session.

        Args:
            session_id: Short session identifier.
            document_context: Serialized DocumentContext dict.

        Returns:
            True if the session was found and updated, False otherwise.
        """
        # R9-12: Lock for thread safety
        with self._lock:
            now = datetime.now(timezone.utc)

            cursor = self._conn.execute(
                """
                UPDATE sessions SET
                    document_context = ?,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (
                    json.dumps(document_context, ensure_ascii=False),
                    now.isoformat(),
                    session_id,
                ),
            )
            self._conn.commit()

            if cursor.rowcount == 0:
                logger.warning("session_document_context_update_no_rows", session_id=session_id)
                return False

            logger.info("session_document_context_updated", session_id=session_id)
            return True

    def update_status(self, session_id: str, status: SessionStatus | str, force: bool = False) -> bool:
        """
        Update only the status of a session with transition validation.

        Args:
            session_id: Short session identifier.
            status: New status (SessionStatus enum or string for backward compatibility).
            force: If True, bypass transition validation (admin override).

        Returns:
            True if the session was found and updated, False otherwise.

        Raises:
            ValueError: If the status is not valid.
            InvalidTransitionError: If the transition is not allowed (unless force=True).
        """
        # Backward compatibility: accept strings but warn
        if isinstance(status, str):
            logger.warning(
                "update_status: string deprecated, use SessionStatus enum",
                status=status,
                session_id=session_id
            )
            try:
                status = SessionStatus(status)
            except ValueError:
                raise ValueError(
                    f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
                )

        # R7-02: Lock to prevent concurrent status updates violating state machine
        with self._lock:
            # Get current session to validate transition
            session = self.get_session(session_id)
            if not session:
                logger.warning("session_status_update_no_session", session_id=session_id)
                return False

            # Validate transition (unless force=True)
            if not force:
                try:
                    current_status = SessionStatus(session.status)
                    validate_transition(current_status, status)
                except ValueError:
                    # R12-12: Invalid current status — block update instead of falling through
                    logger.warning(
                        "session_status_invalid_current",
                        session_id=session_id,
                        current=session.status,
                        new=status.value
                    )
                    return False

            now = datetime.now(timezone.utc)

            cursor = self._conn.execute(
                """
                UPDATE sessions SET
                    status = ?,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (
                    status.value,
                    now.isoformat(),
                    session_id,
                ),
            )
            self._conn.commit()

            # R12-09: Check rowcount inside lock
            if cursor.rowcount == 0:
                logger.warning("session_status_update_no_rows", session_id=session_id)
                return False

        logger.info("session_status_updated", session_id=session_id, status=status.value)
        return True

    def update_metadata(self, session_id: str, company_name: str = None, contact_name: str = None) -> bool:
        """Update only company_name and/or contact_name (no full session overwrite)."""
        updates = []
        params = []
        if company_name is not None:
            updates.append("company_name = ?")
            params.append(company_name)
        if contact_name is not None:
            updates.append("contact_name = ?")
            params.append(contact_name)
        if not updates:
            return False
        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(session_id)
        # R9-12: Lock for thread safety
        with self._lock:
            cursor = self._conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?",
                params,
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def update_voice_config(self, session_id: str, config_updates: dict) -> bool:
        """Atomically merge updates into voice_config (R14-06: no full-session overwrite).

        Args:
            session_id: Short session identifier.
            config_updates: Dict of voice_config keys to update (merged into existing).

        Returns:
            True if the session was found and updated, False otherwise.
        """
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            # R17-05: Copy to avoid mutating in-memory session object
            existing = dict(session.voice_config) if session.voice_config else {}
            existing.update(config_updates)
            now = datetime.now(timezone.utc)
            cursor = self._conn.execute(
                "UPDATE sessions SET voice_config = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(existing, ensure_ascii=False), now.isoformat(), session_id),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def update_dialogue(self, session_id: str, dialogue_history: list, duration_seconds: float, status: str = None) -> bool:
        """Update dialogue_history, duration, and optionally status (no full session overwrite)."""
        # R9-12: Lock for thread safety
        with self._lock:
            now = datetime.now(timezone.utc)
            validated_status = None
            if status:
                # R10-02: Validate status transition through state machine
                session = self.get_session(session_id)
                if session:
                    try:
                        current = SessionStatus(session.status)
                        target = SessionStatus(status)
                        if target != current:
                            validate_transition(current, target)
                        validated_status = status
                    except (ValueError, InvalidTransitionError):
                        logger.warning("update_dialogue_invalid_transition",
                                       session_id=session_id, current=session.status, target=status)
            if validated_status:
                cursor = self._conn.execute(
                    "UPDATE sessions SET dialogue_history = ?, duration_seconds = ?, status = ?, updated_at = ? WHERE session_id = ?",
                    (json.dumps(dialogue_history, ensure_ascii=False), duration_seconds, validated_status, now.isoformat(), session_id),
                )
            else:
                cursor = self._conn.execute(
                    "UPDATE sessions SET dialogue_history = ?, duration_seconds = ?, updated_at = ? WHERE session_id = ?",
                    (json.dumps(dialogue_history, ensure_ascii=False), duration_seconds, now.isoformat(), session_id),
                )
            self._conn.commit()
            return cursor.rowcount > 0

    def list_sessions_summary(self, status: str = None, limit: int = 50, offset: int = 0) -> tuple:
        """
        List sessions as lightweight dicts (no dialogue_history, anketa_data, document_context).

        Args:
            status: Filter by status (optional).
            limit: Max number of results.
            offset: Skip first N results.

        Returns:
            Tuple of (list of dicts with summary fields, total_count).
        """
        # R20-08: Acquire lock for consistent read across two queries
        with self._lock:
            where_clause = ""
            params = []

            if status:
                where_clause = " WHERE status = ?"
                params.append(status)

            # Total count (without LIMIT/OFFSET) for pagination
            count_row = self._conn.execute(
                f"SELECT COUNT(*) FROM sessions{where_clause}", params
            ).fetchone()
            total_count = count_row[0] if count_row else 0

            query = f"""
                SELECT session_id, unique_link, status, created_at, updated_at,
                       company_name, contact_name, duration_seconds, room_name,
                       CASE WHEN document_context IS NOT NULL THEN 1 ELSE 0 END AS has_documents
                FROM sessions{where_clause}
                ORDER BY created_at DESC LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])

            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()

        sessions = []
        for row in rows:
            sessions.append({
                "session_id": row["session_id"],
                "unique_link": row["unique_link"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "company_name": row["company_name"],
                "contact_name": row["contact_name"],
                "duration_seconds": row["duration_seconds"],
                "room_name": row["room_name"],
                "has_documents": bool(row["has_documents"]),
            })

        logger.debug("sessions_summary_listed", count=len(sessions), total=total_count, status_filter=status)
        return sessions, total_count

    def delete_sessions(self, session_ids: list) -> int:
        """Delete sessions by IDs. Returns count of deleted rows."""
        if not session_ids:
            return 0
        placeholders = ",".join("?" * len(session_ids))
        # R9-12: Lock for thread safety
        with self._lock:
            cursor = self._conn.execute(
                f"DELETE FROM sessions WHERE session_id IN ({placeholders})",
                session_ids,
            )
            self._conn.commit()
        logger.info("sessions_deleted", count=cursor.rowcount, session_ids=session_ids)
        return cursor.rowcount

    def list_sessions(self, status: str = None) -> List[ConsultationSession]:
        """
        List all sessions, optionally filtered by status.

        Args:
            status: Filter by status (optional). If None, returns all sessions.

        Returns:
            List of ConsultationSession objects ordered by created_at descending.
        """
        # R19-04: Lock reads to prevent concurrent access on shared connection
        with self._lock:
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
