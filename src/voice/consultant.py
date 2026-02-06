"""
VoiceConsultant - голосовой интерфейс для ConsultantInterviewer.

Связывает:
- LiveKit (WebRTC аудио)
- Azure OpenAI Realtime (STT/TTS)
- ConsultantInterviewer (логика диалога)

v1.1: Добавлена интеграция с AnketaExtractor и OutputManager.
После завершения разговора автоматически генерируется и сохраняется анкета.

v1.2: Интеграция с SessionManager.
- Извлечение session_id из имени комнаты (consultation-{session_id})
- Синхронизация диалога и анкеты в SQLite через SessionManager
- Периодическое извлечение анкеты каждые 6 сообщений для live-обновлений в UI
- Поддержка standalone режима (без web-сервера) — если db_session не найдена

v1.3: Подробное логирование для диагностики.
"""

import asyncio
import os
import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.logging_config import setup_logging

setup_logging("agent")

import structlog
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.agents.voice import Agent as VoiceAgent, AgentSession
from livekit.agents.voice.room_io import RoomInputOptions
from livekit.plugins import openai as lk_openai

from src.anketa import AnketaExtractor, AnketaGenerator
from src.config.prompt_loader import get_prompt
from src.llm.deepseek import DeepSeekClient
from src.knowledge import IndustryKnowledgeManager, EnrichedContextBuilder
from src.output import OutputManager
from src.session.manager import SessionManager

logger       = structlog.get_logger("agent")      # lifecycle, steps, ready
azure_log    = structlog.get_logger("azure")       # RealtimeModel, WSS
dialogue_log = structlog.get_logger("dialogue")    # DIALOGUE_MESSAGE
livekit_log  = structlog.get_logger("livekit")     # room connect, events
anketa_log   = structlog.get_logger("anketa")      # periodic extraction, finalize
session_log  = structlog.get_logger("session")     # DB lookup, sync


class VoiceConsultationSession:
    """Хранит состояние голосовой консультации."""

    def __init__(self, room_name: str = ""):
        self.session_id = str(uuid.uuid4())[:8]
        self.room_name = room_name
        self.start_time = datetime.now()
        self.dialogue_history: List[Dict[str, Any]] = []
        self.status = "active"  # active, completed, error

    def add_message(self, role: str, content: str):
        """Добавить сообщение в историю диалога."""
        self.dialogue_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "phase": "voice"  # Единая фаза для голосового режима
        })
        dialogue_log.info(
            "DIALOGUE_MESSAGE",
            role=role,
            preview=content[:80] if content else "",
            total_messages=len(self.dialogue_history),
            session_id=self.session_id,
        )

    def get_duration_seconds(self) -> float:
        """Получить длительность сессии в секундах."""
        return (datetime.now() - self.start_time).total_seconds()

    def get_company_name(self) -> str:
        """Попытаться извлечь название компании из диалога."""
        for msg in self.dialogue_history:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if "компания" in content.lower() or "называется" in content.lower():
                    return content[:50]
        return f"session_{self.session_id}"


