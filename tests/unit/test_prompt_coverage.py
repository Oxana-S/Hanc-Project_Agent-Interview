"""
Unit tests to verify that the voice consultant prompt covers all 32 FinalAnketa fields.

This ensures that the prompt asks questions for every field in the anketa schema,
preventing the coverage gap where fields are defined but never collected.
"""

import pytest
import yaml
from pathlib import Path


def test_all_32_fields_have_questions_in_prompt():
    """
    Проверить что все 32 поля FinalAnketa упомянуты в consultant.yaml.

    Каждое поле должно иметь либо:
    - Вопрос в discovery checklist
    - Инструкцию по сбору в тексте промпта
    - Автоматическое извлечение (как agent_purpose, main_function)
    """
    # Загрузить prompt
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "voice" / "consultant.yaml"
    with open(prompt_path) as f:
        prompt = yaml.safe_load(f)
        prompt_text = prompt["system_prompt"]

    # Все 32 client-provided поля FinalAnketa (из src/anketa/schema.py:159-202)
    required_fields = [
        # Блок 1: Компания (8)
        "company_name",
        "industry",
        "specialization",
        "website",
        # Блок 2: Контакты (4)
        "contact_name",
        "contact_role",
        "contact_email",
        "contact_phone",
        # Блок 3: Бизнес (9)
        "business_description",
        "services",
        "client_types",
        "current_problems",
        "business_goals",
        "business_type",
        "constraints",
        "compliance_requirements",
        # Блок 4: Операционные (4)
        "call_volume",
        "budget",
        "timeline",
        "additional_notes",
        # Блок 5: Агент характеристики (7)
        "agent_name",
        "agent_purpose",
        "agent_functions",
        "voice_gender",
        "voice_tone",
        "language",
        "call_direction",
        # Блок 6: Операционные детали (3)
        "working_hours",
        "transfer_conditions",
        "integrations",
        # Блок 7: Решение (2)
        "main_function",
        "additional_functions",
    ]

    # Проверить что каждое поле упомянуто в промпте
    # (либо напрямую как field name, либо через чеклист "□")
    missing_fields = []
    for field in required_fields:
        # Check if field name appears anywhere in prompt text
        # OR if there's a checklist item related to it
        if field not in prompt_text.lower():
            # Some fields might be referenced differently, check aliases
            field_aliases = {
                "contact_phone": "телефон",
                "contact_email": "email",
                "contact_name": "имя контактного лица",
                "contact_role": "должность",
                "company_name": "название компании",
                "industry": "отрасль",
                "specialization": "специализация",
                "website": "сайт компании",
                "business_description": "описание",
                "services": "услуги",
                "client_types": "типы клиентов",
                "current_problems": "проблемы",
                "business_goals": "цели",
                "business_type": "тип бизнеса",
                "constraints": "ограничения",
                "compliance_requirements": "compliance",
                "call_volume": "объём звонков",
                "budget": "бюджет",
                "timeline": "сроки",
                "additional_notes": "особые требования",
                "agent_name": "имя агента",
                "agent_purpose": "назначение агента",
                "agent_functions": "задачи для агента",
                "voice_gender": "пол голоса",
                "voice_tone": "тон голоса",
                "language": "язык",
                "call_direction": "направление звонков",
                "working_hours": "график работы",
                "transfer_conditions": "условия перевода",
                "integrations": "интеграции",
                "main_function": "главная",
                "additional_functions": "agent_functions",  # Derived from agent_functions list
            }

            # Check if alias is present
            alias = field_aliases.get(field, "")
            if not alias or alias.lower() not in prompt_text.lower():
                missing_fields.append(field)

    assert len(missing_fields) == 0, \
        f"Fields not covered in consultant.yaml prompt: {', '.join(missing_fields)}"


def test_discovery_checklist_has_at_least_25_items():
    """
    Проверить что Discovery checklist содержит минимум 25 вопросов.

    До fix было 12 вопросов (40% coverage).
    После fix должно быть 25+ вопросов (78% coverage в Discovery фазе).
    """
    # Загрузить prompt
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "voice" / "consultant.yaml"
    with open(prompt_path) as f:
        prompt = yaml.safe_load(f)
        prompt_text = prompt["system_prompt"]

    # Посчитать количество чеклист-айтемов (символ "□")
    checklist_items = prompt_text.count("□")

    assert checklist_items >= 25, \
        f"Discovery checklist has only {checklist_items} items, expected >= 25"


def test_prompt_mentions_agent_parameters():
    """
    Проверить что промпт содержит секцию НАСТРОЙКА АГЕНТА с 7 параметрами.

    Эти вопросы должны задаваться ПОСЛЕ предложения решения:
    - agent_name, agent_purpose, voice_gender, voice_tone,
      language, call_direction, working_hours
    """
    # Загрузить prompt
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "voice" / "consultant.yaml"
    with open(prompt_path) as f:
        prompt = yaml.safe_load(f)
        prompt_text = prompt["system_prompt"]

    # Проверить наличие секции НАСТРОЙКА АГЕНТА
    assert "НАСТРОЙКА АГЕНТА" in prompt_text, \
        "Prompt должен содержать секцию 'НАСТРОЙКА АГЕНТА' с вопросами про параметры агента"

    # Проверить наличие ключевых вопросов
    agent_param_keywords = [
        "имя агента",
        "назначение агента",
        "пол голоса",
        "тон голоса",
        "язык",
        "направление звонков",
        "график работы",
    ]

    missing_keywords = []
    for keyword in agent_param_keywords:
        if keyword.lower() not in prompt_text.lower():
            missing_keywords.append(keyword)

    assert len(missing_keywords) == 0, \
        f"Agent parameters section missing keywords: {', '.join(missing_keywords)}"


def test_transition_rule_updated():
    """
    Проверить что правило перехода к ПРЕДЛОЖЕНИЕ обновлено с 9/12 на 20/25.

    Старое: "НЕ переходи к фазе ПРЕДЛОЖЕНИЕ пока не собрал хотя бы 9 из 12 пунктов"
    Новое: "НЕ переходи к фазе ПРЕДЛОЖЕНИЕ пока не собрал хотя бы 20 из 25 пунктов Discovery"
    """
    # Загрузить prompt
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "voice" / "consultant.yaml"
    with open(prompt_path) as f:
        prompt = yaml.safe_load(f)
        prompt_text = prompt["system_prompt"]

    # Проверить что старое правило удалено
    assert "9 из 12" not in prompt_text, \
        "Old transition rule '9 из 12' should be removed"

    # Проверить что новое правило присутствует
    assert "20 из 25" in prompt_text, \
        "New transition rule '20 из 25 пунктов Discovery' should be present"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
