"""
Output Module - управление структурой output/.

Использование:
    from src.output import OutputManager

    manager = OutputManager()
    company_dir = manager.get_company_dir("Glamour")
    manager.save_anketa(company_dir, anketa_md, anketa_json)
    manager.save_dialogue(company_dir, dialogue_history, ...)
"""

from .manager import OutputManager

__all__ = ["OutputManager"]
