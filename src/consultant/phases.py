"""
Consultant Interview Phases.

Определение фаз консультации и условий перехода.
"""

from enum import Enum


class ConsultantPhase(str, Enum):
    """Фазы консультации AI-консультанта."""

    DISCOVERY = "discovery"      # Свободный диалог, изучение бизнеса
    ANALYSIS = "analysis"        # Анализ + исследование + показ понимания
    PROPOSAL = "proposal"        # Структурированное предложение решения
    REFINEMENT = "refinement"    # Заполнение оставшихся полей анкеты
    COMPLETED = "completed"      # Консультация завершена

    @property
    def display_name(self) -> str:
        """Отображаемое имя фазы."""
        names = {
            "discovery": "Знакомство",
            "analysis": "Анализ",
            "proposal": "Предложение",
            "refinement": "Финализация",
            "completed": "Завершено",
        }
        return names.get(self.value, self.value)

    @property
    def next_phase(self) -> "ConsultantPhase":
        """Следующая фаза."""
        order = [
            ConsultantPhase.DISCOVERY,
            ConsultantPhase.ANALYSIS,
            ConsultantPhase.PROPOSAL,
            ConsultantPhase.REFINEMENT,
            ConsultantPhase.COMPLETED,
        ]
        idx = order.index(self)
        if idx < len(order) - 1:
            return order[idx + 1]
        return ConsultantPhase.COMPLETED

    @property
    def is_terminal(self) -> bool:
        """Является ли фаза финальной."""
        return self == ConsultantPhase.COMPLETED