async def finalize_consultation(consultation: VoiceConsultationSession):
    """
    Генерирует анкету и сохраняет результаты после завершения разговора.
    """
    anketa_log.info(
        "=== FINALIZE START ===",
        session_id=consultation.session_id,
        messages=len(consultation.dialogue_history),
        duration_seconds=consultation.get_duration_seconds()
    )

    if len(consultation.dialogue_history) < 2:
        anketa_log.info("FINALIZE: Not enough dialogue to generate anketa, skipping")
        consultation.status = "completed"
        return

    try:
        deepseek = DeepSeekClient()
        extractor = AnketaExtractor(deepseek)

        anketa = await extractor.extract(
            dialogue_history=consultation.dialogue_history,
            duration_seconds=consultation.get_duration_seconds()
        )

        company_name = anketa.company_name or consultation.get_company_name()
        anketa_log.info("FINALIZE: Anketa extracted", company=company_name)

        output_manager = OutputManager()
        company_dir = output_manager.get_company_dir(
            company_name,
            consultation.start_time
        )

        anketa_md = AnketaGenerator.render_markdown(anketa)
        anketa_json = anketa.model_dump()

        anketa_paths = output_manager.save_anketa(company_dir, anketa_md, anketa_json)

        dialogue_path = output_manager.save_dialogue(
            company_dir=company_dir,
            dialogue_history=consultation.dialogue_history,
            company_name=company_name,
            client_name=anketa.contact_name or "Клиент",
            duration_seconds=consultation.get_duration_seconds(),
            start_time=consultation.start_time
        )

        consultation.status = "completed"

        anketa_log.info(
            "=== FINALIZE DONE ===",
            session_id=consultation.session_id,
            output_dir=str(company_dir),
            anketa_md=str(anketa_paths["md"]),
            anketa_json=str(anketa_paths["json"]),
            dialogue=str(dialogue_path)
        )

    except Exception as e:
        consultation.status = "error"
        anketa_log.error(
            "=== FINALIZE FAILED ===",
            session_id=consultation.session_id,
            error=str(e),
            error_type=type(e).__name__,
            traceback=traceback.format_exc(),
        )


def get_system_prompt() -> str:
    """Получить системный промпт для голосового агента из YAML."""
    return get_prompt("voice/consultant", "system_prompt")


def get_enriched_system_prompt(dialogue_history: List[Dict[str, Any]]) -> str:
    """
    Get system prompt with industry context.

    Detects industry from dialogue and enriches prompt with
    relevant knowledge base information.

    Args:
        dialogue_history: Current dialogue history

    Returns:
        Enriched system prompt
    """
    base_prompt = get_system_prompt()

    # Need at least 2 messages to detect industry
    if len(dialogue_history) < 2:
        return base_prompt

    try:
        manager = IndustryKnowledgeManager()
        builder = EnrichedContextBuilder(manager)

        voice_context = builder.build_for_voice(dialogue_history)

        if voice_context:
            return f"{base_prompt}\n\n### Контекст отрасли:\n{voice_context}"
    except Exception as e:
        logger.warning("Failed to get enriched context", error=str(e))

    return base_prompt


def get_review_system_prompt(anketa_summary: str) -> str:
    """Get system prompt for review phase with current anketa data from YAML."""
    from src.config.prompt_loader import render_prompt
    return render_prompt("voice/review", "system_prompt", anketa_summary=anketa_summary)


def format_anketa_for_voice(anketa_data: dict) -> str:
    """Format anketa data as readable text for voice review."""
    sections = [
        ("Название компании", anketa_data.get("company_name")),
        ("Контактное лицо", anketa_data.get("contact_name")),
        ("Сфера деятельности", anketa_data.get("industry")),
        ("Услуги компании", anketa_data.get("services")),
        ("Текущие проблемы", anketa_data.get("current_problems")),
        ("Предлагаемые задачи для агента", anketa_data.get("proposed_tasks")),
        ("Интеграции", anketa_data.get("integrations")),
        ("Дополнительные заметки", anketa_data.get("notes")),
    ]

    lines: list[str] = []
    index = 1

    for label, value in sections:
        if not value:
            continue

        if isinstance(value, list):
            formatted_value = ", ".join(str(item) for item in value)
        else:
            formatted_value = str(value)

        lines.append(f"{index}. {label}: {formatted_value}")
        index += 1

    if not lines:
        return "(Анкета пока пуста)"

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SessionManager integration (shared DB with web server)
# ---------------------------------------------------------------------------

_session_mgr = SessionManager()


def _sync_to_db(consultation: VoiceConsultationSession, session_id: str):
    """Sync dialogue history and duration to the database."""
    session = _session_mgr.get_session(session_id)
    if session:
        session.dialogue_history = consultation.dialogue_history
        session.duration_seconds = consultation.get_duration_seconds()
        _session_mgr.update_session(session)


