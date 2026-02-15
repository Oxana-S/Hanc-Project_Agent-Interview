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
import uuid as _uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

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
from src.session.models import SessionStatus
from src.session.exceptions import InvalidTransitionError

import re as _re

# R5-09: Session ID format pattern (hex UUID prefix)
_SESSION_ID_RE = _re.compile(r'^[a-f0-9]{8}$')
# R9-01: UUID format for unique_link parameter
_UUID_RE = _re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')


def _validate_session_id(session_id: str):
    """Validate session_id format to prevent path traversal."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id format")


def _safe_content_disposition(disposition: str, filename: str) -> str:
    """Build a Content-Disposition header safe for non-ASCII filenames (RFC 5987)."""
    from urllib.parse import quote
    # R18-01: Sanitize CRLF to prevent header injection
    filename = filename.replace("\r", "").replace("\n", "").replace("\x00", "")
    # ASCII-only fallback: strip non-ASCII chars
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "export"
    # UTF-8 encoded version for modern browsers
    utf8_name = quote(filename, safe="")
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"


logger = structlog.get_logger("server")
livekit_log = structlog.get_logger("livekit")
session_log = structlog.get_logger("session")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(application: FastAPI):
    """Combined startup/shutdown lifecycle (replaces deprecated on_event)."""
    import time

    # --- Startup ---
    # 1. Validate config
    required = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.error("missing_required_env_vars", vars=missing)
        logger.warning("Server will start but LiveKit features will be unavailable")

    # 2. Clean stale LiveKit rooms
    lk_api = None
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
        if count:
            logger.info("startup_cleanup_done", deleted=count)
        else:
            logger.info("startup_no_stale_rooms")
    except Exception as exc:
        logger.warning("startup_cleanup_failed", error=str(exc))
    finally:
        if lk_api:
            await lk_api.aclose()

    # 3. Start runtime status cleanup loop
    # R17-03: Track cleanup task for graceful cancellation on shutdown
    _cleanup_task = None

    async def _cleanup_loop():
        try:
            while True:
                await asyncio.sleep(300)  # 5 minutes
                now = time.time()
                stale = [k for k, v in dict(_runtime_statuses).items() if now - v.get("updated_at", 0) > 3600]
                for k in stale:
                    _runtime_statuses.pop(k, None)
                if stale:
                    logger.debug("runtime_statuses_cleaned", evicted=len(stale))
        except asyncio.CancelledError:
            pass  # Graceful shutdown

    _cleanup_task = asyncio.create_task(_cleanup_loop())
    _track_task(_cleanup_task)

    yield  # --- App running ---

    # --- Shutdown ---
    # R17-03: Cancel cleanup loop before closing other resources
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    try:
        session_mgr.close()
        logger.info("session_manager_closed")
    except Exception as e:
        logger.warning("shutdown_close_failed", error=str(e))
    try:
        from src.voice.consultant import _shared_http_client
        if _shared_http_client and not _shared_http_client.is_closed:
            await _shared_http_client.aclose()
    except Exception:
        pass
    logger.info("server_shutdown_complete")


app = FastAPI(title="Hanc.AI Voice Consultant", lifespan=_lifespan)


# R4-23: Request ID middleware for distributed tracing
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(_uuid.uuid4())[:12]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


_SESSION_FIXED_ROUTES = {"create", "by-link"}


class SessionIDValidationMiddleware(BaseHTTPMiddleware):
    """R7-01: Validate session_id in all /api/session/{id} paths."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Match /api/session/{session_id} but not /api/sessions or fixed sub-routes
        if path.startswith("/api/session/") and not path.startswith("/api/sessions"):
            parts = path.split("/")
            if len(parts) >= 4:
                sid = parts[3]
                # Skip fixed routes that are not session IDs
                if sid and sid not in _SESSION_FIXED_ROUTES and not _SESSION_ID_RE.match(sid):
                    from starlette.responses import JSONResponse
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Invalid session_id format"},
                    )
        return await call_next(request)


