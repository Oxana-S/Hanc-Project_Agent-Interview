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

        # R21-22: Skip already-applied migrations
        row = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (migration_name,)
        ).fetchone()
        if row:
            continue

        # Load migration module dynamically
        spec = importlib.util.spec_from_file_location(migration_name, migration_file)
        if not spec or not spec.loader:
            continue

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Run upgrade function
        if hasattr(module, "upgrade"):
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)",
                (migration_name,)
            )
            conn.commit()
