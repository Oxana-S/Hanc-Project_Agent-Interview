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
import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

# R4-19: Shared httpx client with connection pooling (avoid per-request TCP overhead)
_shared_http_client: httpx.AsyncClient | None = None

# R6-09: Background task reference set (prevent GC of fire-and-forget tasks in agent process)
_agent_bg_tasks: set = set()

# P4.3: Global extraction semaphore — limits concurrent LLM calls to avoid rate limit cascading
_extraction_semaphore: asyncio.Semaphore | None = None


def _track_agent_task(task):
    """Keep a reference to prevent GC of fire-and-forget asyncio tasks."""
    _agent_bg_tasks.add(task)
    task.add_done_callback(_agent_bg_tasks.discard)


# R15-07: Lazy lock creation — avoid binding to wrong event loop at import time
# R16-02: Double-checked locking with threading.Lock for atomic bootstrap
_http_client_lock: asyncio.Lock | None = None
_http_client_lock_init = threading.Lock()


async def _get_http_client() -> httpx.AsyncClient:
    """Get or create a shared httpx.AsyncClient with connection pooling."""
    global _shared_http_client, _http_client_lock
    if _http_client_lock is None:
        with _http_client_lock_init:
            if _http_client_lock is None:
                _http_client_lock = asyncio.Lock()
    async with _http_client_lock:
        if _shared_http_client is None or _shared_http_client.is_closed:
            _shared_http_client = httpx.AsyncClient(
                timeout=10.0,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return _shared_http_client


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
from src.llm.factory import create_llm_client
from src.knowledge import IndustryKnowledgeManager, EnrichedContextBuilder
from src.output import OutputManager
from src.session.manager import SessionManager
from src.session.models import SessionStatus, RuntimeStatus

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
        self.start_time = datetime.now(timezone.utc)
        self.dialogue_history: List[Dict[str, Any]] = []
        self.document_context = None  # DocumentContext from uploaded files
        self.status = SessionStatus.ACTIVE  # DB status (will be synced to SessionManager)
        self.runtime_status = RuntimeStatus.IDLE  # Agent-internal status (ephemeral)
        self.kb_enriched = False  # True after industry KB context injected
        self.review_started = False  # True when review phase activated
        self._agent_speaking = False  # True while agent is generating speech
        self._pending_instructions = None  # Buffered instructions to apply after speech ends
        self._latest_instructions = None  # R14-03: Track latest desired instructions for read consistency
        self.research_done = False  # True after background research launched
        self.current_phase = "discovery"  # discovery → analysis → proposal → refinement
        self.detected_industry_id = None  # Cached industry ID
        self.detected_profile = None  # Cached IndustryProfile
        self._cached_extractor = None  # R4-18: reuse AnketaExtractor across extractions
        self._cached_extractor_provider = None  # R17-04: track provider to invalidate on change
        self._last_extraction_time = 0  # R19-02: timestamp of last successful extraction
        # R23-01: Per-session circuit breaker (was global, blocking all sessions)
        self._extraction_consecutive_failures = 0
        self._extraction_backoff_until = 0.0
        # R23-08: Guard against concurrent finalization on rapid disconnect/reconnect
        self._finalization_started = False

    MAX_DIALOGUE_MESSAGES = 500  # R10-09: Prevent unbounded memory growth

    def add_message(self, role: str, content: str):
        """Добавить сообщение в историю диалога."""
        # R10-09: Cap dialogue history to prevent OOM
        if len(self.dialogue_history) >= self.MAX_DIALOGUE_MESSAGES:
            self.dialogue_history = self.dialogue_history[-(self.MAX_DIALOGUE_MESSAGES - 1):]
        self.dialogue_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": self.current_phase
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
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

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
        consultation.runtime_status = RuntimeStatus.COMPLETED
        return

    # v5.0: Determine consultation type for routing
    _ct = "consultation"
    _fin_session = None
    try:
        _fin_session = _session_mgr.get_session(consultation.session_id)
        if _fin_session and _fin_session.voice_config:
            _ct = _fin_session.voice_config.get("consultation_type", "consultation")
    except Exception:
        pass

    try:
        # R19-03: Reuse cached extractor to avoid redundant LLM client creation
        if consultation._cached_extractor:
            extractor = consultation._cached_extractor
        else:
            _llm_provider = None
            if _fin_session and _fin_session.voice_config:
                _llm_provider = _fin_session.voice_config.get("llm_provider")
            llm = create_llm_client(_llm_provider)
            extractor = AnketaExtractor(llm)

        anketa = await extractor.extract(
            dialogue_history=consultation.dialogue_history,
            duration_seconds=consultation.get_duration_seconds(),
            consultation_type=_ct,
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

        consultation.runtime_status = RuntimeStatus.COMPLETED

        anketa_log.info(
            "=== FINALIZE DONE ===",
            session_id=consultation.session_id,
            output_dir=str(company_dir),
            anketa_md=str(anketa_paths["md"]),
            anketa_json=str(anketa_paths["json"]),
            dialogue=str(dialogue_path)
        )

    except Exception as e:
        consultation.runtime_status = RuntimeStatus.ERROR
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


def get_enriched_system_prompt(
    dialogue_history: List[Dict[str, Any]],
    phase: str = "discovery",
) -> str:
    """
    Get system prompt with industry context.

    Detects industry from dialogue and enriches prompt with
    relevant knowledge base information for the given phase.

    Args:
        dialogue_history: Current dialogue history
        phase: Consultation phase for KB context selection

    Returns:
        Enriched system prompt
    """
    base_prompt = get_system_prompt()

    # Need at least 2 messages to detect industry
    if len(dialogue_history) < 2:
        return base_prompt

    try:
        manager = _get_kb_manager()
        builder = EnrichedContextBuilder(manager)

        voice_context = builder.build_for_voice_full(
            dialogue_history, phase=phase,
        )

        if voice_context:
            return f"{base_prompt}\n\n### Контекст отрасли ({phase}):\n{voice_context}"
    except Exception as e:
        logger.warning("Failed to get enriched context", error=str(e))

    return base_prompt


def get_review_system_prompt(anketa_summary: str) -> str:
    """Get system prompt for review phase with current anketa data from YAML."""
    from src.config.prompt_loader import render_prompt
    return render_prompt("voice/review", "system_prompt", anketa_summary=anketa_summary)


def format_anketa_for_voice(anketa_data: dict) -> str:
    """Format anketa data as readable text for voice review.

    Порядок полей соответствует визуальному порядку на форме (index.html).
    """
    sections = [
        # Секция "О компании"
        ("Название компании", anketa_data.get("company_name")),
        ("Контактное лицо", anketa_data.get("contact_name")),
        ("Должность", anketa_data.get("contact_role")),
        ("Телефон", anketa_data.get("phone") or anketa_data.get("contact_phone")),
        ("Email", anketa_data.get("email") or anketa_data.get("contact_email")),
        ("Сайт", anketa_data.get("website")),
        # Секция "О бизнесе"
        ("Отрасль", anketa_data.get("industry")),
        ("Специализация", anketa_data.get("specialization")),
        ("Тип бизнеса", anketa_data.get("business_type")),
        ("Описание компании", anketa_data.get("company_description") or anketa_data.get("business_description")),
        ("Услуги / продукты", anketa_data.get("services")),
        ("Типы клиентов", anketa_data.get("client_types")),
        ("Текущие проблемы", anketa_data.get("current_problems")),
        ("Цели автоматизации", anketa_data.get("business_goals")),
        # Секция "Настройки агента"
        ("Имя агента", anketa_data.get("agent_name")),
        ("Направление звонков", anketa_data.get("call_direction")),
        ("Назначение агента", anketa_data.get("agent_purpose")),
        ("Задачи агента", anketa_data.get("agent_tasks") or anketa_data.get("agent_functions")),
        ("Интеграции", anketa_data.get("integrations")),
        ("Пол голоса", anketa_data.get("voice_gender")),
        ("Тон голоса", anketa_data.get("voice_tone")),
        ("Перевод на оператора", anketa_data.get("transfer_conditions")),
        # Секция "Дополнительно"
        ("Ограничения", anketa_data.get("constraints")),
        ("Требования регулятора", anketa_data.get("compliance_requirements")),
        ("Объём звонков", anketa_data.get("call_volume")),
        ("Бюджет", anketa_data.get("budget")),
        ("Сроки", anketa_data.get("timeline")),
        ("Примечания", anketa_data.get("additional_notes")),
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

# R19-05: Ensure SQLite connection is closed when agent process exits
import atexit as _atexit
def _close_session_mgr():
    try:
        _session_mgr.close()  # R26-11: Use public method (respects _lock, avoids WAL corruption)
    except Exception:
        pass
_atexit.register(_close_session_mgr)

# R11-08: Cached IndustryKnowledgeManager singleton (avoids re-reading 968 YAML files)
_kb_manager = None
_kb_manager_lock = threading.Lock()


def _get_kb_manager():
    """Get or create cached IndustryKnowledgeManager singleton."""
    global _kb_manager
    if _kb_manager is None:
        with _kb_manager_lock:
            if _kb_manager is None:
                _kb_manager = IndustryKnowledgeManager()
    return _kb_manager


# --- Optional Redis cache for active voice sessions ---
_redis_mgr = None
_redis_lock = threading.Lock()


def _try_get_redis():
    """Get RedisStorageManager or None if Redis unavailable."""
    global _redis_mgr
    if _redis_mgr is not None:
        return _redis_mgr
    with _redis_lock:
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
        except Exception as e:
            logger.debug("Redis unavailable", error=str(e))
    return None


# --- Optional PostgreSQL for long-term anketa storage ---
_postgres_mgr = None
_postgres_lock = threading.Lock()


def _try_get_postgres():
    """Get PostgreSQLStorageManager or None if PostgreSQL unavailable."""
    global _postgres_mgr
    if _postgres_mgr is not None:
        return _postgres_mgr
    with _postgres_lock:
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
        except Exception as e:
            logger.debug("PostgreSQL unavailable", error=str(e))
    return None


# ---------------------------------------------------------------------------
# API Integration - Update anketa via web server API
# ---------------------------------------------------------------------------
# CRITICAL: Voice agent runs as SEPARATE PROCESS from web server.
# SQLite in WAL mode ISOLATES writes between different connections.
# Therefore, voice agent MUST use HTTP API to update anketa, not direct DB writes.
# ---------------------------------------------------------------------------

async def _update_anketa_via_api(
    session_id: str,
    anketa_data: dict,
    anketa_md: str = None
) -> bool:
    """
    Update anketa via web server API instead of direct database write.

    This prevents SQLite WAL isolation issue where voice agent writes
    are not visible to web server (different processes = different connections).

    Returns:
        bool: True if update succeeded, False otherwise
    """
    server_url = os.getenv("WEB_SERVER_URL", "http://localhost:8000")
    url = f"{server_url}/api/session/{session_id}/anketa"

    payload = {
        "anketa_data": anketa_data,
        "anketa_md": anketa_md
    }

    try:
        client = await _get_http_client()
        response = await client.put(url, json=payload)

        if response.status_code == 200:
            logger.info(
                "anketa_updated_via_api",
                session_id=session_id,
                fields_count=len(anketa_data)
            )
            return True
        else:
            logger.warning(
                "anketa_api_update_failed",
                session_id=session_id,
                status_code=response.status_code,
                response=response.text[:200]  # R9-06: Truncate to avoid logging sensitive details
            )
            return False

    except Exception as e:
        logger.error(
            "anketa_api_update_error",
            session_id=session_id,
            error=str(e),
            traceback=traceback.format_exc()
        )
        return False


async def _update_dialogue_via_api(
    session_id: str,
    dialogue_history: list,
    duration_seconds: float,
    status: str = None
) -> bool:
    """
    Update dialogue history via web server API instead of direct database write.

    Same pattern as _update_anketa_via_api — prevents SQLite WAL isolation issue
    where voice agent writes are not visible to web server.
    """
    server_url = os.getenv("WEB_SERVER_URL", "http://localhost:8000")
    url = f"{server_url}/api/session/{session_id}/dialogue"

    payload = {
        "dialogue_history": dialogue_history,
        "duration_seconds": duration_seconds,
    }
    if status:
        payload["status"] = status

    try:
        client = await _get_http_client()
        response = await client.put(url, json=payload)

        if response.status_code == 200:
            logger.info(
                "dialogue_updated_via_api",
                session_id=session_id,
                messages=len(dialogue_history),
            )
            return True
        else:
            logger.warning(
                "dialogue_api_update_failed",
                session_id=session_id,
                status_code=response.status_code,
                response=response.text[:200]  # R9-06: Truncate to avoid logging sensitive details
            )
            return False

    except Exception as e:
        logger.error(
            "dialogue_api_update_error",
            session_id=session_id,
            error=str(e),
        )
        # Fallback to direct DB write
        try:
            _session_mgr.update_dialogue(
                session_id,
                dialogue_history=dialogue_history,
                duration_seconds=duration_seconds,
                status=status,
            )
            logger.info("dialogue_saved_via_direct_db_fallback", session_id=session_id)
            return True
        except Exception as db_err:
            logger.error("dialogue_direct_db_fallback_failed", error=str(db_err))
            return False


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

        # Inject into agent instructions (R19-02: Use _update_instructions_safe for buffering)
        if agent_session is not None:
            current = getattr(consultation, '_latest_instructions', None) \
                or getattr(getattr(agent_session, '_activity', None), 'instructions', '') \
                or get_system_prompt()
            updated = f"{current}\n\n### Данные исследования:\n{research_context}"
            await _update_instructions_safe(consultation, agent_session, updated)
            anketa_log.info(
                "research_injected",
                session_id=session_id,
                sources=result.sources_used,
            )
    except Exception as e:
        anketa_log.warning("background_research_failed", error=str(e))


def _detect_consultation_phase(
    message_count: int,
    completion_rate: float,
    review_started: bool,
) -> str:
    """
    Determine consultation phase from heuristics.

    Phases map to kb_context.yaml sections:
    - "discovery"   — messages < 8, completion < 0.15
    - "analysis"    — messages 8-14, completion 0.15-0.35
    - "proposal"    — messages 14-20, completion 0.35-0.50
    - "refinement"  — completion >= 0.50 or review_started
    """
    if review_started or completion_rate >= 0.50:
        return "refinement"
    if completion_rate >= 0.35 or message_count >= 14:
        return "proposal"
    if completion_rate >= 0.15 or message_count >= 8:
        return "analysis"
    return "discovery"


def _merge_anketa_data(user_data: dict, extracted_data: dict) -> dict:
    """
    Объединить данные из БД (ручные правки) с данными из экстракции.

    Приоритет у ручных правок пользователя (user_data).
    Если поле заполнено пользователем, сохраняем его значение.
    Если поле пустое в user_data, берем из extracted_data.

    Args:
        user_data: Данные из БД (могут содержать ручные правки)
        extracted_data: Свежие данные из DeepSeek экстракции

    Returns:
        Объединенные данные с приоритетом ручных правок
    """
    merged = extracted_data.copy()

    for key, user_value in user_data.items():
        # Если пользователь заполнил поле вручную, сохраняем его значение
        if user_value is not None:
            # Для строк: проверяем что не пустая
            if isinstance(user_value, str) and user_value.strip():
                merged[key] = user_value
            # Для списков: проверяем что не пустой
            elif isinstance(user_value, list) and len(user_value) > 0:
                merged[key] = user_value
            # Для других типов (числа, bool, dict)
            elif not isinstance(user_value, (str, list)):
                merged[key] = user_value

    # ===== FIX #2: Sync contact fields (phone/email ↔ contact_phone/contact_email) =====
    # phone → contact_phone
    if merged.get('phone') and not merged.get('contact_phone'):
        merged['contact_phone'] = merged['phone']
    # contact_phone → phone (reverse sync)
    if merged.get('contact_phone') and not merged.get('phone'):
        merged['phone'] = merged['contact_phone']

    # email → contact_email
    if merged.get('email') and not merged.get('contact_email'):
        merged['contact_email'] = merged['email']
    # contact_email → email (reverse sync)
    if merged.get('contact_email') and not merged.get('email'):
        merged['email'] = merged['contact_email']

    return merged


def _check_required_fields(anketa_data: dict) -> bool:
    """
    Проверить заполнение обязательных полей для перехода в REVIEW.

    v5.0: Все поля обязательны (15 полей).
    Contact fields теперь REQUIRED.
    """
    required = {
        # Блок 1: Компания (3 поля)
        "company_name": anketa_data.get("company_name"),
        "industry": anketa_data.get("industry"),
        "business_description": anketa_data.get("business_description"),

        # Блок 2: Услуги (3 поля)
        "services": anketa_data.get("services"),
        "current_problems": anketa_data.get("current_problems"),
        "business_goals": anketa_data.get("business_goals"),

        # Блок 3: Агент (3 поля)
        "agent_name": anketa_data.get("agent_name"),
        "agent_purpose": anketa_data.get("agent_purpose"),
        "agent_functions": anketa_data.get("agent_functions"),

        # Блок 4: Контакты (3 поля) - v5.0: ОБЯЗАТЕЛЬНЫ
        "contact_name": anketa_data.get("contact_name"),
        "contact_phone": anketa_data.get("contact_phone") or anketa_data.get("phone"),
        "contact_email": anketa_data.get("contact_email") or anketa_data.get("email"),

        # Блок 5: Дополнительно (3 поля)
        "voice_gender": anketa_data.get("voice_gender"),
        "voice_tone": anketa_data.get("voice_tone"),
        "call_direction": anketa_data.get("call_direction"),
    }

    # R10-01: Skip schema defaults — fields with unchanged defaults are not required
    from src.anketa.schema import FinalAnketa
    # Pydantic v2 wraps _-prefixed attrs in ModelPrivateAttr; unwrap via .default
    _raw = getattr(FinalAnketa, '_SCHEMA_DEFAULTS', {})
    schema_defaults = _raw if isinstance(_raw, dict) else getattr(_raw, 'default', {})

    for field_name, value in required.items():
        # Schema defaults are optional — skip them entirely
        if field_name in schema_defaults:
            continue
        # R24-11: Explicit type checks (consistent with completion_rate)
        if isinstance(value, list):
            if len(value) == 0:
                return False
        elif isinstance(value, str):
            if not value.strip():
                return False
        elif not value:
            return False

    return True


def _compute_completion_from_dict(anketa_data: dict) -> float:
    """Compute completion rate from merged anketa dict (mirrors FinalAnketa.completion_rate).

    Uses the same 15 required fields and schema defaults logic as the Pydantic model,
    but works on raw dict data after accumulative merge.
    """
    from src.anketa.schema import FinalAnketa
    _raw = getattr(FinalAnketa, '_SCHEMA_DEFAULTS', {})
    schema_defaults = _raw if isinstance(_raw, dict) else getattr(_raw, 'default', {})

    required_keys = [
        "company_name", "industry", "business_description",
        "services", "current_problems", "business_goals",
        "agent_name", "agent_purpose", "agent_functions",
        "contact_name", "contact_phone", "contact_email",
        "voice_gender", "voice_tone", "call_direction",
    ]

    filled = 0
    defaulted = 0
    for key in required_keys:
        v = anketa_data.get(key)
        # Contact field aliasing
        if key == "contact_phone" and not v:
            v = anketa_data.get("phone")
        if key == "contact_email" and not v:
            v = anketa_data.get("email")

        if key in schema_defaults and v == schema_defaults[key]:
            defaulted += 1
            continue
        if (isinstance(v, list) and len(v) > 0) or \
           (isinstance(v, str) and v and v.strip()) or \
           (v is not None and not isinstance(v, (str, list))):
            filled += 1

    effective_total = max(len(required_keys) - defaulted, 1)
    return filled / effective_total


# Human-readable labels for missing fields reminder
_FIELD_LABELS = {
    # Блок 1: Компания
    "company_name": "название компании (конкретный бренд)",
    "industry": "отрасль",
    "specialization": "специализация",
    "business_description": "описание деятельности",
    "business_type": "тип бизнеса (B2B/B2C)",
    "website": "сайт компании",
    # Блок 2: Услуги
    "services": "услуги/продукты",
    "client_types": "типы клиентов",
    "current_problems": "текущие проблемы/боли",
    "business_goals": "цели автоматизации",
    # Блок 3: Агент
    "agent_name": "имя агента",
    "agent_purpose": "назначение агента",
    "agent_functions": "задачи для автоматизации",
    "integrations": "интеграции с системами",
    "voice_gender": "пол голоса агента",
    "voice_tone": "тон голоса агента",
    "call_direction": "направление звонков",
    "working_hours": "часы работы",
    "transfer_conditions": "условия перевода на оператора",
    # Блок 4: Контакты
    "contact_name": "имя контактного лица",
    "contact_role": "должность",
    "contact_phone": "телефон",
    "contact_email": "email",
    # Блок 5: Дополнительно
    "constraints": "ограничения",
    "compliance_requirements": "требования регулятора",
    "call_volume": "объём звонков",
    "budget": "бюджет",
    "timeline": "сроки внедрения",
    "additional_notes": "дополнительные заметки / особые требования",
    "language": "язык общения агента",
}


def _get_missing_fields(anketa_data: dict) -> List[str]:
    """
    Return list of human-readable labels for fields that are still empty.

    Checks ALL discovery+agent fields (not just required 15).
    This is used to inject a dynamic reminder into agent instructions.
    """
    missing = []
    for field, label in _FIELD_LABELS.items():
        value = anketa_data.get(field)
        # Also check alternate names for contact fields
        if field == "contact_phone":
            value = value or anketa_data.get("phone")
        elif field == "contact_email":
            value = value or anketa_data.get("email")

        is_empty = False
        if value is None:
            is_empty = True
        elif isinstance(value, str) and not value.strip():
            is_empty = True
        elif isinstance(value, list) and (len(value) == 0 or value == [""]):
            is_empty = True
        elif isinstance(value, dict) and len(value) == 0:
            is_empty = True

        if is_empty:
            missing.append(label)

    return missing


def _build_missing_fields_reminder(missing: List[str]) -> str:
    """Build a prompt injection reminding the agent about missing fields."""
    if not missing:
        return ""

    fields_list = "\n".join(f"  • {f}" for f in missing)
    return f"""

### ⚠️ НЕЗАПОЛНЕННЫЕ ПОЛЯ АНКЕТЫ ({len(missing)} из {len(_FIELD_LABELS)}):

СТОП! Ты ещё НЕ собрал следующую информацию от клиента:
{fields_list}

ОБЯЗАТЕЛЬНО задай вопросы по этим полям ПРЕЖДЕ чем переходить к проверке анкеты!
НЕ ПРЕДЛАГАЙ проверить анкету, пока не соберёшь хотя бы 25 из {len(_FIELD_LABELS)} полей.
Задавай вопросы ЕСТЕСТВЕННО, по 1-2 за раз, НЕ перечисляй все сразу.
"""


# ---- Interview mode field labels ----
_INTERVIEW_FIELD_LABELS = {
    # Профиль респондента
    "contact_name": "имя респондента",
    "contact_role": "должность/роль",
    "company_name": "организация респондента",
    "contact_phone": "телефон",
    "contact_email": "email",
    "interviewee_industry": "отрасль респондента",
    "interviewee_context": "контекст/бэкграунд респондента",
    # Структура интервью
    "interview_title": "тема интервью",
    "interview_type": "тип интервью",
    "target_topics": "целевые темы для обсуждения",
    # Контент
    "qa_pairs": "вопросы и ответы",
    "detected_topics": "обнаруженные темы",
    "key_quotes": "ключевые цитаты",
}


def _get_missing_interview_fields(anketa_data: dict) -> List[str]:
    """Return list of human-readable labels for empty interview fields."""
    missing = []
    for field, label in _INTERVIEW_FIELD_LABELS.items():
        value = anketa_data.get(field)

        is_empty = False
        if value is None:
            is_empty = True
        elif isinstance(value, str) and not value.strip():
            is_empty = True
        elif isinstance(value, list) and (len(value) == 0 or value == [""]):
            is_empty = True

        if is_empty:
            missing.append(label)

    return missing


def _build_missing_interview_fields_reminder(missing: List[str]) -> str:
    """Build a prompt injection reminding the interviewer about missing info."""
    if not missing:
        return ""

    fields_list = "\n".join(f"  • {f}" for f in missing)
    return f"""

### ⚠️ НЕСОБРАННАЯ ИНФОРМАЦИЯ ({len(missing)} из {len(_INTERVIEW_FIELD_LABELS)}):

Ты ещё НЕ собрал следующую информацию от респондента:
{fields_list}

ОБЯЗАТЕЛЬНО задай вопросы по этим пунктам ПРЕЖДЕ чем переходить к резюме!
НЕ ПРЕДЛАГАЙ подводить итоги, пока не соберёшь хотя бы 10 из {len(_INTERVIEW_FIELD_LABELS)} пунктов.
Задавай вопросы ЕСТЕСТВЕННО, по одному за раз.
"""


def _filter_review_phase(dialogue_history: List[Dict]) -> List[Dict]:
    """
    Исключить review phase из extraction.

    Review phase = когда пользователь комментирует состояние анкеты:
    - "не заполнено", "пустое поле", "вы не спросили", "смотрю анкету"

    Это НЕ бизнес-данные, это meta-feedback!

    Returns:
        Filtered dialogue без review phase messages
    """
    review_keywords = [
        'не заполнен', 'не заполню', 'пуст', 'вы не спросили', 'не спрашивали',
        'смотрю анкету', 'проверяю анкету', 'должность почему-то',
        'требования регулятора я вижу', 'объем звонков не заполнен',
        'поле не заполнено', 'сроки не заполнены', 'примечания не заполнены',
        'тип бизнеса вы не заполнили', 'контактное лицо не заполнено'
    ]

    filtered = []
    review_started = False
    non_review_streak = 0  # R4-31: count consecutive non-review messages
    _buffered_msg = None  # R14-09: buffer first non-review msg after review phase

    for msg in dialogue_history:
        content_lower = msg.get('content', '').lower()

        # Detect review phase start
        if any(kw in content_lower for kw in review_keywords):
            if not review_started:
                logger.debug("review_phase_detected", message=content_lower[:100])
            review_started = True
            non_review_streak = 0
            continue  # Skip this message

        # If review started, wait for 2 consecutive non-review messages to exit
        # R14-09: Buffer first non-review message and include it when review exits
        if review_started:
            non_review_streak += 1
            if non_review_streak == 1:
                _buffered_msg = msg  # Buffer first non-review message
            if non_review_streak >= 2:
                # Back to normal dialogue — include BOTH buffered and current messages
                review_started = False
                if _buffered_msg is not None:
                    filtered.append(_buffered_msg)
                    _buffered_msg = None
                filtered.append(msg)
            continue

        filtered.append(msg)

    # R16-03: Flush buffered message if dialogue ended mid-review with only 1 non-review msg
    if _buffered_msg is not None:
        filtered.append(_buffered_msg)

    if review_started and filtered:
        logger.info("review_phase_filtered", original_count=len(dialogue_history), filtered_count=len(filtered))

    return filtered


async def _update_instructions_safe(
    consultation: VoiceConsultationSession,
    agent_session: Optional[AgentSession],
    new_instructions: str,
):
    """Update agent instructions, buffering during speech to avoid interruption (P1 fix).

    R14-03: Also stores the latest desired instructions in consultation so that
    subsequent callers within the same extraction cycle can read the most recent
    value instead of stale activity.instructions (which won't reflect buffered updates).
    """
    activity = getattr(agent_session, '_activity', None)
    if not activity or not hasattr(activity, 'update_instructions'):
        return
    # R14-03: Track the latest desired instructions regardless of buffering
    consultation._latest_instructions = new_instructions
    if consultation._agent_speaking:
        consultation._pending_instructions = new_instructions
        anketa_log.debug("instructions_buffered_during_speech")
    else:
        await activity.update_instructions(new_instructions)


async def _extract_and_update_anketa(
    consultation: VoiceConsultationSession,
    session_id: str,
    agent_session: Optional[AgentSession] = None,
):
    """Extract anketa from current dialogue and update in DB.

    v5.0: Uses sliding window for performance optimization.
    - Early conversation (< 12 msgs): full dialogue
    - Later (>= 12 msgs): last 12 messages only

    Also injects industry KB context into the voice agent on first extraction
    (when industry can be detected from dialogue).
    """
    import time
    _semaphore_acquired = False

    # R23-01: Per-session circuit breaker (was global, blocked ALL sessions on single failure)
    if time.time() < consultation._extraction_backoff_until:
        anketa_log.debug(
            "extraction_backoff_active",
            session_id=session_id,
            remaining=round(consultation._extraction_backoff_until - time.time()),
        )
        return

    try:
        dialogue_history = consultation.dialogue_history

        # v5.0: КРИТИЧНО - минимум 4 сообщения для quality extraction
        if len(dialogue_history) < 4:
            anketa_log.debug(
                "extraction_skipped_insufficient_messages",
                session_id=session_id,
                message_count=len(dialogue_history),
            )
            return

        # ===== FIX #4: FILTER REVIEW PHASE =====
        dialogue_filtered = _filter_review_phase(dialogue_history)

        # ===== SLIDING WINDOW OPTIMIZATION =====
        import os

        try:
            WINDOW_SIZE = int(os.getenv('EXTRACTION_WINDOW_SIZE', '12'))
            WINDOW_SIZE = max(4, min(WINDOW_SIZE, 100))  # R26-09: 4 <= window <= 100
        except (ValueError, TypeError):
            WINDOW_SIZE = 12  # R18-08: Fallback on invalid env var

        dialogue_for_extraction = dialogue_filtered
        is_windowed = False

        if len(dialogue_filtered) > WINDOW_SIZE:
            dialogue_for_extraction = dialogue_filtered[-WINDOW_SIZE:]
            is_windowed = True
            anketa_log.debug(
                "using_sliding_window",
                session_id=session_id,
                total_messages=len(dialogue_history),
                filtered_messages=len(dialogue_filtered),
                window_size=WINDOW_SIZE,
            )

        # ===== EXTRACTION =====
        # P4.3: Acquire semaphore to limit concurrent LLM calls
        global _extraction_semaphore
        if _extraction_semaphore is None:
            _max_concurrent = int(os.getenv('MAX_CONCURRENT_EXTRACTIONS', '10'))
            _extraction_semaphore = asyncio.Semaphore(_max_concurrent)

        _semaphore_acquired = True
        await _extraction_semaphore.acquire()
        start_time = time.time()

        # Fetch document_context from DB if client uploaded files
        doc_context = None
        db_session = _session_mgr.get_session(session_id)

        # v5.0: Determine consultation type for routing
        _consultation_type = "consultation"
        if db_session and db_session.voice_config:
            _consultation_type = db_session.voice_config.get("consultation_type", "consultation")

        if db_session and db_session.document_context:
            try:
                from src.documents import DocumentContext
                doc_context = DocumentContext(**db_session.document_context)
            except Exception:
                pass  # Use dict fallback — extractor handles both

        # R4-18: Reuse cached extractor to avoid recreating LLM client per call
        # R17-04: Invalidate cache when llm_provider changes mid-session
        _llm_provider = None
        if db_session and db_session.voice_config:
            _llm_provider = db_session.voice_config.get("llm_provider")
        if (consultation._cached_extractor is None
                or consultation._cached_extractor_provider != _llm_provider):
            llm = create_llm_client(_llm_provider)
            consultation._cached_extractor = AnketaExtractor(llm)
            consultation._cached_extractor_provider = _llm_provider
        extractor = consultation._cached_extractor

        # v5.0: Use sliding window dialogue instead of full history
        anketa = await extractor.extract(
            dialogue_history=dialogue_for_extraction,  # ← SLIDING WINDOW
            duration_seconds=consultation.get_duration_seconds(),
            document_context=doc_context,
            consultation_type=_consultation_type,
            skip_expert_content=True,  # P2.2: Skip expert content in real-time (saves 2-5s)
        )

        # R22-07: Skip DB update if extraction returned a fallback with auto-generated values
        if getattr(anketa, '_is_fallback', None) is True:
            anketa_log.warning(
                "extraction_fallback_skipped",
                session_id=session_id,
                reason="fallback anketa would overwrite real data with auto-generated values",
            )
            return

        extraction_time = time.time() - start_time
        completion_rate = anketa.completion_rate()

        # v5.0 Phase 4: Enhanced performance monitoring
        anketa_log.info(
            "extraction_completed",
            session_id=session_id,
            extraction_time=round(extraction_time, 2),
            is_windowed=is_windowed,
            message_count=len(dialogue_for_extraction),
            total_dialogue_length=len(dialogue_history),
            model=getattr(extractor.llm, 'model', getattr(extractor.llm, 'deployment', 'unknown')),
            completion_rate=round(completion_rate, 2),
        )

        anketa_data = anketa.model_dump(mode="json")

        # ===== FIX #3: ACCUMULATIVE MERGE - preserve non-empty old values =====
        # Если новый extraction вернул пустое поле, но в БД оно заполнено → СОХРАНЯЕМ старое
        if db_session and db_session.anketa_data:
            old_anketa = db_session.anketa_data

            for key, old_value in old_anketa.items():
                new_value = anketa_data.get(key)

                # Если старое значение заполнено, а новое пустое → KEEP OLD
                old_is_filled = False
                new_is_filled = False

                # Check if old value is filled
                if isinstance(old_value, str):
                    old_is_filled = old_value.strip() != ''
                elif isinstance(old_value, list):
                    old_is_filled = len(old_value) > 0
                elif old_value is not None and old_value != {}:
                    old_is_filled = True

                # Check if new value is filled
                if isinstance(new_value, str):
                    new_is_filled = new_value.strip() != ''
                elif isinstance(new_value, list):
                    new_is_filled = len(new_value) > 0
                elif new_value is not None and new_value != {}:
                    new_is_filled = True

                # Preserve old if filled and new is empty
                if old_is_filled and not new_is_filled:
                    anketa_data[key] = old_value
                    anketa_log.debug(
                        "preserving_old_value",
                        session_id=session_id,
                        field=key,
                        reason="new_extraction_empty",
                    )

            # После accumulative merge, применяем merge с user edits
            anketa_data = _merge_anketa_data(old_anketa, anketa_data)
            anketa_log.debug(
                "anketa_merged_accumulative",
                session_id=session_id,
            )

        anketa_md = AnketaGenerator.render_markdown(anketa)

        # CRITICAL: Use API instead of direct DB write (voice agent = separate process)
        # SQLite WAL mode isolates writes between processes → use HTTP API
        await _update_anketa_via_api(session_id, anketa_data, anketa_md)
        consultation._last_extraction_time = time.time()  # R19-02: Track for finalize dedup

        # Note: update_metadata() is redundant - company_name/contact_name
        # are already in anketa_data and will be updated via API

        anketa_log.info(
            "periodic_anketa_extracted",
            session_id=session_id,
            company=anketa.company_name,
            has_documents=doc_context is not None,
        )

        # R23-01: Reset per-session circuit breaker on success
        consultation._extraction_consecutive_failures = 0

        # --- Launch background research if website detected ---
        if not consultation.research_done and anketa.website and _consultation_type != "interview":
            consultation.research_done = True  # set early to prevent duplicates
            industry_id_for_research = None
            try:
                mgr = _get_kb_manager()
                user_text_r = " ".join(
                    m.get("content", "") for m in consultation.dialogue_history
                    if m.get("role") == "user"
                )
                industry_id_for_research = mgr.detect_industry(user_text_r)
            except Exception as e:
                anketa_log.debug("industry_detection_for_research_failed", error=str(e))
            task = asyncio.create_task(_run_background_research(
                consultation, session_id, agent_session,
                website=anketa.website,
                industry=industry_id_for_research,
                company_name=anketa.company_name,
            ))
            _track_agent_task(task)  # R11-10: Prevent GC before completion
            def _research_done(t):
                if t.cancelled():
                    return
                exc = t.exception()
                if exc:
                    anketa_log.warning("background_research_failed", error=str(exc))
            task.add_done_callback(_research_done)
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
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }),
                )
            except Exception as e:
                anketa_log.debug("redis_cache_update_failed", error=str(e))

        # --- Inject/update industry KB context based on phase ---
        # v5.0: Skip KB enrichment for interview mode (interviewer should be neutral)
        if agent_session is not None and _consultation_type != "interview":
            try:
                # Detect industry once, cache in session
                if consultation.detected_profile is None:
                    from src.knowledge.country_detector import get_country_detector

                    user_text = " ".join(
                        m.get("content", "") for m in consultation.dialogue_history
                        if m.get("role") == "user"
                    )
                    manager = _get_kb_manager()
                    industry_id = manager.detect_industry(user_text)

                    if industry_id:
                        detector = get_country_detector()
                        phone = getattr(anketa, 'contact_phone', None)
                        region, country = detector.detect(
                            phone=phone,
                            dialogue_text=user_text,
                        )
                        if region and country:
                            profile = manager.loader.load_regional_profile(
                                region, country, industry_id
                            )
                        else:
                            profile = manager.get_profile(industry_id)
                        consultation.detected_profile = profile
                        consultation.detected_industry_id = industry_id

                # Detect phase and re-inject KB on phase change
                if consultation.detected_profile:
                    new_phase = _detect_consultation_phase(
                        message_count=len(consultation.dialogue_history),
                        completion_rate=anketa.completion_rate() if anketa else 0.0,
                        review_started=consultation.review_started,
                    )

                    if new_phase != consultation.current_phase or not consultation.kb_enriched:
                        consultation.current_phase = new_phase
                        builder = EnrichedContextBuilder(_get_kb_manager())
                        voice_context = builder.build_for_voice_full(
                            consultation.dialogue_history,
                            profile=consultation.detected_profile,
                            phase=new_phase,
                        )
                        if voice_context:
                            base_prompt = get_system_prompt()
                            enriched = f"{base_prompt}\n\n### Контекст отрасли ({new_phase}):\n{voice_context}"
                            await _update_instructions_safe(consultation, agent_session, enriched)
                            consultation.kb_enriched = True
                            anketa_log.info(
                                "KB context injected",
                                session_id=session_id,
                                industry=consultation.detected_industry_id,
                                phase=new_phase,
                            )
            except Exception as e:
                anketa_log.warning("KB injection failed (non-fatal)", error=str(e))

        # --- Missing fields reminder: inject dynamic list into agent instructions ---
        if not consultation.review_started and agent_session is not None:
            try:
                if _consultation_type == "interview":
                    # Interview mode: use interview-specific fields
                    missing = _get_missing_interview_fields(anketa_data)
                    if missing:
                        reminder = _build_missing_interview_fields_reminder(missing)
                        marker = "### ⚠️ НЕСОБРАННАЯ ИНФОРМАЦИЯ"
                    else:
                        reminder = ""
                        marker = None
                else:
                    # Consultation mode: use consultation-specific fields
                    missing = _get_missing_fields(anketa_data)
                    if missing:
                        reminder = _build_missing_fields_reminder(missing)
                        marker = "### ⚠️ НЕЗАПОЛНЕННЫЕ ПОЛЯ АНКЕТЫ"
                    else:
                        reminder = ""
                        marker = None

                if reminder:
                    activity = getattr(agent_session, '_activity', None)
                    if activity and hasattr(activity, 'update_instructions'):
                        # R14-03: Use latest tracked instructions (may include buffered KB update)
                        # instead of stale activity.instructions
                        current_instructions = getattr(consultation, '_latest_instructions', None) \
                            or getattr(activity, 'instructions', '') or ''
                        # Strip previous reminder if present (both markers)
                        for m in ["### ⚠️ НЕЗАПОЛНЕННЫЕ ПОЛЯ АНКЕТЫ", "### ⚠️ НЕСОБРАННАЯ ИНФОРМАЦИЯ"]:
                            if m in current_instructions:
                                current_instructions = current_instructions[:current_instructions.index(m)].rstrip()
                        updated = current_instructions + reminder
                        await _update_instructions_safe(consultation, agent_session, updated)
                        anketa_log.info(
                            "missing_fields_reminder_injected",
                            session_id=session_id,
                            mode=_consultation_type,
                            missing_count=len(missing),
                            missing_fields=missing[:5],  # Log first 5 for brevity
                        )
            except Exception as e:
                anketa_log.warning("missing_fields_reminder_failed", error=str(e))

        # --- Review phase: switch to anketa verification when ready ---
        if agent_session is not None:
            try:
                rate = anketa.completion_rate()
                msg_count = len(consultation.dialogue_history)

                # RECOVERY: если review запущен но completion_rate упал (пользователь удалил поля)
                # → вернуться в discovery mode
                if consultation.review_started and rate < 0.7:
                    consultation.review_started = False
                    anketa_log.info(
                        "review_phase_recovery",
                        session_id=session_id,
                        completion_rate=rate,
                        reason="completion_rate dropped below 0.7",
                    )
                    # Re-inject base prompt with KB context
                    activity = getattr(agent_session, '_activity', None)
                    if activity and hasattr(activity, 'update_instructions'):
                        base_prompt = get_system_prompt()
                        if consultation.kb_enriched and consultation.detected_profile:
                            builder = EnrichedContextBuilder(_get_kb_manager())
                            voice_context = builder.build_for_voice_full(
                                consultation.dialogue_history,
                                profile=consultation.detected_profile,
                                phase=consultation.current_phase,
                            )
                            if voice_context:
                                base_prompt = f"{base_prompt}\n\n### Контекст отрасли ({consultation.current_phase}):\n{voice_context}"
                        await _update_instructions_safe(consultation, agent_session, base_prompt)

                # Переход в REVIEW только если:
                # 1. completion_rate >= 90% (v5.0: почти все поля заполнены = 14/15)
                # 2. Минимум 16 сообщений
                # 3. ВСЕ обязательные поля заполнены (15 полей в v5.0, включая контакты)
                if not consultation.review_started:
                    required_fields_filled = _check_required_fields(anketa_data)

                    if rate >= 0.9 and msg_count >= 16 and required_fields_filled:
                        consultation.review_started = True
                        summary = format_anketa_for_voice(anketa_data)
                        review_prompt = get_review_system_prompt(summary)

                        # FIX B1: APPEND review instructions to base prompt instead of replacing
                        # This preserves anti-hallucination rules, KB context, and platform knowledge
                        activity = getattr(agent_session, '_activity', None)
                        if activity and hasattr(activity, 'update_instructions'):
                            # R27-03: Prefer buffered instructions over stale activity.instructions
                            current_instructions = getattr(consultation, '_latest_instructions', None) \
                                or getattr(activity, 'instructions', None) or get_system_prompt()
                            # Strip any previous missing fields reminder
                            for m in ["### ⚠️ НЕЗАПОЛНЕННЫЕ ПОЛЯ АНКЕТЫ", "### ⚠️ НЕСОБРАННАЯ ИНФОРМАЦИЯ"]:
                                if m in current_instructions:
                                    current_instructions = current_instructions[:current_instructions.index(m)].rstrip()
                            # Append review mode instructions to existing prompt
                            combined_prompt = current_instructions + "\n\n" + review_prompt
                            await _update_instructions_safe(consultation, agent_session, combined_prompt)
                            await agent_session.generate_reply(
                                user_input="[Начни проверку анкеты. Зачитай первый пункт и спроси подтверждение.]"
                            )
                            anketa_log.info(
                                "review_phase_started",
                                session_id=session_id,
                                completion_rate=rate,
                                message_count=msg_count,
                            )
                    elif msg_count >= 16:
                        # Логируем почему НЕ перешли в REVIEW (для отладки)
                        anketa_log.debug(
                            "review_phase_not_ready",
                            session_id=session_id,
                            completion_rate=rate,
                            message_count=msg_count,
                            required_fields_filled=required_fields_filled,
                        )
            except Exception as e:
                anketa_log.warning("review_phase_start_failed", error=str(e))

    except Exception as e:
        # R23-01: Per-session exponential backoff (2, 4, 8, 16, 32, 60s max)
        consultation._extraction_consecutive_failures += 1
        backoff = min(60, 2 ** consultation._extraction_consecutive_failures)
        consultation._extraction_backoff_until = time.time() + backoff
        anketa_log.error(
            "periodic_anketa_extraction_failed",
            error=str(e),
            consecutive_failures=consultation._extraction_consecutive_failures,
            backoff_seconds=backoff,
            exc_info=True,
        )
    finally:
        # P4.3: Release semaphore only if we acquired it
        if _extraction_semaphore is not None and _semaphore_acquired:
            _extraction_semaphore.release()