async def _extract_and_update_anketa(
    consultation: VoiceConsultationSession,
    session_id: str,
):
    """Extract anketa from current dialogue and update in DB."""
    try:
        if len(consultation.dialogue_history) < 4:
            return

        deepseek = DeepSeekClient()
        extractor = AnketaExtractor(deepseek)

        anketa = await extractor.extract(
            dialogue_history=consultation.dialogue_history,
            duration_seconds=consultation.get_duration_seconds(),
        )

        anketa_data = anketa.model_dump()
        anketa_md = AnketaGenerator.render_markdown(anketa)
        _session_mgr.update_anketa(session_id, anketa_data, anketa_md)

        if anketa.company_name or anketa.contact_name:
            session = _session_mgr.get_session(session_id)
            if session:
                if anketa.company_name:
                    session.company_name = anketa.company_name
                if anketa.contact_name:
                    session.contact_name = anketa.contact_name
                _session_mgr.update_session(session)

        anketa_log.info(
            "periodic_anketa_extracted",
            session_id=session_id,
            company=anketa.company_name,
        )

    except Exception as e:
        anketa_log.warning("periodic_anketa_extraction_failed", error=str(e))


async def _finalize_and_save(
    consultation: VoiceConsultationSession,
    session_id: Optional[str],
):
    """Final anketa extraction, filesystem save, and DB update."""
    await finalize_consultation(consultation)

    if not session_id:
        return

    session = _session_mgr.get_session(session_id)
    if not session:
        session_log.warning("finalize_session_not_found", session_id=session_id)
        return

    session.dialogue_history = consultation.dialogue_history
    session.duration_seconds = consultation.get_duration_seconds()
    session.status = "reviewing"

    if consultation.status == "completed":
        try:
            deepseek = DeepSeekClient()
            extractor = AnketaExtractor(deepseek)

            anketa = await extractor.extract(
                dialogue_history=consultation.dialogue_history,
                duration_seconds=consultation.get_duration_seconds(),
            )

            session.anketa_data = anketa.model_dump()
            session.anketa_md = AnketaGenerator.render_markdown(anketa)
            if anketa.company_name:
                session.company_name = anketa.company_name
            if anketa.contact_name:
                session.contact_name = anketa.contact_name

        except Exception as e:
            anketa_log.warning("final_anketa_extraction_failed", error=str(e))

    _session_mgr.update_session(session)
    session_log.info(
        "session_finalized_in_db",
        session_id=session_id,
        status=session.status,
    )


def _lookup_db_session(room_name: str):
    """Extract session_id from room name and look up the DB session."""
    session_log.info("AGENT: Looking up DB session", room_name=room_name)

    if not room_name.startswith("consultation-"):
        session_log.warning(
            "AGENT: Room name does not start with 'consultation-', standalone mode",
            room_name=room_name,
        )
        return None, None

    session_id = room_name.replace("consultation-", "", 1)
    db_session = _session_mgr.get_session(session_id)

    if db_session:
        session_log.info(
            "AGENT: DB session found",
            session_id=session_id,
            status=db_session.status,
            existing_messages=len(db_session.dialogue_history),
        )
    else:
        session_log.warning(
            "AGENT: DB session NOT FOUND - standalone mode",
            session_id=session_id,
        )

    return session_id, db_session


def _init_consultation(room_name: str, db_session) -> VoiceConsultationSession:
    """Create an in-memory consultation, optionally seeded from a DB session."""
    consultation = VoiceConsultationSession(room_name=room_name)
    if db_session:
        consultation.session_id = db_session.session_id
        consultation.dialogue_history = db_session.dialogue_history.copy()

    session_log.info(
        "AGENT: Consultation session initialized",
        session_id=consultation.session_id,
        room=room_name,
        db_backed=db_session is not None,
        existing_messages=len(consultation.dialogue_history),
    )
    return consultation


