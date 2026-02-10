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
import sys
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
from livekit.plugins.openai.realtime.realtime_model import TurnDetection
from openai.types.beta.realtime.session import InputAudioTranscription

from src.anketa import AnketaExtractor, AnketaGenerator
from src.config.prompt_loader import get_prompt
from src.llm.deepseek import DeepSeekClient
from src.knowledge import IndustryKnowledgeManager, EnrichedContextBuilder
from src.output import OutputManager
from src.session.manager import SessionManager

# ---------------------------------------------------------------------------
# Monkey-patch: LiveKit SDK Tee.aclose() crashes on Python 3.14
# Python 3.14 raises RuntimeError when calling aclose() on an async generator
# that is currently suspended at yield. LiveKit SDK 1.4.1 hits this in
# livekit.agents.utils.aio.itertools.Tee.aclose() → audio stream aborts
# mid-sentence. Safe to suppress: the generator will be cleaned up by GC.
# ---------------------------------------------------------------------------
try:
    import livekit.agents.utils.aio.itertools as _lk_itertools

    async def _safe_tee_aclose(self):
        for child in self._children:
            try:
                await child.aclose()
            except RuntimeError as e:
                if "asynchronous generator is already running" in str(e):
                    pass  # Python 3.14 incompatibility — safe to ignore
                else:
                    raise

    _lk_itertools.Tee.aclose = _safe_tee_aclose
except Exception:
    pass  # If SDK structure changes, fail silently

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
        self.document_context = None  # DocumentContext from uploaded files
        self.status = "active"  # active, completed, error
        self.kb_enriched = False  # True after industry KB context injected
        self.review_started = False  # True when review phase activated
        self.research_done = False  # True after background research launched

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
        anketa_json = anketa.model_dump(mode="json")

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


def _build_resume_context(db_session) -> str:
    """Собирает контекст предыдущего разговора для возобновлённых сессий.

    Когда пользователь возвращается к приостановленной сессии, Azure Realtime API
    стартует с чистого листа. Эта функция создаёт текстовое резюме предыдущего
    разговора (последние 20 сообщений + анкета) для инъекции в системный промпт.
    """
    parts = []

    # Раздел 1: Данные анкеты (самое важное — структурированная информация)
    if db_session.anketa_data:
        anketa_summary = format_anketa_for_voice(db_session.anketa_data)
        if anketa_summary and anketa_summary != "(Анкета пока пуста)":
            parts.append(f"Собранная информация (анкета):\n{anketa_summary}")

    # Раздел 2: Последние N сообщений из истории диалога
    history = db_session.dialogue_history or []
    if history:
        recent = history[-20:]
        lines = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if not content:
                continue
            if len(content) > 300:
                content = content[:300] + "..."
            speaker = "Клиент" if role == "user" else "Консультант"
            lines.append(f"- {speaker}: {content}")
        if lines:
            parts.append("Последние сообщения из предыдущего разговора:\n" + "\n".join(lines))

    if not parts:
        return ""

    return (
        "\n\n### ПРОДОЛЖЕНИЕ СЕССИИ\n"
        "Это возобновлённая консультация. Клиент уже общался с тобой ранее.\n"
        "Используй контекст ниже, чтобы продолжить разговор, не задавая вопросы повторно.\n"
        "При приветствии скажи, что рад продолжить, и кратко напомни, на чём остановились.\n\n"
        + "\n\n".join(parts)
    )


# ---------------------------------------------------------------------------
# SessionManager integration (shared DB with web server)
# ---------------------------------------------------------------------------

_session_mgr = SessionManager()

# --- Optional Redis cache for active voice sessions ---
_redis_mgr = None


def _try_get_redis():
    """Get RedisStorageManager or None if Redis unavailable."""
    global _redis_mgr
    if _redis_mgr is not None:
        return _redis_mgr
    try:
        from src.storage.redis import RedisStorageManager
        mgr = RedisStorageManager(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD"),
        )
        if mgr.health_check():
            _redis_mgr = mgr
            return mgr
    except Exception:
        pass
    return None


# --- Optional PostgreSQL for long-term anketa storage ---
_postgres_mgr = None


