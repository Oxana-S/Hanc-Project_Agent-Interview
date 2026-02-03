"""
Consultant Interviewer Module.

AI-консультант с 4 фазами:
- DISCOVERY: свободный диалог
- ANALYSIS: анализ бизнеса
- PROPOSAL: предложение решения
- REFINEMENT: заполнение анкеты

v3.1: Added ConsultationConfig for time optimization.
"""

from src.consultant.phases import ConsultantPhase
from src.consultant.models import (
    BusinessAnalysis,
    PainPoint,
    Opportunity,
    ProposedSolution,
    ProposedFunction,
    ProposedIntegration,
)
from src.consultant.interviewer import ConsultantInterviewer, ConsultationConfig

__all__ = [
    "ConsultantPhase",
    "ConsultationConfig",
    "BusinessAnalysis",
    "PainPoint",
    "Opportunity",
    "ProposedSolution",
    "ProposedFunction",
    "ProposedIntegration",
    "ConsultantInterviewer",
]