def _register_event_handlers(
    session: AgentSession,
    consultation: VoiceConsultationSession,
    session_id: Optional[str],
    db_backed: bool,
):
    """Register LiveKit AgentSession event handlers."""
    messages_since_last_extract = [0]

    # Create file-based logger for event debugging
    import logging
    event_log = logging.getLogger("agent.events")
    fh = logging.FileHandler("/tmp/agent_entrypoint.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    event_log.addHandler(fh)
    event_log.setLevel(logging.DEBUG)

    event_log.info(f"Registering event handlers for session {consultation.session_id}")

    # === USER INPUT EVENTS ===
    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event):
        """Fired when user speech is transcribed (STT result)."""
        transcript = getattr(event, 'transcript', '')
        is_final = getattr(event, 'is_final', False)
        event_log.info(f"USER SPEECH: '{transcript[:100]}' (final={is_final})")

    @session.on("user_state_changed")
    def on_user_state_changed(event):
        """Fired when user's speaking state changes."""
        old_state = getattr(event, 'old_state', 'unknown')
        new_state = getattr(event, 'new_state', 'unknown')
        event_log.info(f"USER STATE: {old_state} -> {new_state}")

    # === AGENT STATE EVENTS ===
    @session.on("agent_state_changed")
    def on_agent_state_changed(event):
        """Fired when agent's state changes."""
        old_state = getattr(event, 'old_state', 'unknown')
        new_state = getattr(event, 'new_state', 'unknown')
        event_log.info(f"AGENT STATE: {old_state} -> {new_state}")

    @session.on("speech_created")
    def on_speech_created(event):
        """Fired when agent starts generating speech."""
        event_log.info("AGENT SPEECH CREATED")

    # === CONVERSATION EVENTS ===
    @session.on("conversation_item_added")
    def on_conversation_item_added(event):
        """Вызывается при каждом новом сообщении в диалоге."""
        item = getattr(event, 'item', None)
        role = getattr(item, 'role', 'unknown') if item else 'unknown'
        content = getattr(item, 'content', '') if item else ''
        event_log.info(f"CONVERSATION: role={role}, content='{str(content)[:80]}'")
        _handle_conversation_item(
            event, consultation, session_id, db_backed,
            messages_since_last_extract,
        )

    # === ERROR EVENTS ===
    @session.on("error")
    def on_error(event):
        """Fired on any error."""
        error = getattr(event, 'error', None)
        event_log.error(f"ERROR: {error}")

    # === METRICS EVENTS ===
    @session.on("metrics_collected")
    def on_metrics_collected(event):
        """Fired when metrics are collected."""
        pass  # Too noisy

    # === SESSION CLOSE ===
    @session.on("close")
    def on_session_close(event):
        """Вызывается при закрытии сессии (отключение клиента)."""
        reason = getattr(event, 'reason', 'unknown')
        event_log.info(f"SESSION CLOSE: reason={reason}, messages={len(consultation.dialogue_history)}")
        asyncio.create_task(_finalize_and_save(consultation, session_id))

    event_log.info("All event handlers registered successfully")


def _handle_conversation_item(
    event,
    consultation: VoiceConsultationSession,
    session_id: Optional[str],
    db_backed: bool,
    messages_since_last_extract: list,
):
    """Process a single conversation item from LiveKit."""
    try:
        item = event.item
        role = getattr(item, 'role', None)
        content = getattr(item, 'content', None)

        dialogue_log.debug(
            "AGENT: Processing conversation item",
            item_type=type(item).__name__,
            role=role,
            has_content=content is not None,
            content_type=type(content).__name__ if content else "None",
            content_preview=str(content)[:60] if content else "",
        )

        if not (role and content):
            dialogue_log.debug(
                "AGENT: Skipping item - no role or content",
                role=role,
                content_is_none=content is None,
            )
            return

        if not isinstance(content, str):
            content = str(content)

        mapped_role = "user" if role == "user" else "assistant"
        consultation.add_message(mapped_role, content)

        if not (db_backed and session_id):
            return

        _sync_to_db(consultation, session_id)
        messages_since_last_extract[0] += 1

        if messages_since_last_extract[0] >= 6:
            messages_since_last_extract[0] = 0
            asyncio.create_task(
                _extract_and_update_anketa(consultation, session_id)
            )

    except Exception as e:
        logger.error(
            "AGENT: Failed to process conversation item",
            error=str(e),
            traceback=traceback.format_exc(),
        )