def _try_get_postgres():
    """Get PostgreSQLStorageManager or None if PostgreSQL unavailable."""
    global _postgres_mgr
    if _postgres_mgr is not None:
        return _postgres_mgr
    try:
        from src.storage.postgres import PostgreSQLStorageManager
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return None
        mgr = PostgreSQLStorageManager(db_url)
        if mgr.health_check():
            _postgres_mgr = mgr
            return mgr
    except Exception:
        pass
    return None


async def _run_background_research(
    consultation: VoiceConsultationSession,
    session_id: str,
    agent_session: Optional[AgentSession],
    website: str,
    industry: Optional[str],
    company_name: Optional[str],
):
    """Run background research on client's website and inject results."""
    try:
        from src.research.engine import ResearchEngine
        engine = ResearchEngine()
        result = await engine.research(
            website=website,
            industry=industry,
            company_name=company_name,
        )

        if not result.has_data():
            anketa_log.info("research_no_data", session_id=session_id)
            return

        # Format research for prompt injection
        parts = []
        if result.industry_insights:
            parts.append("Инсайты отрасли: " + "; ".join(result.industry_insights[:3]))
        if result.best_practices:
            parts.append("Best practices: " + "; ".join(result.best_practices[:3]))
        if result.website_data:
            desc = result.website_data.get("description", "")
            if desc:
                parts.append(f"С сайта клиента: {desc[:200]}")

        if not parts:
            return

        research_context = " | ".join(parts)
        consultation.research_done = True

        # Inject into agent instructions
        if agent_session is not None:
            activity = getattr(agent_session, '_activity', None)
            if activity and hasattr(activity, 'update_instructions'):
                current = getattr(activity, 'instructions', get_system_prompt())
                updated = f"{current}\n\n### Данные исследования:\n{research_context}"
                await activity.update_instructions(updated)
                anketa_log.info(
                    "research_injected",
                    session_id=session_id,
                    sources=result.sources_used,
                )
    except Exception as e:
        anketa_log.warning("background_research_failed", error=str(e))


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
    agent_session: Optional[AgentSession] = None,
):
    """Extract anketa from current dialogue and update in DB.

    Also injects industry KB context into the voice agent on first extraction
    (when industry can be detected from dialogue).
    """
    try:
        if len(consultation.dialogue_history) < 4:
            return

        # Fetch document_context from DB if client uploaded files
        doc_context = None
        db_session = _session_mgr.get_session(session_id)
        if db_session and db_session.document_context:
            try:
                from src.documents import DocumentContext
                doc_context = DocumentContext(**db_session.document_context)
            except Exception:
                pass  # Use dict fallback — extractor handles both

        deepseek = DeepSeekClient()
        extractor = AnketaExtractor(deepseek)

        anketa = await extractor.extract(
            dialogue_history=consultation.dialogue_history,
            duration_seconds=consultation.get_duration_seconds(),
            document_context=doc_context,
        )

        anketa_data = anketa.model_dump(mode="json")
        anketa_md = AnketaGenerator.render_markdown(anketa)
        _session_mgr.update_anketa(session_id, anketa_data, anketa_md)

        # Update metadata via field-specific method (no full session overwrite
        # that could race with update_document_context or update_anketa)
        if anketa.company_name or anketa.contact_name:
            _session_mgr.update_metadata(
                session_id,
                company_name=anketa.company_name,
                contact_name=anketa.contact_name,
            )

        anketa_log.info(
            "periodic_anketa_extracted",
            session_id=session_id,
            company=anketa.company_name,
            has_documents=doc_context is not None,
        )

        # --- Launch background research if website detected ---
        if not consultation.research_done and anketa.website:
            consultation.research_done = True  # set early to prevent duplicates
            industry_id_for_research = None
            try:
                mgr = IndustryKnowledgeManager()
                user_text_r = " ".join(
                    m.get("content", "") for m in consultation.dialogue_history
                    if m.get("role") == "user"
                )
                industry_id_for_research = mgr.detect_industry(user_text_r)
            except Exception:
                pass
            task = asyncio.create_task(_run_background_research(
                consultation, session_id, agent_session,
                website=anketa.website,
                industry=industry_id_for_research,
                company_name=anketa.company_name,
            ))
            task.add_done_callback(lambda t: t.result() if not t.cancelled() and not t.exception() else None)
            anketa_log.info("research_launched", website=anketa.website)

        # --- Update Redis hot cache ---
        redis_mgr = _try_get_redis()
        if redis_mgr:
            try:
                import json as _json
                redis_key = f"voice:session:{session_id}"
                redis_mgr.client.setex(
                    redis_key,
                    7200,
                    _json.dumps({
                        "session_id": session_id,
                        "status": "active",
                        "message_count": len(consultation.dialogue_history),
                        "anketa_completion": anketa.completion_rate(),
                        "industry": getattr(anketa, 'industry', None),
                        "updated_at": datetime.now().isoformat(),
                    }),
                )
            except Exception:
                pass  # Non-critical

        # --- Inject industry KB context with regional awareness (once) ---
        if not consultation.kb_enriched and agent_session is not None:
            try:
                from src.knowledge.country_detector import get_country_detector

                user_text = " ".join(
                    m.get("content", "") for m in consultation.dialogue_history
                    if m.get("role") == "user"
                )
                manager = IndustryKnowledgeManager()
                industry_id = manager.detect_industry(user_text)

                if industry_id:
                    # Detect country from dialogue language + phone
                    detector = get_country_detector()
                    phone = getattr(anketa, 'contact_phone', None)
                    region, country = detector.detect(
                        phone=phone,
                        dialogue_text=user_text,
                    )

                    # Load regional profile (falls back to _base automatically)
                    if region and country:
                        profile = manager.loader.load_regional_profile(
                            region, country, industry_id
                        )
                    else:
                        profile = manager.get_profile(industry_id)

                    if profile:
                        builder = EnrichedContextBuilder(manager)
                        voice_context = builder.build_for_voice(
                            consultation.dialogue_history
                        )
                        if voice_context:
                            base_prompt = get_system_prompt()
                            enriched = f"{base_prompt}\n\n### Контекст отрасли:\n{voice_context}"
                            activity = getattr(agent_session, '_activity', None)
                            if activity and hasattr(activity, 'update_instructions'):
                                await activity.update_instructions(enriched)
                                consultation.kb_enriched = True
                                anketa_log.info(
                                    "KB context injected",
                                    session_id=session_id,
                                    industry=industry_id,
                                    region=region,
                                    country=country,
                                )
            except Exception as e:
                anketa_log.warning("KB injection failed (non-fatal)", error=str(e))

        # --- Review phase: switch to anketa verification when ready ---
        if not consultation.review_started and agent_session is not None:
            try:
                rate = anketa.completion_rate()
                msg_count = len(consultation.dialogue_history)
                if rate >= 0.5 and msg_count >= 16:
                    consultation.review_started = True
                    summary = format_anketa_for_voice(anketa_data)
                    review_prompt = get_review_system_prompt(summary)
                    activity = getattr(agent_session, '_activity', None)
                    if activity and hasattr(activity, 'update_instructions'):
                        await activity.update_instructions(review_prompt)
                        await agent_session.generate_reply(
                            user_input="[Начни проверку анкеты. Зачитай первый пункт и спроси подтверждение.]"
                        )
                        anketa_log.info(
                            "review_phase_started",
                            session_id=session_id,
                            completion_rate=rate,
                            message_count=msg_count,
                        )
            except Exception as e:
                anketa_log.warning("review_phase_start_failed", error=str(e))

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

    # Save dialogue + duration + status via field-specific update
    # (no full session overwrite that could race with document_context/anketa)
    _session_mgr.update_dialogue(
        session_id,
        dialogue_history=consultation.dialogue_history,
        duration_seconds=consultation.get_duration_seconds(),
        status="reviewing",
    )

    if consultation.status == "completed":
        try:
            # Fetch document_context if client uploaded files
            doc_context = None
            session = _session_mgr.get_session(session_id)
            if session and session.document_context:
                try:
                    from src.documents import DocumentContext
                    doc_context = DocumentContext(**session.document_context)
                except Exception:
                    pass

            deepseek = DeepSeekClient()
            extractor = AnketaExtractor(deepseek)

            anketa = await extractor.extract(
                dialogue_history=consultation.dialogue_history,
                duration_seconds=consultation.get_duration_seconds(),
                document_context=doc_context,
            )

            anketa_data = anketa.model_dump(mode="json")
            anketa_md = AnketaGenerator.render_markdown(anketa)
            _session_mgr.update_anketa(session_id, anketa_data, anketa_md)

            if anketa.company_name or anketa.contact_name:
                _session_mgr.update_metadata(
                    session_id,
                    company_name=anketa.company_name,
                    contact_name=anketa.contact_name,
                )

        except Exception as e:
            anketa_log.warning("final_anketa_extraction_failed", error=str(e))

    session_log.info(
        "session_finalized_in_db",
        session_id=session_id,
        status="reviewing",
    )

    # Load fresh session for downstream pipelines (notifications, learning, PostgreSQL)
    session = _session_mgr.get_session(session_id)
    if not session:
        session_log.warning("finalize_session_lost_after_update", session_id=session_id)
        return

    # --- Send notifications (fire-and-forget) ---
    try:
        from src.notifications.manager import NotificationManager
        notifier = NotificationManager()
        await notifier.on_session_confirmed(session)
        anketa_log.info("notification_sent", session_id=session_id)
    except Exception as e:
        anketa_log.warning("notification_failed", error=str(e))

    # --- Record learning for industry KB ---
    try:
        manager = IndustryKnowledgeManager()
        builder = EnrichedContextBuilder(manager)
        industry_id = builder.get_industry_id(consultation.dialogue_history)
        if industry_id and session.anketa_data:
            company = session.company_name or "N/A"
            filled = sum(1 for v in session.anketa_data.values()
                         if v and v != [] and v != "")
            insight = (
                f"Голосовая сессия {session_id}: {company}, "
                f"заполнено полей: {filled}, "
                f"длительность: {round(session.duration_seconds / 60, 1)} мин"
            )
            manager.record_learning(industry_id, insight, f"voice_{session_id}")
            anketa_log.info("learning_recorded", industry_id=industry_id)
    except Exception as e:
        anketa_log.warning("record_learning_failed", error=str(e))

    # --- Save to PostgreSQL (long-term storage) ---
    pg_mgr = _try_get_postgres()
    if pg_mgr and session.anketa_data:
        try:
            from src.anketa.schema import FinalAnketa as _FinalAnketa

            anketa_dict = dict(session.anketa_data)
            if not anketa_dict.get("interview_id"):
                anketa_dict["interview_id"] = session_id
            anketa_obj = _FinalAnketa(**anketa_dict)

            await pg_mgr.save_anketa(anketa_obj)
            await pg_mgr.update_interview_session(
                session_id=session_id,
                completed_at=datetime.now(),
                duration=session.duration_seconds,
                completeness_score=anketa_obj.completion_rate() if hasattr(anketa_obj, 'completion_rate') else None,
                status=session.status or "completed",
            )
            anketa_log.info("postgres_saved", session_id=session_id)
        except Exception as e:
            anketa_log.warning("postgres_save_failed", error=str(e))

    # --- Remove from Redis hot cache ---
    redis_mgr = _try_get_redis()
    if redis_mgr:
        try:
            redis_mgr.client.delete(f"voice:session:{session_id}")
        except Exception:
            pass


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
    # При возобновлении сессии продолжаем счёт, а не начинаем с нуля
    messages_since_last_extract = [len(consultation.dialogue_history) % 6]

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
        """Fired when user speech is transcribed (STT result).

        The Realtime API first fires (transcript="", is_final=False) as a placeholder
        when user stops speaking, then fires (transcript="actual text", is_final=True)
        when Azure completes transcription. We capture final transcripts into
        dialogue_history so DeepSeek can extract anketa data from them.
        """
        transcript = getattr(event, 'transcript', '')
        is_final = getattr(event, 'is_final', False)
        event_log.info(f"USER SPEECH: '{transcript[:100]}' (final={is_final})")

        # Capture final user transcripts into dialogue history
        if is_final and transcript.strip():
            consultation.add_message("user", transcript.strip())
            if db_backed and session_id:
                messages_since_last_extract[0] += 1
                if messages_since_last_extract[0] >= 6:
                    messages_since_last_extract[0] = 0
                    asyncio.create_task(
                        _extract_and_update_anketa(consultation, session_id, session)
                    )

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
        raw_content = getattr(item, 'content', '') if item else ''
        # Extract text from List content for logging
        if isinstance(raw_content, list):
            text_parts = [c for c in raw_content if isinstance(c, str)]
            display = " ".join(text_parts) if text_parts else str(raw_content)
        else:
            display = str(raw_content) if raw_content else ""
        event_log.info(f"CONVERSATION: role={role}, content='{display[:80]}'")
        _handle_conversation_item(
            event, consultation, session_id, db_backed,
            messages_since_last_extract, session,
        )

    # === ERROR EVENTS ===
    @session.on("error")
    def on_error(event):
        """Fired on any error — log full Azure error details."""
        error = getattr(event, 'error', None)
        # Extract the inner body (Azure's actual error) from APIError
        body = getattr(error, 'body', None)
        if body:
            msg = getattr(body, 'message', None) or body
            code = getattr(body, 'code', None)
            etype = getattr(body, 'type', None)
            event_log.error(
                f"ERROR: code={code} type={etype} message={msg}"
            )
        else:
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
    agent_session: Optional[AgentSession] = None,
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

        if not role:
            dialogue_log.debug(
                "AGENT: Skipping item - no role",
                role=role,
            )
            return

        # ChatMessage.content is List[str | AudioContent | ...] in LiveKit SDK
        # Extract text parts only
        if isinstance(content, list):
            text_parts = [c for c in content if isinstance(c, str)]
            content = " ".join(text_parts) if text_parts else ""
        elif content is not None and not isinstance(content, str):
            content = str(content)
        else:
            content = content or ""

        if not content.strip():
            dialogue_log.debug(
                "AGENT: Skipping item - empty content after extraction",
                role=role,
            )
            return

        mapped_role = "user" if role == "user" else "assistant"

        # Skip user messages — already captured by on_user_input_transcribed.
        # Processing them here too would double-count and trigger extraction
        # every 3 messages instead of 6.
        if mapped_role == "user":
            return

        consultation.add_message(mapped_role, content)

        if not (db_backed and session_id):
            return

        messages_since_last_extract[0] += 1

        if messages_since_last_extract[0] >= 6:
            messages_since_last_extract[0] = 0
            asyncio.create_task(
                _extract_and_update_anketa(consultation, session_id, agent_session)
            )

    except Exception as e:
        logger.error(
            "AGENT: Failed to process conversation item",
            error=str(e),
            traceback=traceback.format_exc(),
        )