async def _finalize_and_save(
    consultation: VoiceConsultationSession,
    session_id: Optional[str],
):
    """Final anketa extraction, filesystem save, and DB update."""
    # R25-01: Server-side deduplication — if session already finalized by another agent,
    # skip to prevent duplicate notifications/writes.
    # F7.3: Allow finalization for 'confirmed' — user may confirm mid-conversation,
    # and we still need to run final extraction to capture last dialogue data.
    if session_id:
        pre_check = _session_mgr.get_session(session_id)
        if pre_check and pre_check.status in (
            SessionStatus.DECLINED.value, SessionStatus.REVIEWING.value
        ):
            session_log.info(
                "finalize_already_done",
                session_id=session_id,
                status=pre_check.status,
            )
            return

    await finalize_consultation(consultation)

    if not session_id:
        return

    # ✅ FIX БАГ #2: Re-read session to get current status (may have been paused)
    fresh_session = _session_mgr.get_session(session_id)
    if not fresh_session:
        # R9-20: Session was deleted — don't finalize
        session_log.warning("finalize_session_not_found", session_id=session_id)
        return
    current_status = SessionStatus(fresh_session.status)

    # Only update to "reviewing" if status is still "active"
    # Don't overwrite "paused", "confirmed", "declined"
    if current_status == SessionStatus.ACTIVE:
        final_status = SessionStatus.REVIEWING
    else:
        final_status = current_status

    # Save dialogue + duration + status via HTTP API (not direct DB write)
    # Voice agent = separate process → SQLite WAL isolates writes
    await _update_dialogue_via_api(
        session_id,
        dialogue_history=consultation.dialogue_history,
        duration_seconds=consultation.get_duration_seconds(),
        status=final_status.value,  # ✅ Preserve paused/confirmed/declined
    )

    # R24-09: Also attempt final extraction on error (DB-targeted extraction is independent)
    if consultation.runtime_status in (RuntimeStatus.COMPLETED, RuntimeStatus.ERROR):
        # R19-02: Skip redundant final extraction if last real-time extraction
        # was within 10 seconds — data is already fresh enough
        import time as _t
        _since_last = _t.time() - consultation._last_extraction_time
        if _since_last < 10.0:
            anketa_log.info(
                "finalize_extraction_skipped_recent",
                session_id=session_id,
                seconds_since_last=round(_since_last, 1),
            )
        else:
            try:
                # Fetch document_context if client uploaded files
                doc_context = None
                session = _session_mgr.get_session(session_id)
                # v5.0: Determine consultation type for extraction routing
                _fin_ct = "consultation"
                if session and session.voice_config:
                    _fin_ct = session.voice_config.get("consultation_type", "consultation")
                if session and session.document_context:
                    try:
                        from src.documents import DocumentContext
                        doc_context = DocumentContext(**session.document_context)
                    except Exception:
                        pass

                # R10-11: Reuse cached extractor if available
                if consultation._cached_extractor:
                    extractor = consultation._cached_extractor
                else:
                    _fin_llm_provider = None
                    if session and session.voice_config:
                        _fin_llm_provider = session.voice_config.get("llm_provider")
                    llm = create_llm_client(_fin_llm_provider)
                    extractor = AnketaExtractor(llm)

                anketa = await extractor.extract(
                    dialogue_history=consultation.dialogue_history,
                    duration_seconds=consultation.get_duration_seconds(),
                    document_context=doc_context,
                    consultation_type=_fin_ct,
                )

                # R22-07: Skip DB update if extraction returned a fallback
                if getattr(anketa, '_is_fallback', None) is True:
                    anketa_log.warning(
                        "finalize_extraction_fallback_skipped",
                        session_id=session_id,
                    )
                else:
                    anketa_data = anketa.model_dump(mode="json")
                    anketa_md = AnketaGenerator.render_markdown(anketa)

                    # CRITICAL: Use API instead of direct DB write (voice agent = separate process)
                    await _update_anketa_via_api(session_id, anketa_data, anketa_md)

            except Exception as e:
                anketa_log.warning("final_anketa_extraction_failed", error=str(e))

    session_log.info(
        "session_finalized_in_db",
        session_id=session_id,
        status=final_status.value,  # R12-13: Use actual status, not hardcoded
    )

    # Load fresh session for downstream pipelines (notifications, learning, PostgreSQL)
    session = _session_mgr.get_session(session_id)
    if not session:
        session_log.warning("finalize_session_lost_after_update", session_id=session_id)
        return

    # --- Send notifications only for confirmed/reviewing sessions (R19-07) ---
    if final_status in (SessionStatus.CONFIRMED, SessionStatus.REVIEWING):
        try:
            from src.notifications.manager import NotificationManager
            notifier = NotificationManager()
            await notifier.on_session_confirmed(session)
            anketa_log.info("notification_sent", session_id=session_id, status=final_status.value)
        except Exception as e:
            anketa_log.warning("notification_failed", error=str(e))
    else:
        anketa_log.debug("notification_skipped", session_id=session_id, status=final_status.value)

    # --- Record learning for industry KB ---
    try:
        manager = _get_kb_manager()
        builder = EnrichedContextBuilder(manager)
        industry_id = builder.get_industry_id(consultation.dialogue_history)
        if industry_id and session.anketa_data:
            company = session.company_name or "N/A"
            # FIX: Handle Mock objects and prevent StopIteration in async context
            try:
                anketa_values = list(session.anketa_data.values()) if hasattr(session.anketa_data, 'values') else []
                filled = sum(1 for v in anketa_values if v and v != [] and v != "")
            except (StopIteration, RuntimeError):
                filled = 0  # Fallback if iteration fails

            # R18-03: Use consultation duration (accurate) instead of stale DB session.duration_seconds
            _duration_secs = consultation.get_duration_seconds()
            insight = (
                f"Голосовая сессия {session_id}: {company}, "
                f"заполнено полей: {filled}, "
                f"длительность: {round(_duration_secs / 60, 1)} мин"
            )
            manager.record_learning(industry_id, insight, f"voice_{session_id}")

            # Dual-write to PostgreSQL (fire-and-forget)
            pg_learning = _try_get_postgres()
            if pg_learning:
                try:
                    await pg_learning.save_learning(industry_id, insight, f"voice_{session_id}")
                except Exception:
                    pass  # Non-fatal: YAML is primary

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
                completed_at=datetime.now(timezone.utc),
                duration=consultation.get_duration_seconds(),  # R19-01: Use computed, not stale DB
                completeness_score=anketa_obj.completion_rate() if hasattr(anketa_obj, 'completion_rate') else None,
                status=final_status.value,  # R18-02: Use computed status, not stale DB read
            )
            anketa_log.info("postgres_saved", session_id=session_id)
        except Exception as e:
            anketa_log.warning("postgres_save_failed", error=str(e))

    # --- Remove from Redis hot cache ---
    redis_mgr = _try_get_redis()
    if redis_mgr:
        try:
            redis_mgr.client.delete(f"voice:session:{session_id}")
        except Exception as e:
            anketa_log.debug("redis_cache_cleanup_failed", error=str(e))


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
    # v5.0: Real-time extraction - removed message counter
    # FIX: Prevent duplicate extraction (race condition between 2 triggers)
    extraction_running = [False]  # mutable for closure
    last_extraction_time = [0.0]  # P3: throttle extraction interval

    # Create file-based logger for event debugging (only add handler once)
    import logging
    event_log = logging.getLogger("agent.events")
    from logging.handlers import RotatingFileHandler
    if not any(isinstance(h, (logging.FileHandler, RotatingFileHandler)) for h in event_log.handlers):
        fh = RotatingFileHandler("/tmp/agent_entrypoint.log", maxBytes=10*1024*1024, backupCount=3)
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
            # R25-09: Skip synthetic system prompts (bracket-wrapped instructions)
            # that leak into transcription from generate_reply() calls
            stripped = transcript.strip()
            if stripped.startswith('[') and stripped.endswith(']'):
                logger.debug("skipping_synthetic_prompt", preview=stripped[:60])
                return
            consultation.add_message("user", stripped)
            if db_backed and session_id:
                # v5.0: Real-time extraction - trigger на КАЖДОЕ user message
                # FIX: Skip if extraction already running (prevent duplication)
                if extraction_running[0]:
                    logger.debug("extraction_skipped_already_running", trigger="user_input")
                    return

                # P3: Throttle extraction to prevent excessive API calls
                # Skip throttle for early messages (< 8) to fill initial data quickly
                import time as _time
                _now = _time.time()
                _min_interval = float(os.getenv('MIN_EXTRACTION_INTERVAL', '10'))
                if (len(consultation.dialogue_history) >= 8
                        and _now - last_extraction_time[0] < _min_interval):
                    logger.debug(
                        "extraction_throttled",
                        trigger="user_input",
                        seconds_since_last=round(_now - last_extraction_time[0], 1),
                    )
                    return

                extraction_running[0] = True
                # R14-02: Set last_extraction_time AFTER extraction completes
                # (not before) to prevent rapid-fire retries after transient failures

                async def run_extraction():
                    try:
                        # R14-08: Timeout extraction to prevent indefinite blocking
                        # when DeepSeek API is degraded (default 180s * 3 retries = 540s)
                        _extraction_timeout = float(os.getenv('EXTRACTION_TIMEOUT', '60'))
                        await asyncio.wait_for(
                            _extract_and_update_anketa(consultation, session_id, session),
                            timeout=_extraction_timeout,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "extraction_timed_out",
                            trigger="user_input",
                            timeout=_extraction_timeout,
                            session_id=session_id,
                        )
                    except asyncio.CancelledError:
                        # R17-03: Explicit handling — task may be cancelled on shutdown
                        logger.info("extraction_cancelled", session_id=session_id)
                    except Exception as e:
                        logger.error("extraction_failed", error=str(e), trigger="user_input")
                    finally:
                        extraction_running[0] = False
                        last_extraction_time[0] = _time.time()

                _track_agent_task(asyncio.create_task(run_extraction()))

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

        # P1: Track speaking state for instruction buffering
        consultation._agent_speaking = (new_state == 'speaking')

        # P1: Apply buffered instructions when agent stops speaking
        if old_state == 'speaking' and new_state != 'speaking':
            if consultation._pending_instructions:
                pending = consultation._pending_instructions
                consultation._pending_instructions = None
                _track_agent_task(asyncio.create_task(
                    _update_instructions_safe(consultation, session, pending)
                ))  # R11-10: Prevent GC before completion
                anketa_log.debug("buffered_instructions_applied")

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
            session, extraction_running,
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

        # R18-03/R18-04: Removed redundant _update_dialogue_via_api call.
        # _finalize_and_save() already saves dialogue with correct final_status.
        # The old code caused: (1) double API call, (2) status race where "active"
        # from fresh_session could overwrite "reviewing" set by concurrent extraction.

        # P7.1: Close cached extractor's LLM httpx client to prevent connection leak
        if consultation._cached_extractor and hasattr(consultation._cached_extractor, 'llm'):
            llm_client = consultation._cached_extractor.llm
            if hasattr(llm_client, 'aclose'):
                async def _close_llm():
                    try:
                        await llm_client.aclose()
                    except Exception:
                        pass
                _track_agent_task(asyncio.create_task(_close_llm()))

        # B5: Shield finalization from cancellation during agent teardown
        # R18-01: Only finalize for DB-backed sessions (avoid wasted LLM extraction for standalone)
        # R23-08: Guard against concurrent finalization on rapid disconnect/reconnect
        if consultation._finalization_started:
            event_log.info("finalization_already_started, skipping duplicate")
            return
        consultation._finalization_started = True

        if db_backed and session_id:
            _track_agent_task(asyncio.create_task(asyncio.shield(_finalize_and_save(consultation, session_id))))
        elif len(consultation.dialogue_history) >= 2:
            # Standalone mode: still run finalization for local output
            _track_agent_task(asyncio.create_task(asyncio.shield(_finalize_and_save(consultation, None))))

    event_log.info("All event handlers registered successfully")