def _create_realtime_model():
    """Build the Azure OpenAI RealtimeModel from environment variables."""
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
    azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = os.getenv(
        "AZURE_OPENAI_DEPLOYMENT_NAME",
        "gpt-4o-realtime-preview",
    )
    azure_api_version = os.getenv(
        "AZURE_OPENAI_REALTIME_API_VERSION",
        "2024-10-01-preview",
    )

    azure_log.info(
        "AGENT: Creating RealtimeModel",
        endpoint=azure_endpoint[:40] + "..." if len(azure_endpoint) > 40 else azure_endpoint,
        deployment=azure_deployment,
        api_version=azure_api_version,
        api_key_present=bool(azure_api_key),
        api_key_length=len(azure_api_key) if azure_api_key else 0,
    )

    if not all([azure_endpoint, azure_api_key]):
        raise ValueError("Azure OpenAI credentials not configured in .env")

    wss_endpoint = azure_endpoint.replace("https://", "wss://")
    azure_log.info("AGENT: WSS endpoint", wss_endpoint=wss_endpoint[:50] + "...")

    # VAD configuration for better turn detection (v1.4)
    # - threshold=0.6: Filter out quiet noise (0.5 = default, 0.6 = stricter)
    # - prefix_padding_ms=300: Buffer before speech start
    # - silence_duration_ms=1200: Wait 1.2 sec silence before responding
    model = lk_openai.realtime.RealtimeModel.with_azure(
        azure_deployment=azure_deployment,
        azure_endpoint=wss_endpoint,
        api_key=azure_api_key,
        api_version=azure_api_version,
        voice="alloy",
        temperature=0.7,
        turn_detection=lk_openai.realtime.ServerVadOptions(
            threshold=0.6,
            prefix_padding_ms=300,
            silence_duration_ms=1200,
        ),
    )

    azure_log.info(
        "AGENT: RealtimeModel created",
        model_type=type(model).__name__,
    )
    return model


