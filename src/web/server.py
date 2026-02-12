"""
FastAPI web server for Hanc.AI Voice Consultant.

Serves the consultation frontend from public/ and provides REST API
for session lifecycle, anketa polling/editing, and session confirmation.

Endpoints:
    Pages:
        GET  /                              - Main consultation page
        GET  /session/{link}                - Returning client page (by unique link)

    API - Sessions:
        POST /api/session/create            - Create new consultation session
        GET  /api/session/by-link/{link}    - Get session by unique link (resumption)
        GET  /api/session/{session_id}      - Get full session data
        GET  /api/session/{session_id}/anketa - Get anketa data (for polling)
        PUT  /api/session/{session_id}/anketa - Update anketa (client edits)
        POST /api/session/{session_id}/confirm - Confirm anketa
        POST /api/session/{session_id}/end  - End active session
        POST /api/session/{session_id}/kill - Force-kill session + LiveKit room

    API - Rooms:
        GET    /api/rooms                   - List active LiveKit rooms
        DELETE /api/rooms                   - Delete all active LiveKit rooms

    Static:
        /*                                  - Static files from public/
"""

import asyncio
import os
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.logging_config import setup_logging

setup_logging("server")

import structlog

from livekit.api import (
    LiveKitAPI,
    CreateRoomRequest,
    DeleteRoomRequest,
    ListRoomsRequest,
    RoomAgentDispatch,
    CreateAgentDispatchRequest,
)
from livekit.protocol.room import UpdateRoomMetadataRequest
from src.session.manager import SessionManager

logger = structlog.get_logger("server")
livekit_log = structlog.get_logger("livekit")
session_log = structlog.get_logger("session")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Hanc.AI Voice Consultant")

# Singleton session manager
session_mgr = SessionManager()


# ---------------------------------------------------------------------------
# Startup: clean stale LiveKit rooms
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def _cleanup_stale_rooms():
    """Delete old LiveKit rooms left from previous server runs."""
    try:
        lk_api = LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        result = await lk_api.room.list_rooms(ListRoomsRequest())
        count = 0
        for r in result.rooms:
            try:
                await lk_api.room.delete_room(DeleteRoomRequest(room=r.name))
                count += 1
                logger.info("startup_cleanup_room", room=r.name)
            except Exception:
                pass
        await lk_api.aclose()
        if count:
            logger.info("startup_cleanup_done", deleted=count)
        else:
            logger.info("startup_no_stale_rooms")
    except Exception as exc:
        logger.warning("startup_cleanup_failed", error=str(exc))

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    """Request body for creating a new consultation session."""
    pattern: str = "interaction"
    voice_settings: Optional[dict] = None  # e.g. {"silence_duration_ms": 3000}


class CreateSessionResponse(BaseModel):
    """Response body after a session is created."""
    session_id: str
    unique_link: str
    room_name: str
    livekit_url: str
    user_token: str


class UpdateAnketaRequest(BaseModel):
    """Request body for updating anketa data."""
    anketa_data: Optional[dict] = None
    anketa_md: Optional[str] = None


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/")
async def index():
    """Serve main consultation page."""
    return FileResponse("public/index.html")


@app.get("/session/{link}")
async def session_page(link: str):
    """Serve consultation page for returning clients."""
    session = session_mgr.get_session_by_link(link)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return FileResponse("public/index.html")


@app.get("/session/{link}/review")
async def session_review_page(link: str):
    """Serve review page for completed sessions (SPA handles rendering)."""
    session = session_mgr.get_session_by_link(link)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return FileResponse("public/index.html")


# ---------------------------------------------------------------------------
# API: Sessions
# ---------------------------------------------------------------------------


@app.get("/api/sessions")
async def list_sessions(status: str = None, limit: int = 50, offset: int = 0):
    """List all sessions (lightweight summaries for dashboard)."""
    sessions = session_mgr.list_sessions_summary(status, limit, offset)
    return {"sessions": sessions, "total": len(sessions)}


