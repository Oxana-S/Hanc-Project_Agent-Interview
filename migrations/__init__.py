"""
Database migrations for session management.

Migrations are run automatically on SessionManager initialization.
Each migration file follows the naming convention: NNN_description.py
"""

import sqlite3
from pathlib import Path
import importlib.util


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    """R21-22: Create migration tracking table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def run_all_migrations(conn: sqlite3.Connection) -> None:
    """
    Run all pending migrations in order.

    R21-22: Tracks applied migrations to prevent re-execution.

    Args:
        conn: SQLite database connection
    """
    _ensure_migration_table(conn)

    migrations_dir = Path(__file__).parent
    migration_files = sorted(migrations_dir.glob("0*.py"))

    for migration_file in migration_files:
        migration_name = migration_file.stem

        # R22-03: Atomically claim migration via INSERT OR IGNORE to prevent
        # TOCTOU race when multiple processes start simultaneously
        cursor = conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
            (migration_name,)
        )
        if cursor.rowcount == 0:
            conn.commit()  # Release any implicit transaction from INSERT OR IGNORE
            continue  # Already applied (or being applied by another process)

        # Load and run migration module
        try:
            spec = importlib.util.spec_from_file_location(migration_name, migration_file)
            if not spec or not spec.loader:
                conn.execute("DELETE FROM schema_migrations WHERE version = ?", (migration_name,))
                conn.commit()
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, "upgrade"):
                module.upgrade(conn)
            conn.commit()
        except Exception:
            # Rollback claim so migration can be retried
            conn.execute("DELETE FROM schema_migrations WHERE version = ?", (migration_name,))
            conn.commit()
            raise