async def entrypoint(ctx: JobContext):
    """
    Точка входа для LiveKit Agent.

    Вызывается когда клиент подключается к комнате.
    """
    # Debug logging to file (subprocess logs don't forward to parent)
    import logging
    debug_log = logging.getLogger("agent.entrypoint")
    fh = logging.FileHandler("/tmp/agent_entrypoint.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    debug_log.addHandler(fh)
    debug_log.setLevel(logging.DEBUG)

    debug_log.info(f"=== ENTRYPOINT START === Room: {ctx.room.name}")

    # Force reinitialize logging in subprocess
    from src.logging_config import setup_logging
    setup_logging("agent")

    logger.info("=" * 60)
    logger.info(
        "=== AGENT ENTRYPOINT CALLED ===",
        room_name=ctx.room.name,
        room_sid=getattr(ctx.room, "sid", "unknown"),
    )
    logger.info("=" * 60)
    debug_log.info("Logger initialized, proceeding to create RealtimeModel...")

    # Step 1: Create RealtimeModel
    try:
        debug_log.info("STEP 1/5: Creating RealtimeModel...")
        realtime_model = _create_realtime_model()
        debug_log.info("STEP 1/5: RealtimeModel created OK")
    except Exception as e:
        debug_log.error(f"STEP 1/5 FAILED: {e}")
        raise

    # Step 2: Create VoiceAgent with instructions only
    try:
        debug_log.info("STEP 2/5: Creating VoiceAgent...")
        prompt = get_system_prompt()
        agent = VoiceAgent(instructions=prompt)
        debug_log.info(f"STEP 2/5: VoiceAgent created, prompt_length={len(prompt)}")
    except Exception as e:
        debug_log.error(f"STEP 2/5 FAILED: {e}")
        raise

    # Step 3: Connect to room
    try:
        debug_log.info("STEP 3/5: Connecting to room...")
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
        debug_log.info(f"STEP 3/5: Connected to room {ctx.room.name}")

        # Log remote participants and their tracks
        for pid, participant in ctx.room.remote_participants.items():
            debug_log.info(f"  Remote participant: {participant.identity}")
            for tid, track_pub in participant.track_publications.items():
                debug_log.info(f"    Track: {track_pub.kind} - subscribed={track_pub.subscribed}")
    except Exception as e:
        debug_log.error(f"STEP 3/5 FAILED: {e}")
        raise

    # Step 4: Create AgentSession + event handlers
    try:
        debug_log.info("STEP 4/5: Creating AgentSession...")
        session = AgentSession(
            llm=realtime_model,
            allow_interruptions=True,
        )
        debug_log.info("STEP 4/5: AgentSession created")

        session_id, db_session = _lookup_db_session(ctx.room.name)
        consultation = _init_consultation(ctx.room.name, db_session)

        _register_event_handlers(
            session, consultation, session_id, db_backed=db_session is not None,
        )
        debug_log.info("STEP 4/5: Event handlers registered")
    except Exception as e:
        debug_log.error(f"STEP 4/5 FAILED: {e}")
        raise

    # Add room event handlers for debugging participant/track connections
    @ctx.room.on("participant_connected")
    def on_participant_connected(participant):
        debug_log.info(f"ROOM EVENT: Participant connected: {participant.identity}")

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant):
        debug_log.info(f"ROOM EVENT: Track subscribed: {track.kind} from {participant.identity}")

    @ctx.room.on("track_published")
    def on_track_published(publication, participant):
        debug_log.info(f"ROOM EVENT: Track published: {publication.kind} from {participant.identity}")

    # Step 5: Start agent session and trigger greeting
    try:
        debug_log.info("STEP 5/5: Starting agent session...")
        room_input = RoomInputOptions(audio_enabled=True)
        await session.start(agent, room=ctx.room, room_input_options=room_input)
        debug_log.info("STEP 5/5: Agent session started with audio input enabled")

        # Trigger the agent to greet the user
        await session.generate_reply(
            user_input="[Поприветствуй клиента и спроси о его компании]"
        )
        debug_log.info("STEP 5/5: Greeting triggered successfully!")

        # Greeting lock — ignore mic noise during first second (v1.4)
        await asyncio.sleep(1.0)
        debug_log.info("STEP 5/5: Greeting lock released")
    except Exception as e:
        debug_log.error(f"STEP 5/5 FAILED: {e}")
        raise

    debug_log.info(f"=== AGENT FULLY READY === room={ctx.room.name}")
    debug_log.info("Agent is now listening for user speech...")


def run_voice_agent():
    """
    Запустить голосового агента.

    Использование:
        python -m src.voice.consultant

    Или через скрипт:
        python scripts/run_voice_agent.py
    """
    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    logger.info("=" * 60)
    logger.info("=== VOICE AGENT STARTING ===")
    logger.info(
        "AGENT CONFIG",
        livekit_url=livekit_url,
        api_key_present=bool(api_key),
        api_secret_present=bool(api_secret),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", "")[:40],
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
        azure_api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    )
    logger.info("=" * 60)

    # agent_name отключает автоматический dispatch - агент будет запускаться
    # только при явном вызове через CreateAgentDispatchRequest
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="hanc-consultant",  # Explicit dispatch only
            api_key=api_key,
            api_secret=api_secret,
            ws_url=livekit_url,
        ),
    )


if __name__ == "__main__":
    run_voice_agent()