@app.post("/api/sessions/delete")
async def delete_sessions(req: dict):
    """Delete sessions by IDs. Also deletes associated LiveKit rooms."""
    session_ids = req.get("session_ids", [])
    if not session_ids:
        return {"deleted": 0}

    # Delete LiveKit rooms for each session
    rooms_deleted = 0
    try:
        lk_api = LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        for sid in session_ids:
            room_name = f"consultation-{sid}"
            try:
                await lk_api.room.delete_room(DeleteRoomRequest(room=room_name))
                rooms_deleted += 1
            except Exception:
                pass  # room may not exist
        await lk_api.aclose()
    except Exception as e:
        livekit_log.warning("bulk_room_delete_failed", error=str(e))

    deleted = session_mgr.delete_sessions(session_ids)
    session_log.info("sessions_bulk_deleted", deleted=deleted, rooms_deleted=rooms_deleted)
    return {"deleted": deleted, "rooms_deleted": rooms_deleted}


@app.post("/api/session/create", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest):
    """Create a new consultation session.

    Generates a session with a unique link, sets up a LiveKit room name,
    creates the room with agent dispatch, and returns a user token for
    WebRTC connection.
    """
    logger.info("=== SESSION CREATE START ===", pattern=req.pattern)

    # Step 1: Create DB session
    session = session_mgr.create_session(voice_config=req.voice_settings)
    room_name = f"consultation-{session.session_id}"
    session.room_name = room_name
    session_mgr.update_session(session)
    session_log.info(
        "STEP 1/4: DB session created",
        session_id=session.session_id,
        room_name=room_name,
        unique_link=session.unique_link,
    )

    # Step 2: Generate LiveKit token for the user
    livekit_url = os.getenv("LIVEKIT_URL", "")
    user_token = ""
    try:
        from src.voice.livekit_client import LiveKitClient
        lk = LiveKitClient()
        user_token = lk.create_token(room_name, f"client-{session.session_id}")
        livekit_log.info(
            "STEP 2/4: LiveKit token generated",
            livekit_url=livekit_url,
            token_length=len(user_token),
            participant=f"client-{session.session_id}",
        )
    except Exception as exc:
        livekit_log.error(
            "STEP 2/4 FAILED: LiveKit token generation error",
            error=str(exc),
            error_type=type(exc).__name__,
        )

    # Step 3: Create LiveKit room
    try:
        lk_api = LiveKitAPI(
            url=livekit_url,
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        livekit_log.info(
            "STEP 3/4: Creating LiveKit room...",
            room_name=room_name,
            livekit_url=livekit_url,
            api_key_present=bool(os.getenv("LIVEKIT_API_KEY")),
        )
        room_result = await lk_api.room.create_room(
            CreateRoomRequest(
                name=room_name,
                empty_timeout=300,
            )
        )
        livekit_log.info(
            "STEP 3/4: LiveKit room created",
            room_name=room_name,
            room_sid=getattr(room_result, "sid", "unknown"),
        )
    except Exception as exc:
        livekit_log.error(
            "STEP 3/4 FAILED: LiveKit room creation error",
            error=str(exc),
            error_type=type(exc).__name__,
            room_name=room_name,
        )
        lk_api = None

    # Step 4: Dispatch agent to the room
    if lk_api:
        try:
            livekit_log.info(
                "STEP 4/4: Dispatching agent to room...",
                room_name=room_name,
            )
            dispatch_result = await lk_api.agent_dispatch.create_dispatch(
                CreateAgentDispatchRequest(
                    room=room_name,
                    agent_name="hanc-consultant",  # Must match WorkerOptions.agent_name
                )
            )
            livekit_log.info(
                "STEP 4/4: Agent dispatched",
                room_name=room_name,
                dispatch_id=getattr(dispatch_result, "dispatch_id", "unknown"),
            )
        except Exception as exc:
            livekit_log.error(
                "STEP 4/4 FAILED: Agent dispatch error",
                error=str(exc),
                error_type=type(exc).__name__,
                room_name=room_name,
            )
        finally:
            await lk_api.aclose()

    logger.info(
        "=== SESSION CREATE DONE ===",
        session_id=session.session_id,
        room_name=room_name,
        token_ok=bool(user_token),
    )

    return CreateSessionResponse(
        session_id=session.session_id,
        unique_link=session.unique_link,
        room_name=room_name,
        livekit_url=livekit_url,
        user_token=user_token,
    )


@app.get("/api/session/by-link/{link}")
async def get_session_by_link(link: str):
    """Get session data by unique link (for session resumption from URL)."""
    session = session_mgr.get_session_by_link(link)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session_log.info("session_by_link", link=link, session_id=session.session_id)
    return session.model_dump()


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Get full session data by session_id."""
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump()


@app.get("/api/session/{session_id}/anketa")
async def get_anketa(session_id: str):
    """Get anketa data for a session (polled by frontend every ~2s)."""
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Calculate completion_rate from anketa_data
    completion_rate = 0.0
    if session.anketa_data:
        try:
            from src.anketa.schema import FinalAnketa, InterviewAnketa

            # Detect anketa type
            anketa_type = session.anketa_data.get('anketa_type')
            if anketa_type == 'interview':
                anketa = InterviewAnketa(**session.anketa_data)
            else:
                anketa = FinalAnketa(**session.anketa_data)

            completion_rate = anketa.completion_rate()
        except Exception as e:
            logger.warning("completion_rate_calc_failed", error=str(e), session_id=session_id)

    return {
        "anketa_data": session.anketa_data,
        "anketa_md": session.anketa_md,
        "status": session.status,
        "company_name": session.company_name,
        "updated_at": session.updated_at.isoformat(),
        "completion_rate": completion_rate,
    }


@app.put("/api/session/{session_id}/voice-config")
async def update_voice_config(session_id: str, req: dict):
    """Update voice_config for an existing session (e.g. speech_speed, silence_duration_ms).

    After saving to DB, signals the running agent to re-read the config
    by updating room metadata. This avoids calling /reconnect which can
    accidentally recreate rooms and dispatch duplicate agents.
    """
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.voice_config = req
    session_mgr.update_session(session)
    session_log.info("voice_config_updated", session_id=session_id, voice_config=req)

    # Signal running agent to re-read voice_config via room metadata
    room_name = session.room_name or f"consultation-{session_id}"
    try:
        import json, time
        lk_api = LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        await lk_api.room.update_room_metadata(
            UpdateRoomMetadataRequest(
                room=room_name,
                metadata=json.dumps({"config_version": time.time()}),
            )
        )
        await lk_api.aclose()
        livekit_log.info("voice_config_signal_sent", room=room_name)
    except Exception as e:
        livekit_log.debug("voice_config_signal_skipped", room=room_name, error=str(e))

    return {"ok": True}


@app.get("/api/session/{session_id}/reconnect")
async def reconnect_session(session_id: str):
    """Get new LiveKit token to reconnect to an existing session room.

    Used when the user reloads the page and needs to rejoin the room.
    If the room no longer exists, creates a new one with agent dispatch.
    Also resumes paused sessions by setting status back to active.
    """
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Resume paused sessions
    if session.status == "paused":
        session_mgr.update_status(session_id, "active")
        session_log.info("session_resumed", session_id=session_id)

    room_name = session.room_name or f"consultation-{session_id}"
    livekit_url = os.getenv("LIVEKIT_URL", "")

    # Generate a new token for this room
    try:
        from src.voice.livekit_client import LiveKitClient
        lk = LiveKitClient()
        user_token = lk.create_token(room_name, f"client-{session_id}")
    except Exception as exc:
        livekit_log.error("reconnect_token_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to generate token")

    # Check if room still exists; if not, recreate + dispatch agent
    try:
        lk_api = LiveKitAPI(
            url=livekit_url,
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        result = await lk_api.room.list_rooms(ListRoomsRequest())
        room_exists = any(r.name == room_name for r in result.rooms)

        if not room_exists:
            livekit_log.info("reconnect_room_not_found_recreating", room=room_name)
            await lk_api.room.create_room(
                CreateRoomRequest(name=room_name, empty_timeout=300)
            )
            await lk_api.agent_dispatch.create_dispatch(
                CreateAgentDispatchRequest(room=room_name, agent_name="hanc-consultant")
            )
        else:
            # Signal running agent to re-read voice_config from DB.
            # Updates room metadata which triggers "room_metadata_changed" event
            # on the agent, so it picks up changed speech_speed / silence / voice.
            import json, time
            try:
                await lk_api.room.update_room_metadata(
                    UpdateRoomMetadataRequest(
                        room=room_name,
                        metadata=json.dumps({"config_version": time.time()}),
                    )
                )
                livekit_log.info("reconnect_metadata_signal_sent", room=room_name)
            except Exception as meta_exc:
                livekit_log.warning("reconnect_metadata_signal_failed", error=str(meta_exc))

        await lk_api.aclose()
    except Exception as exc:
        livekit_log.warning("reconnect_room_check_failed", error=str(exc))

    session_log.info(
        "session_reconnect",
        session_id=session_id,
        room_name=room_name,
        room_existed=room_exists if 'room_exists' in dir() else "unknown",
    )
    return {
        "room_name": room_name,
        "livekit_url": livekit_url,
        "user_token": user_token,
    }


@app.put("/api/session/{session_id}/anketa")
async def update_anketa(session_id: str, req: UpdateAnketaRequest):
    """Update anketa data (client edits from the frontend)."""
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if req.anketa_data:
        session_mgr.update_anketa(session_id, req.anketa_data, req.anketa_md)
    logger.info("anketa_updated_by_client", session_id=session_id)
    return {"status": "ok"}


@app.post("/api/session/{session_id}/confirm")
async def confirm_session(session_id: str):
    """Confirm the anketa - marks session as confirmed."""
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_mgr.update_status(session_id, "confirmed")
    session_log.info("session_confirmed", session_id=session_id)

    # Trigger notifications in background
    try:
        from src.notifications import NotificationManager
        notifier = NotificationManager()
        asyncio.create_task(notifier.on_session_confirmed(session))
    except Exception as e:
        logger.warning("notification_trigger_failed", error=str(e))

    return {"status": "confirmed"}


@app.post("/api/session/{session_id}/end")
async def end_session(session_id: str):
    """End an active session - marks it as paused."""
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_mgr.update_status(session_id, "paused")
    session_log.info(
        "session_ended",
        session_id=session_id,
        duration=session.duration_seconds,
        messages=len(session.dialogue_history),
    )
    return {
        "status": "paused",
        "duration": session.duration_seconds,
        "message_count": len(session.dialogue_history),
        "unique_link": session.unique_link,
    }


@app.post("/api/session/{session_id}/kill")
async def kill_session(session_id: str):
    """Force-kill session: delete LiveKit room and mark as declined."""
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    room_name = session.room_name or f"consultation-{session_id}"
    room_deleted = False

    try:
        lk_api = LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        await lk_api.room.delete_room(DeleteRoomRequest(room=room_name))
        room_deleted = True
        livekit_log.info("room_deleted", room=room_name)
        await lk_api.aclose()
    except Exception as e:
        livekit_log.warning("room_delete_failed", room=room_name, error=str(e))

    session_mgr.update_status(session_id, "declined")
    session_log.info("session_killed", session_id=session_id, room_deleted=room_deleted)

    return {
        "status": "killed",
        "room_deleted": room_deleted,
        "room_name": room_name,
    }


@app.get("/api/session/{session_id}/export/{format}")
async def export_session(session_id: str, format: str):
    """Export session anketa in the requested format (md or pdf/print-html)."""
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    anketa_md = session.anketa_md
    company_name = session.company_name
    voice_config = session.voice_config if session.voice_config else {}
    session_type = voice_config.get("consultation_type", "consultation")

    if format == "md":
        from src.anketa.exporter import export_markdown

        content, filename = export_markdown(anketa_md or "", company_name or "")
        session_log.info("session_exported", session_id=session_id, format="md")
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    elif format == "pdf":
        from src.anketa.exporter import export_print_html

        content, filename = export_print_html(
            anketa_md or "", company_name or "", session_type
        )
        session_log.info("session_exported", session_id=session_id, format="pdf")
        return Response(
            content=content,
            media_type="text/html",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported export format: {format}. Supported: md, pdf",
        )


# ---------------------------------------------------------------------------
# API: Agent health check
# ---------------------------------------------------------------------------


def _check_agent_alive() -> tuple:
    """Check if voice agent worker is running. Uses PID file + pgrep fallback."""
    import subprocess

    # Method 1: PID file
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pid_file = os.path.join(_project_root, ".agent.pid")
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True, pid
        except (OSError, ValueError):
            pass

    # Method 2: pgrep fallback (PID file may not exist)
    try:
        result = subprocess.run(
            ["pgrep", "-f", "run_voice_agent.py"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            pid = int(result.stdout.strip().split('\n')[0])
            return True, pid
    except (subprocess.TimeoutExpired, ValueError):
        pass

    return False, None


@app.get("/api/agent/health")
async def agent_health():
    """Check if a voice agent worker process is alive."""
    alive, pid = _check_agent_alive()
    return {"worker_alive": alive, "worker_pid": pid}


# ---------------------------------------------------------------------------
# API: LLM Providers
# ---------------------------------------------------------------------------


@app.get("/api/llm/providers")
async def llm_providers():
    """Return available LLM providers (those with API keys configured)."""
    from src.llm.factory import get_available_providers
    return get_available_providers()


# ---------------------------------------------------------------------------
# API: LiveKit Rooms
# ---------------------------------------------------------------------------


@app.get("/api/rooms")
async def list_rooms():
    """List all active LiveKit rooms."""
    lk_api = LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
    )
    result = await lk_api.room.list_rooms(ListRoomsRequest())
    await lk_api.aclose()

    rooms = [
        {
            "name": r.name,
            "sid": r.sid,
            "participants": r.num_participants,
            "created_at": r.creation_time,
        }
        for r in result.rooms
    ]
    return {"rooms": rooms, "count": len(rooms)}


@app.delete("/api/rooms")
async def cleanup_all_rooms():
    """Delete ALL active LiveKit rooms."""
    lk_api = LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
    )
    result = await lk_api.room.list_rooms(ListRoomsRequest())
    deleted = []
    for r in result.rooms:
        try:
            await lk_api.room.delete_room(DeleteRoomRequest(room=r.name))
            deleted.append(r.name)
            livekit_log.info("room_cleanup_deleted", room=r.name)
        except Exception as e:
            livekit_log.warning("room_cleanup_failed", room=r.name, error=str(e))
    await lk_api.aclose()

    logger.info("rooms_cleanup_done", deleted_count=len(deleted))
    return {"deleted": deleted, "count": len(deleted)}


# ---------------------------------------------------------------------------
# API: Document Upload
# ---------------------------------------------------------------------------

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILES_PER_SESSION = 5
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md"}


@app.post("/api/session/{session_id}/documents/upload")
async def upload_documents(
    session_id: str,
    files: List[UploadFile] = File(...),
):
    """Upload documents for analysis during consultation.

    Parses uploaded files (PDF, DOCX, XLSX, TXT, MD), analyzes them
    with LLM, stores DocumentContext in the session, and triggers
    immediate anketa extraction enriched with document data.
    """
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if len(files) > MAX_FILES_PER_SESSION:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_FILES_PER_SESSION} files per session",
        )

    # Save uploaded files to data/uploads/{session_id}/
    upload_dir = Path("data/uploads") / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    from src.documents import DocumentParser, DocumentAnalyzer

    parser = DocumentParser()
    parsed_docs = []
    saved_files = []

    for file in files:
        # Validate extension
        ext = Path(file.filename or "").suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            )

        # Read and validate size
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File {file.filename} exceeds {MAX_FILE_SIZE // (1024*1024)}MB limit",
            )

        # Save to disk
        file_path = upload_dir / file.filename
        file_path.write_bytes(content)
        saved_files.append(file.filename)

        # Parse
        doc = parser.parse(file_path)
        if doc:
            parsed_docs.append(doc)
            logger.info("document_parsed", filename=file.filename, chunks=len(doc.chunks))
        else:
            logger.warning("document_parse_failed", filename=file.filename)

    if not parsed_docs:
        raise HTTPException(status_code=400, detail="No documents could be parsed")

    # Analyze with LLM
    analyzer = DocumentAnalyzer()
    doc_context = await analyzer.analyze(parsed_docs)

    # Store in session
    context_dict = doc_context.model_dump(mode="json")
    # Remove heavy chunks from storage (keep summary + extracted info only)
    for doc_data in context_dict.get("documents", []):
        doc_data.pop("chunks", None)
    session_mgr.update_document_context(session_id, context_dict)

    logger.info(
        "documents_uploaded_and_analyzed",
        session_id=session_id,
        files=saved_files,
        key_facts=len(doc_context.key_facts),
        services=len(doc_context.services_mentioned),
    )

    # v4.3: Notify running agent via LiveKit room metadata
    try:
        room_name = f"consultation-{session_id}"
        lk_api = LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        import json as _json
        metadata = _json.dumps({
            "document_context_updated": True,
            "document_count": len(parsed_docs),
            "key_facts_count": len(doc_context.key_facts),
        })
        await lk_api.room.update_room_metadata(
            UpdateRoomMetadataRequest(room=room_name, metadata=metadata)
        )
        logger.info("agent_notified_about_documents", session_id=session_id, room=room_name)
    except Exception as e:
        logger.warning("failed_to_notify_agent_about_documents", error=str(e), session_id=session_id)

    # Trigger immediate anketa extraction with document context
    task = asyncio.create_task(
        _extract_anketa_with_documents(session_id, doc_context)
    )
    task.add_done_callback(lambda t: t.result() if not t.cancelled() and not t.exception() else None)

    return {
        "status": "success",
        "documents": saved_files,
        "document_count": len(parsed_docs),
        "summary": doc_context.summary,
        "key_facts": doc_context.key_facts[:5],
        "services": doc_context.services_mentioned[:10],
    }


async def _extract_anketa_with_documents(session_id: str, doc_context):
    """Background task: extract anketa enriched with document data."""
    try:
        session = session_mgr.get_session(session_id)
        if not session:
            return

        from src.anketa import AnketaExtractor, AnketaGenerator
        from src.llm.factory import create_llm_client

        _llm_provider = None
        if session.voice_config:
            _llm_provider = session.voice_config.get("llm_provider")
        extractor = AnketaExtractor(create_llm_client(_llm_provider))
        anketa = await extractor.extract(
            dialogue_history=session.dialogue_history or [],
            duration_seconds=session.duration_seconds,
            document_context=doc_context,
        )

        anketa_data = anketa.model_dump(mode="json")
        anketa_md = AnketaGenerator.render_markdown(anketa)
        session_mgr.update_anketa(session_id, anketa_data, anketa_md)

        if anketa.company_name or anketa.contact_name:
            session_mgr.update_metadata(
                session_id,
                company_name=anketa.company_name,
                contact_name=anketa.contact_name,
            )

        logger.info(
            "document_anketa_extracted",
            session_id=session_id,
            company=anketa.company_name,
            completion=f"{anketa.completion_rate():.0f}%",
        )
    except Exception as e:
        logger.warning("document_anketa_extraction_failed", session_id=session_id, error=str(e))


# ---------------------------------------------------------------------------
# Analytics & Learnings (PostgreSQL)
# ---------------------------------------------------------------------------

_pg_mgr = None


def _try_get_postgres():
    """Lazy-init PostgreSQL connection (fail-safe)."""
    global _pg_mgr
    if _pg_mgr is not None:
        return _pg_mgr
    pg_url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    if pg_url:
        try:
            from src.storage.postgres import PostgreSQLStorageManager
            _pg_mgr = PostgreSQLStorageManager(pg_url)
            return _pg_mgr
        except Exception:
            pass
    return None


@app.get("/api/statistics")
async def get_statistics():
    """Статистика по всем сессиям и отраслям."""
    pg_mgr = _try_get_postgres()
    if not pg_mgr:
        raise HTTPException(status_code=503, detail="PostgreSQL not configured")
    stats = await pg_mgr.get_statistics()
    return stats.model_dump()


@app.get("/api/learnings")
async def get_learnings(industry_id: Optional[str] = None, limit: int = 50):
    """Learnings по отраслям."""
    pg_mgr = _try_get_postgres()
    if not pg_mgr:
        raise HTTPException(status_code=503, detail="PostgreSQL not configured")
    learnings = await pg_mgr.get_learnings(industry_id=industry_id, limit=limit)
    return {"learnings": learnings, "count": len(learnings)}


# ---------------------------------------------------------------------------
# Static files - mounted AFTER API routes so API paths take priority
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory="public"), name="static")