app.add_middleware(RequestIDMiddleware)
app.add_middleware(SessionIDValidationMiddleware)


# R15-05: Security headers middleware (defense-in-depth)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # R26-01: Content-Security-Policy to mitigate XSS and CDN compromise
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://unpkg.com; "
            "connect-src 'self' wss: https:; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "frame-ancestors 'none'"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)

# Singleton session manager
session_mgr = SessionManager()

# In-memory runtime status cache (ephemeral, not persisted)
# Maps session_id -> {"runtime_status": "idle"|"processing"|"completing"|"completed"|"error", "updated_at": float}
_runtime_statuses: dict = {}


# R5-20: Background task reference set (prevent GC of fire-and-forget tasks)
_background_tasks: set = set()


def _track_task(task):
    """Keep a reference to a background task to prevent GC."""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    """Request body for creating a new consultation session."""
    pattern: str = Field(default="interaction", pattern=r"^(interaction|management)$")  # R15-04
    voice_settings: Optional[dict] = None  # e.g. {"silence_duration_ms": 3000}


class CreateSessionResponse(BaseModel):
    """Response body after a session is created."""
    session_id: str
    unique_link: str
    room_name: str
    livekit_url: str
    user_token: str
    warning: Optional[str] = None  # R4-04: Non-null when LiveKit setup had issues


class UpdateAnketaRequest(BaseModel):
    """Request body for updating anketa data."""
    anketa_data: Optional[dict] = Field(default=None)
    anketa_md: Optional[str] = Field(default=None, max_length=100000)

    @field_validator('anketa_data')
    @classmethod
    def cap_dict_keys(cls, v):
        """R23-05: Pydantic v2 ignores max_length on dict; validate explicitly."""
        if v is not None and len(v) > 200:
            raise ValueError(f"anketa_data has {len(v)} keys, max 200")
        return v


class UpdateDialogueRequest(BaseModel):
    """Request body for updating dialogue history from voice agent."""
    dialogue_history: list = Field(max_length=500)  # R15-01: Cap to prevent memory exhaustion
    duration_seconds: float = Field(ge=0, le=86400)  # Max 24 hours
    status: Optional[str] = None  # Must be a valid SessionStatus value


class UpdateRuntimeStatusRequest(BaseModel):
    """R20-11: Request body for updating ephemeral runtime status."""
    runtime_status: str = Field(pattern=r"^(idle|processing|completing|completed|error)$")


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
    # R9-01: Validate unique_link format (UUID)
    if not _UUID_RE.match(link):
        raise HTTPException(status_code=400, detail="Invalid link format")
    session = session_mgr.get_session_by_link(link)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return FileResponse("public/index.html")


@app.get("/session/{link}/review")
async def session_review_page(link: str):
    """Serve review page for completed sessions (SPA handles rendering)."""
    # R9-01: Validate unique_link format (UUID)
    if not _UUID_RE.match(link):
        raise HTTPException(status_code=400, detail="Invalid link format")
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
    limit = min(max(limit, 1), 200)  # R4-20: bound limit param
    offset = max(offset, 0)
    # R11-09: Validate status parameter
    if status is not None:
        from src.session.models import VALID_STATUSES
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {sorted(VALID_STATUSES)}")
    sessions, total_count = session_mgr.list_sessions_summary(status, limit, offset)
    return {"sessions": sessions, "total": total_count}


class DeleteSessionsRequest(BaseModel):
    session_ids: List[str] = Field(default_factory=list, max_length=100)