def _create_realtime_model(voice_config: dict = None):
    """Build the Azure OpenAI RealtimeModel from environment variables."""
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
    azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = os.getenv(
        "AZURE_OPENAI_DEPLOYMENT_NAME",
        "gpt-4o-realtime-preview",
    )
    azure_api_version = os.getenv(
        "AZURE_OPENAI_REALTIME_API_VERSION",
        "2025-04-01-preview",
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

    # VAD configuration for turn detection (v2.0)
    #
    # Root cause of v1.5 problems (diagnosed from session 905f8cdf logs):
    #   4 ghost VAD triggers in 71 seconds — VAD detected noise/echo/breathing,
    #   STT returned empty string, agent started responding to nothing,
    #   real user speech then interrupted the ghost response → user perceives
    #   agent as "stuttering" / "starting words but not finishing them".
    #
    # v2.0 fixes:
    # - threshold 0.65→0.85: Much stricter noise filter, ignores breathing/echo
    # - silence_duration_ms 1500→2000: Wait 2s silence before ending turn
    # - prefix_padding_ms 300→500: More audio context before speech start
    # v3.0 fixes (diagnosed from RAW AZURE EVENT logs):
    # - eagerness REMOVED: Azure 2025-04-01-preview rejects it as unknown_parameter
    # - threshold 0.85→0.9: Stricter noise filter
    # - silence_duration_ms 2000→3000: Wait 3s silence before ending turn — user gets
    #   time to pause mid-sentence without agent jumping in
    # - prefix_padding_ms 500: Keep as is
    #
    # v4.1: silence_duration_ms is configurable per session via voice_config
    silence_ms = 4000  # default
    if voice_config and "silence_duration_ms" in voice_config:
        silence_ms = int(voice_config["silence_duration_ms"])
        silence_ms = max(1500, min(6000, silence_ms))  # clamp to safe range

    model = lk_openai.realtime.RealtimeModel.with_azure(
        azure_deployment=azure_deployment,
        azure_endpoint=wss_endpoint,
        api_key=azure_api_key,
        api_version=azure_api_version,
        voice="alloy",
        temperature=0.7,
        # Explicit input audio transcription — required for user speech to appear
        # as text in dialogue_history. Without this, the Realtime API processes
        # audio internally (model can "hear") but no text transcript is produced,
        # so conversation_item_added never fires for role=user.
        input_audio_transcription=InputAudioTranscription(model="whisper-1", language="ru"),
        turn_detection=TurnDetection(
            type="server_vad",
            threshold=0.9,
            prefix_padding_ms=500,
            silence_duration_ms=silence_ms,
        ),
    )

    azure_log.info(
        "AGENT: VAD silence_duration_ms",
        silence_duration_ms=silence_ms,
        from_voice_config=voice_config is not None,
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
    debug_log.info("Logger initialized, proceeding to DB lookup...")

    # Step 1: DB lookup (need voice_config before model creation)
    try:
        debug_log.info("STEP 1/5: Looking up DB session for voice_config...")
        session_id, db_session = _lookup_db_session(ctx.room.name)
        voice_config = db_session.voice_config if db_session else None
        debug_log.info(f"STEP 1/5: DB session found={db_session is not None}, voice_config={voice_config}")
    except Exception as e:
        debug_log.warning(f"STEP 1/5: DB lookup failed (non-fatal): {e}")
        session_id, db_session, voice_config = None, None, None

    # Step 2: Create RealtimeModel with voice_config
    try:
        debug_log.info("STEP 2/5: Creating RealtimeModel...")
        realtime_model = _create_realtime_model(voice_config=voice_config)
        debug_log.info("STEP 2/5: RealtimeModel created OK")
    except Exception as e:
        debug_log.error(f"STEP 2/5 FAILED: {e}")
        raise

    # Step 3: Create VoiceAgent with instructions (+ resume context if returning)
    try:
        debug_log.info("STEP 3/5: Creating VoiceAgent...")
        prompt = get_system_prompt()

        # Инъекция контекста предыдущего разговора для возобновлённых сессий
        if db_session and db_session.dialogue_history:
            resume_ctx = _build_resume_context(db_session)
            if resume_ctx:
                prompt = prompt + resume_ctx
                debug_log.info(
                    f"STEP 3/5: Resume context injected, "
                    f"history_messages={len(db_session.dialogue_history)}, "
                    f"context_length={len(resume_ctx)}"
                )

        agent = VoiceAgent(instructions=prompt)
        debug_log.info(f"STEP 3/5: VoiceAgent created, prompt_length={len(prompt)}")
    except Exception as e:
        debug_log.error(f"STEP 3/5 FAILED: {e}")
        raise

    # Step 4: Connect to room
    try:
        debug_log.info("STEP 4/5: Connecting to room...")
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
        debug_log.info(f"STEP 4/5: Connected to room {ctx.room.name}")

        # Log remote participants and their tracks
        for pid, participant in ctx.room.remote_participants.items():
            debug_log.info(f"  Remote participant: {participant.identity}")
            for tid, track_pub in participant.track_publications.items():
                debug_log.info(f"    Track: {track_pub.kind} - subscribed={track_pub.subscribed}")
    except Exception as e:
        debug_log.error(f"STEP 4/5 FAILED: {e}")
        raise

    # Step 5: Create AgentSession + event handlers
    try:
        debug_log.info("STEP 5/5: Creating AgentSession...")
        # Interruption parameters (v3.0)
        #
        # v2.0 still interrupted too aggressively — user complaint:
        #   "Агент не дает мне договорить. Он вечно вмешивается."
        #
        # v3.0 — much more patient:
        #   - min_interruption_duration 1.5→2.0: Need 2s of clear speech to interrupt
        #   - min_interruption_words 3→4: Need 4 words before interrupting
        #   - min_endpointing_delay 1.5→2.5: Wait 2.5s of silence before responding
        #   - false_interruption_timeout 2.5→3.0: 3s window to detect false positives
        session = AgentSession(
            llm=realtime_model,
            allow_interruptions=True,
            min_interruption_duration=2.0,
            min_interruption_words=4,
            min_endpointing_delay=2.5,
            false_interruption_timeout=3.0,
            resume_false_interruption=True,
        )
        debug_log.info("STEP 5/5: AgentSession created")

        # session_id and db_session already obtained in Step 1
        consultation = _init_consultation(ctx.room.name, db_session)

        _register_event_handlers(
            session, consultation, session_id, db_backed=db_session is not None,
        )
        debug_log.info("STEP 5/5: Event handlers registered")

        # Register session in Redis (optional hot cache)
        redis_mgr = _try_get_redis()
        if redis_mgr and session_id:
            try:
                import json as _json
                redis_key = f"voice:session:{session_id}"
                redis_mgr.client.setex(
                    redis_key,
                    7200,  # 2h TTL
                    _json.dumps({
                        "session_id": session_id,
                        "room_name": ctx.room.name,
                        "status": "active",
                        "started_at": datetime.now().isoformat(),
                        "message_count": 0,
                    }),
                )
                debug_log.info(f"Session registered in Redis: {session_id}")
            except Exception as e:
                debug_log.warning(f"Redis registration failed (non-fatal): {e}")

        # Register session in PostgreSQL (optional long-term storage)
        pg_mgr = _try_get_postgres()
        if pg_mgr and session_id:
            try:
                from src.models import InterviewPattern as _Pattern
                await pg_mgr.save_interview_session(
                    session_id=session_id,
                    interview_id=session_id,
                    pattern=_Pattern.INTERACTION,
                    status="active",
                    metadata={
                        "room_name": ctx.room.name,
                        "started_at": datetime.now().isoformat(),
                    },
                )
                debug_log.info(f"Session registered in PostgreSQL: {session_id}")
            except Exception as e:
                debug_log.warning(f"PostgreSQL registration failed (non-fatal): {e}")
    except Exception as e:
        debug_log.error(f"STEP 5/5 FAILED: {e}")
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

        # === DIAGNOSTIC: Hook into raw WebSocket events to see what Azure sends ===
        try:
            activity = getattr(session, '_activity', None)
            rt_session = activity.realtime_llm_session if activity else None
            if rt_session and hasattr(rt_session, 'on'):
                _event_counts: dict = {}

                @rt_session.on("openai_server_event_received")
                def _on_raw_event(event):
                    etype = event.get("type", "unknown") if isinstance(event, dict) else "unknown"
                    _event_counts[etype] = _event_counts.get(etype, 0) + 1
                    # Log transcription-related and session.updated events in full
                    if "transcription" in etype or "error" in etype:
                        debug_log.info(f"RAW AZURE EVENT: {etype} -> {event}")
                    # Log session.updated to verify Azure applied input_audio_transcription
                    if etype == "session.updated":
                        sess = event.get("session", {}) if isinstance(event, dict) else {}
                        iat = sess.get("input_audio_transcription")
                        td = sess.get("turn_detection")
                        debug_log.info(
                            f"SESSION.UPDATED from Azure: "
                            f"input_audio_transcription={iat}, "
                            f"turn_detection={td}"
                        )
                    # Periodic summary every 20 events
                    total = sum(_event_counts.values())
                    if total % 20 == 0:
                        debug_log.info(f"RAW EVENT COUNTS: {dict(_event_counts)}")

                debug_log.info("STEP 5/5: Raw WebSocket event hook installed on RealtimeSession")
            else:
                debug_log.warning(
                    f"STEP 5/5: Cannot hook raw events — "
                    f"activity={type(activity).__name__ if activity else None}, "
                    f"rt_session={type(rt_session).__name__ if rt_session else None}"
                )
        except Exception as e:
            debug_log.warning(f"STEP 5/5: Raw event hook failed (non-fatal): {e}")

        # Trigger the agent to greet the user
        await session.generate_reply(
            user_input="[Поприветствуй клиента и спроси о его компании]"
        )
        debug_log.info("STEP 5/5: Greeting triggered successfully!")

        # Greeting lock — ignore mic noise/echo during greeting (v4.0)
        # v1.4: 1.0s — too short, Azure server-side VAD detected 67ms echo
        # v4.0: 3.0s — enough for full greeting + echo decay
        await asyncio.sleep(3.0)
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

    # LiveKit Agents SDK >= 1.0 требует subcommand (dev/start/connect).
    # По умолчанию запускаем в dev-режиме для совместимости с документацией:
    #   python scripts/run_voice_agent.py
    if len(sys.argv) == 1:
        sys.argv.append("dev")

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
