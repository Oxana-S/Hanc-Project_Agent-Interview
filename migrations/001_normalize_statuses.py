"""
Migration 001: Normalize phantom 'processing' status to 'reviewing'.

The 'processing' status was used in code but never added to VALID_STATUSES,
creating a phantom status that bypassed validation. This migration normalizes
all 'processing' sessions to 'reviewing', which is semantically equivalent
(both indicate the agent is finalizing the anketa).
"""

import sqlite3


def upgrade(conn: sqlite3.Connection) -> None:
    """
    Migrate sessions with status='processing' to status='reviewing'.

    Args:
        conn: SQLite database connection
    """
    cursor = conn.execute(
        "UPDATE sessions SET status = 'reviewing' WHERE status = 'processing'"
    )
    count = cursor.rowcount
    conn.commit()

    if count > 0:
        print(f"✅ Migration 001: Migrated {count} sessions from 'processing' to 'reviewing'")
    else:
        print("✅ Migration 001: No sessions with 'processing' status found")


def downgrade(conn: sqlite3.Connection) -> None:
    """
    Rollback not needed - 'processing' and 'reviewing' are semantically equivalent.
    """
    pass