@app.post("/api/sessions/delete")
async def delete_sessions(req: DeleteSessionsRequest):
    """Delete sessions by IDs. Also deletes associated LiveKit rooms."""
    if not req.session_ids:
        return {"deleted": 0}

    # R9-02: Validate each session_id format in the body
    for sid in req.session_ids:
        if not _SESSION_ID_RE.match(sid):
            raise HTTPException(status_code=400, detail=f"Invalid session_id format: {sid}")

    # Delete LiveKit rooms for each session
    rooms_deleted = 0
    lk_api = None
    try:
        lk_api = LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        for sid in req.session_ids:
            room_name = f"consultation-{sid}"
            try:
                await lk_api.room.delete_room(DeleteRoomRequest(room=room_name))
                rooms_deleted += 1
            except Exception:
                pass  # room may not exist
    except Exception as e:
        livekit_log.warning("bulk_room_delete_failed", error=str(e))
    finally:
        if lk_api:
            await lk_api.aclose()

    # R4-32: cleanup runtime statuses for deleted sessions
    for sid in req.session_ids:
        _runtime_statuses.pop(sid, None)

    # R9-08: Cleanup uploaded files for deleted sessions
    import shutil
    for sid in req.session_ids:
        upload_dir = Path("data/uploads") / sid
        if upload_dir.exists():
            try:
                shutil.rmtree(upload_dir)
            except Exception as e:
                logger.warning("upload_cleanup_failed", session_id=sid, error=str(e))

    deleted = session_mgr.delete_sessions(req.session_ids)
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
    lk_api = None  # R11-18: Initialize before try to prevent UnboundLocalError
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
        # R9-11: Close lk_api before nullifying to prevent resource leak
        if lk_api:
            try:
                await lk_api.aclose()
            except Exception:
                pass
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

    # R4-04: Warn frontend if voice setup had issues
    warning = None
    if not user_token:
        warning = "Voice connection unavailable: failed to generate LiveKit token"
    elif not lk_api:
        warning = "Voice room creation failed — agent may not connect automatically"

    logger.info(
        "=== SESSION CREATE DONE ===",
        session_id=session.session_id,
        room_name=room_name,
        token_ok=bool(user_token),
        warning=warning,
    )

    return CreateSessionResponse(
        session_id=session.session_id,
        unique_link=session.unique_link,
        room_name=room_name,
        livekit_url=livekit_url,
        user_token=user_token,
        warning=warning,
    )


@app.get("/api/session/by-link/{link}")
async def get_session_by_link(link: str):
    """Get session data by unique link (for session resumption from URL)."""
    # R9-01: Validate unique_link format (UUID)
    if not _UUID_RE.match(link):
        raise HTTPException(status_code=400, detail="Invalid link format")
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

    # Include ephemeral runtime_status if available
    rt = _runtime_statuses.get(session_id, {})

    return {
        "anketa_data": session.anketa_data,
        "anketa_md": session.anketa_md,
        "status": session.status,
        "runtime_status": rt.get("runtime_status", "idle"),
        "company_name": session.company_name,
        "updated_at": session.updated_at.isoformat(),
        "completion_rate": completion_rate,
    }


@app.put("/api/session/{session_id}/runtime-status")
async def update_runtime_status(session_id: str, req: UpdateRuntimeStatusRequest):
    """Update ephemeral runtime status (called by voice agent process).

    Valid values: idle, processing, completing, completed, error
    """
    import time
    status = req.runtime_status  # R20-11: Validated by Pydantic model
    # R15-02: Verify session exists before caching runtime status (prevents cache pollution)
    if session_id not in _runtime_statuses:
        # R26-07: Check cap BEFORE DB lookup to prevent wasted queries
        if len(_runtime_statuses) > 5000:
            raise HTTPException(status_code=503, detail="Runtime status cache full")
        if not session_mgr.get_session(session_id):
            raise HTTPException(status_code=404, detail="Session not found")
    _runtime_statuses[session_id] = {"runtime_status": status, "updated_at": time.time()}
    return {"ok": True}


ALLOWED_VOICE_CONFIG_KEYS = {
    "consultation_type", "voice_gender", "voice_tone", "language",
    "speech_speed", "silence_duration_ms", "llm_provider", "verbosity",
}

