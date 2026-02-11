"""
Functional test for all 3 databases: SQLite, Redis, PostgreSQL.

Tests real CRUD operations against live database instances.
Run: ./venv/bin/python tests/test_db_functional.py
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env
from dotenv import load_dotenv
load_dotenv()


# ============================================================
# COLORS
# ============================================================

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
NC = "\033[0m"

passed = 0
failed = 0
errors = []


def ok(msg: str):
    global passed
    passed += 1
    print(f"  {GREEN}PASS{NC}  {msg}")


def fail(msg: str, detail: str = ""):
    global failed
    failed += 1
    errors.append(f"{msg}: {detail}")
    print(f"  {RED}FAIL{NC}  {msg}")
    if detail:
        print(f"        {detail}")


def section(name: str):
    print(f"\n{BOLD}{'=' * 60}{NC}")
    print(f"{BOLD}  {name}{NC}")
    print(f"{BOLD}{'=' * 60}{NC}\n")


# ============================================================
# 1. SQLite — SessionManager
# ============================================================

def test_sqlite():
    section("1. SQLite — SessionManager")

    from src.session.manager import SessionManager

    # Use temp DB to avoid polluting real data
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_sessions.db")
        mgr = SessionManager(db_path=db_path)

        # 1.1 Create session
        try:
            session = mgr.create_session(room_name="test-room-001")
            assert session.session_id, "session_id must not be empty"
            assert session.room_name == "test-room-001"
            assert session.status == "active"
            assert session.unique_link
            ok(f"CREATE session (id={session.session_id})")
        except Exception as e:
            fail("CREATE session", str(e))
            return

        sid = session.session_id

        # 1.2 Read session
        try:
            loaded = mgr.get_session(sid)
            assert loaded is not None, "Session not found"
            assert loaded.session_id == sid
            assert loaded.room_name == "test-room-001"
            assert loaded.status == "active"
            ok(f"READ session by id")
        except Exception as e:
            fail("READ session by id", str(e))

        # 1.3 Read by unique_link
        try:
            loaded_link = mgr.get_session_by_link(session.unique_link)
            assert loaded_link is not None, "Session not found by link"
            assert loaded_link.session_id == sid
            ok("READ session by unique_link")
        except Exception as e:
            fail("READ session by unique_link", str(e))

        # 1.4 Update anketa
        try:
            anketa_data = {
                "company_name": "TestCorp",
                "industry": "IT",
                "business_description": "Testing databases"
            }
            result = mgr.update_anketa(sid, anketa_data, anketa_md="# TestCorp\n\nIT company")
            assert result is True, "update_anketa returned False"
            reloaded = mgr.get_session(sid)
            assert reloaded.anketa_data["company_name"] == "TestCorp"
            assert reloaded.anketa_md == "# TestCorp\n\nIT company"
            ok("UPDATE anketa")
        except Exception as e:
            fail("UPDATE anketa", str(e))

        # 1.5 Update status
        try:
            result = mgr.update_status(sid, "reviewing")
            assert result is True
            reloaded = mgr.get_session(sid)
            assert reloaded.status == "reviewing"
            ok("UPDATE status → reviewing")
        except Exception as e:
            fail("UPDATE status", str(e))

        # 1.6 Update metadata
        try:
            result = mgr.update_metadata(sid, company_name="TestCorp Ltd", contact_name="Ivan")
            assert result is True
            reloaded = mgr.get_session(sid)
            assert reloaded.company_name == "TestCorp Ltd"
            assert reloaded.contact_name == "Ivan"
            ok("UPDATE metadata (company_name + contact_name)")
        except Exception as e:
            fail("UPDATE metadata", str(e))

        # 1.7 Update dialogue
        try:
            dialogue = [
                {"role": "assistant", "content": "Hello!"},
                {"role": "user", "content": "Hi, I need a voice agent"}
            ]
            result = mgr.update_dialogue(sid, dialogue, duration_seconds=45.5)
            assert result is True
            reloaded = mgr.get_session(sid)
            assert len(reloaded.dialogue_history) == 2
            assert reloaded.duration_seconds == 45.5
            ok("UPDATE dialogue (2 messages, 45.5s)")
        except Exception as e:
            fail("UPDATE dialogue", str(e))

        # 1.8 Update document_context
        try:
            doc_ctx = {"files": ["brief.md"], "summary": "Test brief"}
            result = mgr.update_document_context(sid, doc_ctx)
            assert result is True
            reloaded = mgr.get_session(sid)
            assert reloaded.document_context["files"] == ["brief.md"]
            ok("UPDATE document_context")
        except Exception as e:
            fail("UPDATE document_context", str(e))

        # 1.9 Create second session for list test
        try:
            session2 = mgr.create_session(room_name="test-room-002")
            mgr.update_status(session2.session_id, "confirmed")
            ok(f"CREATE second session (id={session2.session_id})")
        except Exception as e:
            fail("CREATE second session", str(e))
            session2 = None

        # 1.10 List all sessions
        try:
            all_sessions = mgr.list_sessions()
            assert len(all_sessions) == 2, f"Expected 2 sessions, got {len(all_sessions)}"
            ok(f"LIST all sessions (count={len(all_sessions)})")
        except Exception as e:
            fail("LIST all sessions", str(e))

        # 1.11 List by status
        try:
            reviewing = mgr.list_sessions(status="reviewing")
            assert len(reviewing) == 1
            assert reviewing[0].session_id == sid
            ok("LIST sessions by status=reviewing")
        except Exception as e:
            fail("LIST sessions by status", str(e))

        # 1.12 List summary
        try:
            summary = mgr.list_sessions_summary()
            assert len(summary) == 2
            assert summary[0]["session_id"] in [sid, session2.session_id if session2 else ""]
            ok("LIST sessions_summary")
        except Exception as e:
            fail("LIST sessions_summary", str(e))

        # 1.13 Full update_session
        try:
            full = mgr.get_session(sid)
            full.status = "confirmed"
            full.duration_seconds = 120.0
            result = mgr.update_session(full)
            assert result is True
            reloaded = mgr.get_session(sid)
            assert reloaded.status == "confirmed"
            assert reloaded.duration_seconds == 120.0
            ok("UPDATE full session object")
        except Exception as e:
            fail("UPDATE full session", str(e))

        # 1.14 Invalid status
        try:
            mgr.update_status(sid, "INVALID_STATUS")
            fail("Invalid status should raise ValueError")
        except ValueError:
            ok("REJECT invalid status (ValueError raised)")
        except Exception as e:
            fail("REJECT invalid status", str(e))

        # 1.15 Delete sessions
        try:
            ids_to_delete = [sid]
            if session2:
                ids_to_delete.append(session2.session_id)
            count = mgr.delete_sessions(ids_to_delete)
            assert count == len(ids_to_delete), f"Deleted {count}, expected {len(ids_to_delete)}"
            remaining = mgr.list_sessions()
            assert len(remaining) == 0, f"Expected 0, got {len(remaining)}"
            ok(f"DELETE {count} sessions, verified empty")
        except Exception as e:
            fail("DELETE sessions", str(e))

        # 1.16 Read nonexistent session
        try:
            gone = mgr.get_session(sid)
            assert gone is None, "Deleted session should return None"
            ok("READ deleted session → None")
        except Exception as e:
            fail("READ deleted session", str(e))

        mgr.close()
        ok("CLOSE SessionManager")


# ============================================================
# 2. Redis — RedisStorageManager
# ============================================================

async def test_redis():
    section("2. Redis — RedisStorageManager")

    try:
        from src.storage.redis import RedisStorageManager
        from src.models import InterviewContext, InterviewPattern, InterviewStatus
    except ImportError as e:
        fail("Import RedisStorageManager", str(e))
        return

    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", 6379))
    password = os.getenv("REDIS_PASSWORD")
    db = int(os.getenv("REDIS_DB", 0))

    try:
        mgr = RedisStorageManager(host=host, port=port, password=password, db=db, session_ttl=60)
    except Exception as e:
        fail("Connect to Redis", str(e))
        return

    # 2.1 Health check
    try:
        healthy = mgr.health_check()
        assert healthy is True, "Redis health check failed"
        ok("Health check → True")
    except Exception as e:
        fail("Health check", str(e))
        return

    # Create test context
    test_session_id = f"dbtest-{str(uuid4())[:8]}"
    test_interview_id = str(uuid4())

    context = InterviewContext(
        session_id=test_session_id,
        interview_id=test_interview_id,
        pattern=InterviewPattern.INTERACTION,
        status=InterviewStatus.IN_PROGRESS,
        total_questions=10,
        answered_questions=3,
        total_duration_seconds=45.0,
        livekit_room_name="test-room-redis",
    )

    # 2.2 Save context
    try:
        result = await mgr.save_context(context)
        assert result is True, "save_context returned False"
        ok(f"SAVE context (session={test_session_id})")
    except Exception as e:
        fail("SAVE context", str(e))
        return

    # 2.3 Load context
    try:
        loaded = await mgr.load_context(test_session_id)
        assert loaded is not None, "Context not found"
        assert loaded.session_id == test_session_id
        assert loaded.interview_id == test_interview_id
        assert loaded.pattern == InterviewPattern.INTERACTION
        assert loaded.answered_questions == 3
        assert loaded.livekit_room_name == "test-room-redis"
        ok("LOAD context — all fields match")
    except Exception as e:
        fail("LOAD context", str(e))

    # 2.4 Check TTL
    try:
        key = mgr._get_key(test_session_id)
        ttl = mgr.client.ttl(key)
        assert 0 < ttl <= 60, f"TTL should be 0-60, got {ttl}"
        ok(f"TTL check → {ttl}s (expected ≤60)")
    except Exception as e:
        fail("TTL check", str(e))

    # 2.5 Get all active sessions
    try:
        active = await mgr.get_all_active_sessions()
        assert test_session_id in active, f"Test session not in active list"
        ok(f"GET all active sessions (found test session among {len(active)})")
    except Exception as e:
        fail("GET all active sessions", str(e))

    # 2.6 Update context
    try:
        context.answered_questions = 7
        context.status = InterviewStatus.COMPLETED
        result = await mgr.update_context(context)
        assert result is True
        reloaded = await mgr.load_context(test_session_id)
        assert reloaded.answered_questions == 7
        assert reloaded.status == InterviewStatus.COMPLETED
        ok("UPDATE context (answered=7, status=completed)")
    except Exception as e:
        fail("UPDATE context", str(e))

    # 2.7 Extend TTL
    try:
        result = await mgr.extend_ttl(test_session_id, additional_seconds=120)
        assert result is True
        new_ttl = mgr.client.ttl(key)
        assert new_ttl > 60, f"Extended TTL should be > 60, got {new_ttl}"
        ok(f"EXTEND TTL → {new_ttl}s")
    except Exception as e:
        fail("EXTEND TTL", str(e))

    # 2.8 Get session info
    try:
        info = await mgr.get_session_info(test_session_id)
        assert info is not None
        assert info["session_id"] == test_session_id
        assert info["progress_percentage"] == 70.0  # 7/10 * 100
        ok(f"GET session info (progress={info['progress_percentage']}%)")
    except Exception as e:
        fail("GET session info", str(e))

    # 2.9 Delete context
    try:
        result = await mgr.delete_context(test_session_id)
        assert result is True
        gone = await mgr.load_context(test_session_id)
        assert gone is None, "Deleted context should return None"
        ok("DELETE context — verified gone")
    except Exception as e:
        fail("DELETE context", str(e))

    # 2.10 Delete nonexistent
    try:
        result = await mgr.delete_context("nonexistent-session-xyz")
        assert result is False, "Delete of nonexistent should return False"
        ok("DELETE nonexistent → False")
    except Exception as e:
        fail("DELETE nonexistent", str(e))

    # 2.11 Extend TTL on nonexistent
    try:
        result = await mgr.extend_ttl("nonexistent-session-xyz")
        assert result is False
        ok("EXTEND TTL nonexistent → False")
    except Exception as e:
        fail("EXTEND TTL nonexistent", str(e))


# ============================================================
# 3. PostgreSQL — PostgreSQLStorageManager
# ============================================================

async def test_postgres():
    section("3. PostgreSQL — PostgreSQLStorageManager")

    try:
        from src.storage.postgres import PostgreSQLStorageManager
        from src.models import InterviewPattern, InterviewStatistics
        from src.anketa.schema import FinalAnketa, AgentFunction
    except ImportError as e:
        fail("Import PostgreSQLStorageManager", str(e))
        return

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Build from components
        pg_host = os.getenv("POSTGRES_HOST", "localhost")
        pg_port = os.getenv("POSTGRES_PORT", "5432")
        pg_db = os.getenv("POSTGRES_DB", "voice_interviewer")
        pg_user = os.getenv("POSTGRES_USER", "interviewer_user")
        pg_pass = os.getenv("POSTGRES_PASSWORD", "")
        db_url = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"

    try:
        mgr = PostgreSQLStorageManager(database_url=db_url)
    except Exception as e:
        fail("Connect to PostgreSQL", str(e))
        return

    # 3.1 Health check
    try:
        healthy = mgr.health_check()
        assert healthy is True, "PostgreSQL health check failed"
        ok("Health check → True")
    except Exception as e:
        fail("Health check", str(e))
        return

    # Test data IDs (unique to avoid conflicts)
    test_session_id = f"pgtest-{str(uuid4())[:8]}"
    test_interview_id = str(uuid4())
    test_anketa_id = str(uuid4())

    # 3.2 Save interview session
    try:
        result = await mgr.save_interview_session(
            session_id=test_session_id,
            interview_id=test_interview_id,
            pattern=InterviewPattern.INTERACTION,
            status="active",
            metadata={"source": "db_test", "test": True}
        )
        assert result is True, "save_interview_session returned False"
        ok(f"SAVE interview_session (id={test_session_id})")
    except Exception as e:
        fail("SAVE interview_session", str(e))
        return

    # 3.3 Update interview session
    try:
        result = await mgr.update_interview_session(
            session_id=test_session_id,
            completed_at=datetime.now(),
            duration=185.5,
            questions_asked=12,
            questions_answered=10,
            clarifications=3,
            completeness_score=0.85,
            status="completed"
        )
        assert result is True
        ok("UPDATE interview_session (completed, 185.5s, 10/12 questions)")
    except Exception as e:
        fail("UPDATE interview_session", str(e))

    # 3.4 Save anketa
    try:
        anketa = FinalAnketa(
            anketa_id=test_anketa_id,
            interview_id=test_interview_id,
            pattern="interaction",
            company_name="DBTest Corp",
            industry="Technology",
            business_description="Testing PostgreSQL storage",
            services=["Voice agents", "Chatbots"],
            agent_name="TestBot",
            agent_purpose="Handle customer calls",
            agent_functions=[
                AgentFunction(name="Greet", description="Greet the customer", priority="high")
            ],
        )
        result = await mgr.save_anketa(anketa)
        assert result is True, "save_anketa returned False"
        ok(f"SAVE anketa (id={test_anketa_id}, company=DBTest Corp)")
    except Exception as e:
        fail("SAVE anketa", str(e))
        return

    # 3.5 Get anketa by ID
    try:
        loaded = await mgr.get_anketa(test_anketa_id)
        assert loaded is not None, "Anketa not found"
        assert loaded.anketa_id == test_anketa_id
        assert loaded.company_name == "DBTest Corp"
        assert loaded.industry == "Technology"
        assert loaded.business_description == "Testing PostgreSQL storage"
        assert len(loaded.services) == 2
        assert loaded.agent_name == "TestBot"
        assert len(loaded.agent_functions) == 1
        assert loaded.agent_functions[0].name == "Greet"
        ok("GET anketa by ID — all fields match")
    except Exception as e:
        fail("GET anketa by ID", str(e))

    # 3.6 Get anketas by company
    try:
        by_company = await mgr.get_anketas_by_company("DBTest")
        assert len(by_company) >= 1, f"Expected >= 1 anketas, got {len(by_company)}"
        assert any(a.anketa_id == test_anketa_id for a in by_company)
        ok(f"GET anketas by company 'DBTest' (found {len(by_company)})")
    except Exception as e:
        fail("GET anketas by company", str(e))

    # 3.7 Get statistics
    try:
        stats = await mgr.get_statistics()
        assert stats.total_interviews >= 1
        assert stats.completed_interviews >= 1
        ok(f"GET statistics (total={stats.total_interviews}, completed={stats.completed_interviews})")
    except Exception as e:
        fail("GET statistics", str(e))

    # 3.8 Update nonexistent session
    try:
        result = await mgr.update_interview_session(
            session_id="nonexistent-session-xyz",
            status="completed"
        )
        assert result is False, "Update nonexistent should return False"
        ok("UPDATE nonexistent session → False")
    except Exception as e:
        fail("UPDATE nonexistent session", str(e))

    # 3.9 Get nonexistent anketa
    try:
        gone = await mgr.get_anketa("nonexistent-anketa-xyz")
        assert gone is None
        ok("GET nonexistent anketa → None")
    except Exception as e:
        fail("GET nonexistent anketa", str(e))

    # 3.10 Cleanup test data
    try:
        db_session = mgr._get_session()
        from src.storage.postgres import AnketaDB, InterviewSessionDB

        db_session.query(AnketaDB).filter(AnketaDB.anketa_id == test_anketa_id).delete()
        db_session.query(InterviewSessionDB).filter(
            InterviewSessionDB.session_id == test_session_id
        ).delete()
        db_session.commit()
        db_session.close()

        # Verify cleanup
        verify_anketa = await mgr.get_anketa(test_anketa_id)
        assert verify_anketa is None, "Anketa should be deleted"
        ok("CLEANUP test data — verified deleted")
    except Exception as e:
        fail("CLEANUP test data", str(e))


# ============================================================
# 4. Cross-DB: SessionManager → Real data/sessions.db
# ============================================================

def test_sqlite_real_db():
    section("4. SQLite — Real DB connection (data/sessions.db)")

    from src.session.manager import SessionManager

    db_path = "data/sessions.db"

    try:
        mgr = SessionManager(db_path=db_path)
        ok(f"CONNECT to real DB ({db_path})")
    except Exception as e:
        fail(f"CONNECT to real DB", str(e))
        return

    # Create, verify, delete — leave no trace
    try:
        session = mgr.create_session(room_name="functional-test-room")
        sid = session.session_id
        loaded = mgr.get_session(sid)
        assert loaded is not None
        count = mgr.delete_sessions([sid])
        assert count == 1
        verify = mgr.get_session(sid)
        assert verify is None
        ok(f"CREATE → READ → DELETE on real DB (no trace left)")
    except Exception as e:
        fail("CRUD on real DB", str(e))

    mgr.close()


# ============================================================
# MAIN
# ============================================================

async def main():
    print(f"\n{BOLD}{'=' * 60}{NC}")
    print(f"{BOLD}  Hanc.AI — Database Functional Tests{NC}")
    print(f"{BOLD}  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{NC}")
    print(f"{BOLD}{'=' * 60}{NC}")

    # 1. SQLite (temp DB)
    test_sqlite()

    # 2. Redis
    await test_redis()

    # 3. PostgreSQL
    await test_postgres()

    # 4. SQLite real DB
    test_sqlite_real_db()

    # Summary
    section("SUMMARY")
    total = passed + failed
    print(f"  Total:   {total}")
    print(f"  {GREEN}Passed:  {passed}{NC}")
    if failed:
        print(f"  {RED}Failed:  {failed}{NC}")
        print(f"\n  {RED}Failures:{NC}")
        for err in errors:
            print(f"    - {err}")
    else:
        print(f"  Failed:  0")

    print()
    if failed == 0:
        print(f"  {GREEN}{BOLD}ALL TESTS PASSED{NC}")
    else:
        print(f"  {RED}{BOLD}{failed} TEST(S) FAILED{NC}")

    print()
    return 1 if failed else 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
