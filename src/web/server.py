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

    Static:
        /*                                  - Static files from public/
"""

import asyncio
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.logging_config import setup_logging

setup_logging("server")

import structlog

from livekit.api import LiveKitAPI, CreateRoomRequest, RoomAgentDispatch, CreateAgentDispatchRequest
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
# Pydantic request / response models
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    """Request body for creating a new consultation session."""
    pattern: str = "interaction"


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
    """Serve consultation page for returning clients.

    Verifies that the unique link exists, then serves the same index page.
    The JS frontend reads session data from the API using the link.
    """
    session = session_mgr.get_session_by_link(link)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return FileResponse("public/index.html")


# ---------------------------------------------------------------------------
# API: Sessions
# ---------------------------------------------------------------------------


@app.post("/api/session/create", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest):
    """Create a new consultation session.

    Generates a session with a unique link, sets up a LiveKit room name,
    creates the room with agent dispatch, and returns a user token for
    WebRTC connection.
    """
    logger.info("=== SESSION CREATE START ===", pattern=req.pattern)

    # Step 1: Create DB session
    session = session_mgr.create_session()
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
    return {
        "anketa_data": session.anketa_data,
        "anketa_md": session.anketa_md,
        "status": session.status,
        "company_name": session.company_name,
        "updated_at": session.updated_at.isoformat(),
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


# ---------------------------------------------------------------------------
# Static files - mounted AFTER API routes so API paths take priority
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory="public"), name="static")