# R20-07: Type validators for voice_config values (prevent type confusion in downstream)
_VOICE_CONFIG_VALIDATORS = {
    "speech_speed": lambda v: isinstance(v, (int, float)) and 0.5 <= v <= 2.0,
    "silence_duration_ms": lambda v: isinstance(v, (int, float)) and 300 <= v <= 10000,
    "voice_gender": lambda v: isinstance(v, str) and v in ("male", "female", "neutral"),
    "voice_tone": lambda v: isinstance(v, str) and len(v) <= 50,
    "language": lambda v: isinstance(v, str) and len(v) <= 10,
    "verbosity": lambda v: isinstance(v, str) and v in ("concise", "normal", "verbose"),
    "llm_provider": lambda v: isinstance(v, str) and v in ("deepseek", "azure", "openai", "anthropic", "xai"),
    "consultation_type": lambda v: isinstance(v, str) and v in ("consultation", "interaction", "management", "interview"),
}


@app.put("/api/session/{session_id}/voice-config")
async def update_voice_config(session_id: str, req: dict):
    """Update voice_config for an existing session (e.g. speech_speed, silence_duration_ms).

    After saving to DB, signals the running agent to re-read the config
    by updating room metadata. This avoids calling /reconnect which can
    accidentally recreate rooms and dispatch duplicate agents.
    """
    # R14-06: Use atomic update_voice_config to prevent full-session overwrite race
    # R6-13: Filter to allowed keys (preserves consultation_type, llm_provider)
    filtered = {k: v for k, v in req.items() if k in ALLOWED_VOICE_CONFIG_KEYS}
    # R20-07: Validate value types to prevent type confusion in downstream consumers
    for key, value in list(filtered.items()):
        validator = _VOICE_CONFIG_VALIDATORS.get(key)
        if validator and not validator(value):
            raise HTTPException(status_code=400, detail=f"Invalid value for {key}")
    if not session_mgr.update_voice_config(session_id, filtered):
        raise HTTPException(status_code=404, detail="Session not found")
    session_log.info("voice_config_updated", session_id=session_id, voice_config=filtered)

    # Signal running agent to re-read voice_config via room metadata
    # R15-BUG: Fetch session for room_name (removed by R14-06 refactor)
    session = session_mgr.get_session(session_id)
    room_name = (session.room_name if session else None) or f"consultation-{session_id}"
    lk_api = None
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
        livekit_log.info("voice_config_signal_sent", room=room_name)
    except Exception as e:
        livekit_log.debug("voice_config_signal_skipped", room=room_name, error=str(e))
    finally:
        if lk_api:
            await lk_api.aclose()

    return {"ok": True}


@app.get("/api/session/{session_id}/reconnect")
async def reconnect_session(session_id: str):
    """Get new LiveKit token to reconnect to an existing session room (idempotent).

    Used when the user reloads the page and needs to rejoin the room.
    If the room no longer exists, creates a new one with agent dispatch.
    Does NOT change session status - use POST /resume to resume paused sessions.
    """
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # REMOVED: session_mgr.update_status() — GET должен быть idempotent

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
    room_exists = None  # R4-06: initialize before try block
    lk_api = None
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

    except Exception as exc:
        livekit_log.warning("reconnect_room_check_failed", error=str(exc))
    finally:
        if lk_api:
            await lk_api.aclose()

    session_log.info(
        "session_reconnect",
        session_id=session_id,
        room_name=room_name,
        room_existed=room_exists,
    )
    return {
        "room_name": room_name,
        "livekit_url": livekit_url,
        "user_token": user_token,
    }


@app.post("/api/session/{session_id}/pause")
async def pause_session(session_id: str):
    """Pause an active session - changes status to 'paused'."""
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != SessionStatus.ACTIVE.value:
        raise HTTPException(status_code=400, detail="Session is not active")

    try:
        session_mgr.update_status(session_id, SessionStatus.PAUSED)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session_log.info("session_paused", session_id=session_id)
    return {"status": SessionStatus.PAUSED.value, "message": "Session paused"}


