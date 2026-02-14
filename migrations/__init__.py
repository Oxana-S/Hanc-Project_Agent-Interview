"""
Database migrations for session management.

Migrations are run automatically on SessionManager initialization.
Each migration file follows the naming convention: NNN_description.py
"""

import sqlite3
from pathlib import Path
import importlib.util


def run_all_migrations(conn: sqlite3.Connection) -> None:
    """
    Run all pending migrations in order.

    Args:
        conn: SQLite database connection
    """
    migrations_dir = Path(__file__).parent
    migration_files = sorted(migrations_dir.glob("0*.py"))

    for migration_file in migration_files:
        migration_name = migration_file.stem

        # Load migration module dynamically
        spec = importlib.util.spec_from_file_location(migration_name, migration_file)
        if not spec or not spec.loader:
            continue

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Run upgrade function
        if hasattr(module, "upgrade"):
            module.upgrade(conn)
