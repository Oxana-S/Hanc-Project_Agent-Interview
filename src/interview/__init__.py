"""Interview module — логика проведения интервью."""

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

__all__ = [
    "MaximumInterviewer",
    "InterviewPhase",
    "FieldStatus",
    "FieldPriority",
    "AnketaField",
    "CollectedInfo",
    "PhaseTransition",
    "ANKETA_FIELDS",
]