@app.post("/api/session/{session_id}/resume")
async def resume_session(session_id: str):
    """Resume paused session - changes status to 'active'.

    This is a separate POST endpoint to avoid GET side effects.
    Frontend should call this when user explicitly clicks Resume button.
    """
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != SessionStatus.PAUSED.value:
        raise HTTPException(status_code=400, detail="Session is not paused")

    try:
        session_mgr.update_status(session_id, SessionStatus.ACTIVE)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session_log.info("session_resumed", session_id=session_id)

    return {"status": SessionStatus.ACTIVE.value, "message": "Session resumed"}


@app.put("/api/session/{session_id}/anketa")
@app.post("/api/session/{session_id}/anketa")  # POST for sendBeacon compatibility
async def update_anketa(session_id: str, req: UpdateAnketaRequest):
    """Update anketa data (client edits from the frontend).

    Supports both PUT (normal fetch) and POST (sendBeacon on tab close).
    """
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if req.anketa_data:
        session_mgr.update_anketa(session_id, req.anketa_data, req.anketa_md)
    logger.info("anketa_updated_by_client", session_id=session_id)
    return {"status": "ok"}


@app.put("/api/session/{session_id}/dialogue")
async def update_dialogue(session_id: str, req: UpdateDialogueRequest):
    """Update dialogue history from voice agent process (avoids SQLite WAL isolation)."""
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # R15-12: Single authority for status validation — let manager.py handle it
    # (removes TOCTOU gap from double validation in server + manager)
    session_mgr.update_dialogue(
        session_id,
        dialogue_history=req.dialogue_history,
        duration_seconds=req.duration_seconds,
        status=req.status,
    )
    logger.info(
        "dialogue_updated_via_api",
        session_id=session_id,
        messages=len(req.dialogue_history),
        duration=req.duration_seconds,
        status_updated=req.status,
    )
    return {"status": "ok", "messages": len(req.dialogue_history)}


@app.post("/api/session/{session_id}/confirm")
async def confirm_session(session_id: str):
    """Confirm the anketa - marks session as confirmed."""
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        session_mgr.update_status(session_id, SessionStatus.CONFIRMED)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    _runtime_statuses.pop(session_id, None)  # R4-32: cleanup on terminal state
    session_log.info("session_confirmed", session_id=session_id)

    # R17-15: Re-read session after status update so notification gets fresh state
    fresh_session = session_mgr.get_session(session_id) or session

    # Trigger notifications in background
    try:
        from src.notifications import NotificationManager
        notifier = NotificationManager()
        _track_task(asyncio.create_task(notifier.on_session_confirmed(fresh_session)))
    except Exception as e:
        logger.warning("notification_trigger_failed", error=str(e))

    return {"status": SessionStatus.CONFIRMED.value}