def _handle_conversation_item(
    event,
    consultation: VoiceConsultationSession,
    session_id: Optional[str],
    db_backed: bool,
    agent_session: Optional[AgentSession] = None,
    extraction_running: list = None,
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

        # v5.0: Extraction logic removed from here - only in on_user_input_transcribed now

    except Exception as e:
        logger.error(
            "AGENT: Failed to process conversation item",
            error=str(e),
            traceback=traceback.format_exc(),
        )


def _get_voice_id(voice_config: dict = None) -> str:
    """Map voice_gender setting to Azure OpenAI voice ID."""
    if not voice_config:
        return "alloy"
    gender = voice_config.get("voice_gender", "neutral")
    voice_map = {"male": "echo", "female": "shimmer", "neutral": "alloy"}
    return voice_map.get(gender, "alloy")


# Verbosity prompt prefixes — prepended to system prompt to adjust agent's response length.
# Must match exactly between _apply_verbosity_update (strip) and entrypoint (add).
_VERBOSITY_PREFIXES = {
    "concise": "ВАЖНО: Отвечай МАКСИМАЛЬНО кратко — 1-2 предложения + 1 вопрос. Без длинных вступлений.\n\n",
    "verbose": "ВАЖНО: Давай развёрнутые ответы с примерами и пояснениями. Объясняй подробно.\n\n",
}


def _get_verbosity_prompt_prefix(verbosity: str) -> str:
    """Return the verbosity instruction prefix for the given setting."""
    return _VERBOSITY_PREFIXES.get(verbosity, "")


async def _apply_verbosity_update(consultation, agent_session, new_verbosity: str, log):
    """Update agent instructions mid-session to reflect new verbosity setting.

    R17-05/R17-06: Uses _update_instructions_safe() for buffering during speech,
    and reads from consultation._latest_instructions for consistency.

    Strips the old verbosity prefix (if any) from current instructions,
    then prepends the new one. Preserves all other prompt content
    (KB context, resume context, review phase, etc.).
    """
    try:
        activity = getattr(agent_session, '_activity', None)
        if not activity or not hasattr(activity, 'update_instructions'):
            log.warning("verbosity update: no activity or update_instructions available")
            return

        # R17-06: Read from _latest_instructions (not stale activity.instructions)
        current = getattr(consultation, '_latest_instructions', None) \
            or getattr(activity, 'instructions', '') or ''

        # Strip old verbosity prefix if present
        for prefix in _VERBOSITY_PREFIXES.values():
            if current.startswith(prefix):
                current = current[len(prefix):]
                break

        # Prepend new verbosity prefix (empty for "normal")
        new_prefix = _get_verbosity_prompt_prefix(new_verbosity)
        new_instructions = new_prefix + current

        # R17-05: Use _update_instructions_safe for buffering during speech
        await _update_instructions_safe(consultation, agent_session, new_instructions)
        log.info(f"verbosity updated mid-session: {new_verbosity}")
    except Exception as e:
        log.warning(f"verbosity mid-session update failed (non-fatal): {e}")


def _apply_voice_config_update(realtime_model, config_state: dict, session_id: str, log, agent_session=None, consultation=None):
    """Re-read voice_config from DB and update RealtimeModel mid-session if changed.

    Called when room metadata changes (server signals reconnect) or client track is subscribed.
    Uses RealtimeModel.update_options() for speed/silence/voice (sync, sends session.update to Azure).
    Uses AgentActivity.update_instructions() for verbosity (async, scheduled via event loop).
    """
    try:
        if not session_id:
            return

        db_session = _session_mgr.get_session(session_id)
        if not db_session or not db_session.voice_config:
            return

        new_cfg = db_session.voice_config
        old_cfg = config_state.get("config") or {}

        new_silence = int(new_cfg.get("silence_duration_ms", 2000))
        old_silence = int(old_cfg.get("silence_duration_ms", 2000))
        new_speed = float(new_cfg.get("speech_speed", 1.0))
        old_speed = float(old_cfg.get("speech_speed", 1.0))
        new_voice = new_cfg.get("voice_gender", "neutral")
        old_voice = old_cfg.get("voice_gender", "neutral")
        new_verbosity = new_cfg.get("verbosity", "normal")
        old_verbosity = old_cfg.get("verbosity", "normal")

        log.info(
            f"voice_config diff: "
            f"silence={old_silence}->{new_silence}, "
            f"speed={old_speed}->{new_speed}, "
            f"voice={old_voice}->{new_voice}, "
            f"verbosity={old_verbosity}->{new_verbosity}"
        )

        if (new_silence == old_silence and new_speed == old_speed
                and new_voice == old_voice and new_verbosity == old_verbosity):
            log.info("voice_config unchanged on reconnect, no update needed")
            return

        # Sync updates: speed and silence → isolated RealtimeModel.update_options() calls.
        # voice_gender is NOT sent mid-session — Azure Realtime API locks voice after first audio output.
        # Isolated calls prevent one rejected parameter from blocking others.

        if new_speed != old_speed:
            new_speed = max(0.75, min(1.5, new_speed))
            try:
                realtime_model.update_options(speed=new_speed)
                log.info(f"voice_config updated mid-session (speed): {new_speed}")
            except Exception as e:
                log.warning(f"speed update_options failed: {e}")

        if new_silence != old_silence:
            new_silence = max(300, min(5000, new_silence))
            try:
                realtime_model.update_options(
                    turn_detection=TurnDetection(
                        type="server_vad",
                        threshold=0.9,
                        prefix_padding_ms=500,
                        silence_duration_ms=new_silence,
                    )
                )
                log.info(f"voice_config updated mid-session (silence): {new_silence}ms")
            except Exception as e:
                log.warning(f"silence update_options failed: {e}")

        if new_voice != old_voice:
            log.info(f"voice_gender changed {old_voice}->{new_voice} — skipped (Azure locks voice after first audio)")

        # Async update: verbosity → AgentActivity.update_instructions()
        if new_verbosity != old_verbosity and agent_session is not None:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                _track_agent_task(loop.create_task(_apply_verbosity_update(consultation, agent_session, new_verbosity, log)))  # R11-19
            except RuntimeError:
                log.warning("verbosity update skipped: no running event loop")

        config_state["config"] = new_cfg
    except Exception as e:
        log.warning(f"voice_config mid-session update failed (non-fatal): {e}")


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
    # v4.3: range extended to 300-5000ms (was 1500-6000), speech_speed added
    silence_ms = 2000  # default (was 4000)
    if voice_config and "silence_duration_ms" in voice_config:
        silence_ms = int(voice_config["silence_duration_ms"])
        silence_ms = max(300, min(5000, silence_ms))  # clamp to safe range

    # v4.3: speech_speed — audio playback speed multiplier (0.75-1.5)
    # Azure Realtime max is 1.5 — exceeding it rejects the ENTIRE session.update
    speech_speed = 1.0  # default
    if voice_config and "speech_speed" in voice_config:
        speech_speed = float(voice_config["speech_speed"])
        speech_speed = max(0.75, min(1.5, speech_speed))  # Azure max is 1.5

    model = lk_openai.realtime.RealtimeModel.with_azure(
        azure_deployment=azure_deployment,
        azure_endpoint=wss_endpoint,
        api_key=azure_api_key,
        api_version=azure_api_version,
        voice=_get_voice_id(voice_config),
        temperature=0.7,
        speed=speech_speed,
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
        speech_speed=speech_speed,
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
    # Debug logging to file (subprocess logs don't forward to parent, add handler once)
    # R14-05: Use RotatingFileHandler (same as agent.events) to avoid conflicts
    import logging
    from logging.handlers import RotatingFileHandler as _RFH
    debug_log = logging.getLogger("agent.entrypoint")
    if not any(isinstance(h, (logging.FileHandler, _RFH)) for h in debug_log.handlers):
        fh = _RFH("/tmp/agent_entrypoint.log", maxBytes=10*1024*1024, backupCount=3)
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
        # v5.0: Route prompt based on consultation_type
        consultation_type = voice_config.get("consultation_type", "consultation") if voice_config else "consultation"
        if consultation_type == "interview":
            prompt = get_prompt("voice/interviewer", "system_prompt")
        else:
            prompt = get_system_prompt()

        # v5.0: Verbosity injection — prepend instruction based on voice_config.
        # Uses _VERBOSITY_PREFIXES dict so mid-session _apply_verbosity_update() can
        # strip/replace the exact same prefix strings.
        if voice_config:
            verbosity = voice_config.get("verbosity", "normal")
            verbosity_prefix = _get_verbosity_prompt_prefix(verbosity)
            if verbosity_prefix:
                prompt = verbosity_prefix + prompt

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
        #
        # v4.3 — min_endpointing_delay proportional to silence_duration_ms:
        #   500ms→0.3s, 1000ms→0.6s, 2000ms→1.2s, 3000ms→1.8s, 4000ms→2.4s
        vc_silence = 2000
        if voice_config and "silence_duration_ms" in voice_config:
            vc_silence = int(voice_config["silence_duration_ms"])
        endpointing_delay = max(0.3, min(3.0, vc_silence / 1000 * 0.6))

        session = AgentSession(
            llm=realtime_model,
            allow_interruptions=True,
            min_interruption_duration=2.0,
            min_interruption_words=4,
            min_endpointing_delay=endpointing_delay,
            false_interruption_timeout=3.0,
            resume_false_interruption=True,
        )
        debug_log.info(
            "STEP 5/5: AgentSession created",
            extra={"min_endpointing_delay": endpointing_delay},
        )

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
                        "started_at": datetime.now(timezone.utc).isoformat(),
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
                        "started_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                debug_log.info(f"Session registered in PostgreSQL: {session_id}")
            except Exception as e:
                debug_log.warning(f"PostgreSQL registration failed (non-fatal): {e}")
    except Exception as e:
        debug_log.error(f"STEP 5/5 FAILED: {e}")
        raise

    # Track voice_config for mid-session updates (mutable dict for closure access)
    _voice_config_state = {"config": voice_config}

    # Add room event handlers for debugging participant/track connections
    @ctx.room.on("participant_connected")
    def on_participant_connected(participant):
        debug_log.info(f"ROOM EVENT: Participant connected: {participant.identity}")

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant):
        debug_log.info(f"ROOM EVENT: Track subscribed: {track.kind} from {participant.identity}")
        # v5.0: Re-read voice_config from DB when client reconnects (audio track re-subscribed).
        # This enables mid-session updates to speech_speed, silence_duration_ms, voice_gender, verbosity.
        if participant.identity.startswith("client-"):
            _apply_voice_config_update(realtime_model, _voice_config_state, session_id, debug_log, agent_session=session, consultation=consultation)

    @ctx.room.on("track_published")
    def on_track_published(publication, participant):
        debug_log.info(f"ROOM EVENT: Track published: {publication.kind} from {participant.identity}")

    @ctx.room.on("room_metadata_changed")
    def on_room_metadata_changed(old_metadata, new_metadata):
        """Triggered by server reconnect endpoint to signal voice_config change.

        The server updates room metadata with a config_version timestamp
        when a client reconnects. This is the primary mechanism for applying
        mid-session voice settings (speed, silence, voice gender, verbosity).

        v4.3: Also handles document_context_updated notifications when files are uploaded.
        """
        debug_log.info(f"ROOM EVENT: Room metadata changed: {old_metadata!r} -> {new_metadata!r}")

        # Handle document upload notification
        try:
            import json as _json
            metadata = _json.loads(new_metadata) if new_metadata else {}
            if metadata.get("document_context_updated"):
                # Re-load session to get fresh document_context
                if session_id:
                    fresh_session = _session_mgr.get_session(session_id)
                    if fresh_session and fresh_session.document_context:
                        debug_log.info(
                            "documents_uploaded_agent_notified",
                            session_id=session_id,
                            document_count=metadata.get("document_count", 0),
                            key_facts=metadata.get("key_facts_count", 0),
                        )
                        debug_log.info(f"Agent received document notification: {metadata}")

                        # F3.1: Inject document context into agent instructions
                        doc_ctx = fresh_session.document_context
                        doc_summary = None
                        if isinstance(doc_ctx, dict):
                            doc_summary = doc_ctx.get('summary') or doc_ctx.get('text', '')
                        elif hasattr(doc_ctx, 'summary'):
                            doc_summary = doc_ctx.summary

                        if doc_summary and session:
                            current_instr = getattr(consultation, '_latest_instructions', None) \
                                or getattr(getattr(session, '_activity', None), 'instructions', None) \
                                or ''
                            doc_block = f"\n\n### Документы клиента:\n{str(doc_summary)[:3000]}"
                            if "### Документы клиента:" not in current_instr:
                                updated_instr = current_instr + doc_block
                                _track_agent_task(asyncio.create_task(
                                    _update_instructions_safe(consultation, session, updated_instr)
                                ))
                                debug_log.info("document_context_injected_into_instructions")
        except Exception as e:
            debug_log.warning(f"Failed to handle document notification: {e}")

        # Handle voice_config updates
        _apply_voice_config_update(realtime_model, _voice_config_state, session_id, debug_log, agent_session=session, consultation=consultation)

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
