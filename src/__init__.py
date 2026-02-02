"""
Voice Interviewer — модуль для проведения AI-интервью.

Экспорты:
- models: базовые модели данных
- interview: логика интервью (Maximum режим)
- storage: хранение данных (Redis, PostgreSQL)
- llm: LLM клиенты (DeepSeek)
- cli: CLI интерфейсы
"""

from src.models import (
    InterviewPattern,
    InterviewStatus,
    QuestionStatus,
    AnalysisStatus,
    InterviewContext,
    CompletedAnketa,
)
from src.interview.maximum import MaximumInterviewer
from src.interview.phases import (
    InterviewPhase,
    FieldStatus,
    FieldPriority,
    AnketaField,
    CollectedInfo,
    PhaseTransition,
    ANKETA_FIELDS,
)
from src.storage.redis import RedisStorageManager
from src.storage.postgres import PostgreSQLStorageManager
from src.llm.deepseek import DeepSeekClient

__all__ = [
    # Models
    "InterviewPattern",
    "InterviewStatus",
    "QuestionStatus",
    "AnalysisStatus",
    "InterviewContext",
    "CompletedAnketa",
    # Interview
    "MaximumInterviewer",
    "InterviewPhase",
    "FieldStatus",
    "FieldPriority",
    "AnketaField",
    "CollectedInfo",
    "PhaseTransition",
    "ANKETA_FIELDS",
    # Storage
    "RedisStorageManager",
    "PostgreSQLStorageManager",
    # LLM
    "DeepSeekClient",
]