@app.post("/api/session/{session_id}/end")
async def end_session(session_id: str):
    """End an active session - marks it as paused."""
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        session_mgr.update_status(session_id, SessionStatus.PAUSED)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session_log.info(
        "session_ended",
        session_id=session_id,
        duration=session.duration_seconds,
        messages=len(session.dialogue_history),
    )
    return {
        "status": SessionStatus.PAUSED.value,
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

    lk_api = None
    try:
        lk_api = LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        await lk_api.room.delete_room(DeleteRoomRequest(room=room_name))
        room_deleted = True
        livekit_log.info("room_deleted", room=room_name)
    except Exception as e:
        livekit_log.warning("room_delete_failed", room=room_name, error=str(e))
    finally:
        if lk_api:
            await lk_api.aclose()

    try:
        session_mgr.update_status(session_id, SessionStatus.DECLINED)
    except InvalidTransitionError as e:
        # Kill is admin override - use force=True
        session_mgr.update_status(session_id, SessionStatus.DECLINED, force=True)

    _runtime_statuses.pop(session_id, None)  # R4-32: cleanup on terminal state
    session_log.info("session_killed", session_id=session_id, room_deleted=room_deleted)

    return {
        "status": "killed",
        "room_deleted": room_deleted,
        "room_name": room_name,
    }


@app.post("/api/session/{session_id}/reconnect")
async def reconnect_session_post(session_id: str):
    """
    Reconnect to a paused session - generates fresh LiveKit token.
    Only works for sessions with status='paused' or 'active'.
    """
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Validate session can be resumed (only paused or active)
    if session.status not in [SessionStatus.PAUSED.value, SessionStatus.ACTIVE.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reconnect: session status is '{session.status}'. Only 'paused' or 'active' sessions can be resumed."
        )

    room_name = session.room_name or f"consultation-{session_id}"

    # Generate fresh LiveKit token
    try:
        from src.voice.livekit_client import LiveKitClient
        lk = LiveKitClient()
        user_token = lk.create_token(room_name, f"client-{session.session_id}")
        livekit_log.info(
            "session_reconnect_token_generated",
            session_id=session_id,
            room=room_name,
            token_length=len(user_token),
        )
    except Exception as exc:
        livekit_log.error(
            "session_reconnect_token_failed",
            session_id=session_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to generate LiveKit token"  # R9-14: Don't expose internal error
        )

    # Update session status to 'active' via state machine
    if session.status == SessionStatus.PAUSED.value:
        try:
            session_mgr.update_status(session_id, SessionStatus.ACTIVE)
        except InvalidTransitionError as e:
            raise HTTPException(status_code=400, detail=str(e))

    session_log.info(
        "session_reconnected",
        session_id=session_id,
        room=room_name,
        previous_status=session.status,
    )

    return {
        "token": user_token,
        "room_name": room_name,
        "livekit_url": os.getenv("LIVEKIT_URL", ""),
        "session_id": session_id,
        "status": "active",
    }


@app.get("/api/session/{session_id}/export/{export_format}")
async def export_session(session_id: str, export_format: str):
    """Export session anketa in the requested format (md or pdf/print-html)."""
    # R11-20: Whitelist validation first (don't reflect user input in error)
    if export_format not in ("md", "pdf"):
        raise HTTPException(status_code=400, detail="Unsupported export format. Supported: md, pdf")

    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    anketa_md = session.anketa_md
    company_name = session.company_name
    voice_config = session.voice_config if session.voice_config else {}
    session_type = voice_config.get("consultation_type", "consultation")

    if export_format == "md":
        from src.anketa.exporter import export_markdown

        content, filename = export_markdown(anketa_md or "", company_name or "")
        session_log.info("session_exported", session_id=session_id, format="md")
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": _safe_content_disposition("attachment", filename)},
        )

    else:  # pdf
        from src.anketa.exporter import export_print_html

        content, filename = export_print_html(
            anketa_md or "", company_name or "", session_type
        )
        session_log.info("session_exported", session_id=session_id, format="pdf")
        return Response(
            content=content,
            media_type="text/html",
            headers={"Content-Disposition": _safe_content_disposition("inline", filename)},
        )


# ---------------------------------------------------------------------------
# API: Agent health check
# ---------------------------------------------------------------------------


async def _check_agent_alive() -> tuple:
    """Check if voice agent worker is running. Uses PID file + async pgrep fallback."""
    # Method 1: PID file (os.kill is non-blocking — just sends signal 0)
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pid_file = os.path.join(_project_root, ".agent.pid")
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            if pid <= 0 or pid > 4194304:
                raise ValueError("Invalid PID")
            os.kill(pid, 0)
            return True, pid
        except (OSError, ValueError):
            pass

    # Method 2: async pgrep fallback (P1.4: non-blocking subprocess)
    try:
        proc = await asyncio.create_subprocess_exec(
            "pgrep", "-f", "run_voice_agent.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        if proc.returncode == 0 and stdout.strip():
            pid = int(stdout.decode().strip().split('\n')[0])
            return True, pid
    except (asyncio.TimeoutError, ValueError):
        pass

    return False, None


@app.get("/api/agent/health")
async def agent_health():
    """Check if a voice agent worker process is alive."""
    alive, pid = await _check_agent_alive()
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
    try:
        result = await lk_api.room.list_rooms(ListRoomsRequest())
    finally:
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
    try:
        result = await lk_api.room.list_rooms(ListRoomsRequest())
        deleted = []
        for r in result.rooms:
            try:
                await lk_api.room.delete_room(DeleteRoomRequest(room=r.name))
                deleted.append(r.name)
                livekit_log.info("room_cleanup_deleted", room=r.name)
            except Exception as e:
                livekit_log.warning("room_cleanup_failed", room=r.name, error=str(e))
    finally:
        await lk_api.aclose()

    logger.info("rooms_cleanup_done", deleted_count=len(deleted))
    return {"deleted": deleted, "count": len(deleted)}


# ---------------------------------------------------------------------------
# API: Document Upload
# ---------------------------------------------------------------------------

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILES_PER_SESSION = 5
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md"}
# R5-08: Allowed MIME types per extension (content_type validation)
_ALLOWED_MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".xls": {"application/vnd.ms-excel"},
    ".txt": {"text/plain"},
    ".md": {"text/plain", "text/markdown"},
}


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
    _validate_session_id(session_id)  # R5-09: prevent path traversal
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

    # R9-07: Check total accumulated files (not just current batch)
    existing_files = list(upload_dir.glob("*"))
    if len(existing_files) + len(files) > MAX_FILES_PER_SESSION:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_FILES_PER_SESSION} files per session (already have {len(existing_files)})",
        )

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

        # R5-08: Validate MIME content type
        allowed_mimes = _ALLOWED_MIME_TYPES.get(ext, set())
        if file.content_type and allowed_mimes and file.content_type not in allowed_mimes:
            # Allow application/octet-stream as fallback (some browsers send it)
            if file.content_type != "application/octet-stream":
                raise HTTPException(
                    status_code=400,
                    detail=f"MIME type '{file.content_type}' not allowed for {ext}",
                )

        # Read and validate size
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File {file.filename} exceeds {MAX_FILE_SIZE // (1024*1024)}MB limit",
            )

        # Save to disk (sanitize filename to prevent path traversal)
        safe_name = Path(file.filename or "upload").name  # strips directory components
        if not safe_name or safe_name.startswith("."):
            safe_name = f"upload_{len(saved_files)}{ext}"
        # R8-02: Deduplicate filenames to prevent race condition overwrites
        file_path = upload_dir / safe_name
        if file_path.exists():
            stem = Path(safe_name).stem
            suffix = Path(safe_name).suffix
            counter = 1
            while file_path.exists() and counter < 100:
                file_path = upload_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            if file_path.exists():
                raise HTTPException(status_code=409, detail="Too many filename collisions")
            safe_name = file_path.name
        file_path.write_bytes(content)
        saved_files.append(safe_name)

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
    try:
        doc_context = await analyzer.analyze(parsed_docs)
    except Exception as exc:
        logger.error("document_analysis_failed", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Document analysis failed")

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
    lk_api = None
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
    finally:
        if lk_api:
            await lk_api.aclose()

    # Trigger immediate anketa extraction with document context
    task = asyncio.create_task(
        _extract_anketa_with_documents(session_id, doc_context)
    )
    _track_task(task)
    def _log_bg_task_error(t):
        if not t.cancelled() and t.exception():
            logger.error("background_extraction_failed", error=str(t.exception()))
    task.add_done_callback(_log_bg_task_error)

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
            completion=f"{anketa.completion_rate():.0%}",
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
    limit = min(max(limit, 1), 200)  # R9-05: bound limit param
    pg_mgr = _try_get_postgres()
    if not pg_mgr:
        raise HTTPException(status_code=503, detail="PostgreSQL not configured")
    learnings = await pg_mgr.get_learnings(industry_id=industry_id, limit=limit)
    return {"learnings": learnings, "count": len(learnings)}


# ---------------------------------------------------------------------------
# Static files - mounted AFTER API routes so API paths take priority
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory="public"), name="static")
