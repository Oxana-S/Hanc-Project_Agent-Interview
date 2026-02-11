"""
Tests for src/anketa/markdown_parser.py

Comprehensive tests for AnketaMarkdownParser class.
All methods are pure functions (string in -> dict/list out), NO mocks needed.
"""

import pytest

from src.anketa.schema import (
    FinalAnketa, AgentFunction, Integration,
    FAQItem, ObjectionHandler, DialogueExample, FinancialMetric,
    Competitor, MarketInsight, EscalationRule, KPIMetric,
    ChecklistItem, AIRecommendation, TargetAudienceSegment
)
from src.anketa.markdown_parser import AnketaMarkdownParser, parse_anketa_markdown


def _make_base_anketa(**overrides):
    """Create a base FinalAnketa for testing."""
    defaults = {
        "company_name": "Test Company",
        "industry": "IT",
    }
    defaults.update(overrides)
    return FinalAnketa(**defaults)


@pytest.fixture
def parser():
    """Return a fresh parser instance."""
    return AnketaMarkdownParser()


# =========================================================================
# TestParseCompanyInfo
# =========================================================================

class TestParseCompanyInfo:
    """Tests for _parse_company_info method."""

    @pytest.mark.unit
    def test_parse_company_info_full_table(self, parser):
        """All company info fields are extracted from table."""
        content = (
            "## 1. Информация о компании\n\n"
            "| Поле | Значение |\n"
            "| --- | --- |\n"
            "| Компания | Acme Corp |\n"
            "| Отрасль | E-commerce |\n"
            "| Специализация | Marketplace |\n"
            "| Сайт | https://acme.com |\n"
            "| Контактное лицо | John Doe |\n"
            "| Должность | CEO |\n\n"
            "### Описание бизнеса\n\n"
            "Online marketplace\n\n"
            "### Услуги / Продукты\n\n"
            "- Product A\n"
            "- Product B\n\n"
            "### Типы клиентов\n\n"
            "- B2B\n"
            "- B2C\n\n"
            "---\n"
        )
        result = parser._parse_company_info(content)

        assert result['company_name'] == 'Acme Corp'
        assert result['industry'] == 'E-commerce'
        assert result['specialization'] == 'Marketplace'
        assert result['website'] == 'https://acme.com'
        assert result['contact_name'] == 'John Doe'
        assert result['contact_role'] == 'CEO'
        assert result['business_description'] == 'Online marketplace'
        assert result['services'] == ['Product A', 'Product B']
        assert result['client_types'] == ['B2B', 'B2C']

    @pytest.mark.unit
    def test_parse_company_info_empty_values(self, parser):
        """Fields with dash '---' are treated as empty strings (or None for website)."""
        content = (
            "| Компания | — |\n"
            "| Отрасль | — |\n"
            "| Специализация | — |\n"
            "| Сайт | — |\n"
            "| Контактное лицо | — |\n"
            "| Должность | — |\n\n"
            "---\n"
        )
        result = parser._parse_company_info(content)

        assert result['company_name'] == ''
        assert result['industry'] == ''
        assert result['specialization'] == ''
        assert result['website'] is None
        assert result['contact_name'] == ''
        assert result['contact_role'] == ''

    @pytest.mark.unit
    def test_parse_company_info_missing_table(self, parser):
        """When no table is found, result has no table-based fields."""
        content = "Some random text without any table\n\n---\n"
        result = parser._parse_company_info(content)

        assert 'company_name' not in result
        assert 'industry' not in result

    @pytest.mark.unit
    def test_parse_company_info_business_description(self, parser):
        """Business description is extracted from ### section."""
        content = (
            "### Описание бизнеса\n\n"
            "We build amazing products for everyone.\n\n"
            "### Услуги / Продукты\n\n"
            "- Service A\n\n"
            "---\n"
        )
        result = parser._parse_company_info(content)
        assert result['business_description'] == 'We build amazing products for everyone.'

    @pytest.mark.unit
    def test_parse_company_info_business_description_not_specified(self, parser):
        """Business description '*He указано*' is ignored."""
        content = (
            "### Описание бизнеса\n\n"
            "*Не указано*\n\n"
            "### Услуги / Продукты\n\n"
            "- X\n\n"
            "---\n"
        )
        result = parser._parse_company_info(content)
        assert 'business_description' not in result

    @pytest.mark.unit
    def test_parse_company_info_services_list(self, parser):
        """Services are parsed as a bullet list."""
        content = (
            "### Услуги / Продукты\n\n"
            "- Web development\n"
            "- Mobile apps\n"
            "- Consulting\n\n"
            "### Типы клиентов\n\n"
            "- Startups\n\n"
            "---\n"
        )
        result = parser._parse_company_info(content)
        assert result['services'] == ['Web development', 'Mobile apps', 'Consulting']

    @pytest.mark.unit
    def test_parse_company_info_client_types(self, parser):
        """Client types are parsed as a bullet list."""
        content = (
            "### Типы клиентов\n\n"
            "- Enterprise\n"
            "- SMB\n\n"
            "---\n"
        )
        result = parser._parse_company_info(content)
        assert result['client_types'] == ['Enterprise', 'SMB']

    @pytest.mark.unit
    def test_parse_company_info_website_dash_sets_none(self, parser):
        """Website field with dash value is set to None."""
        content = "| Сайт | — |\n\n---\n"
        result = parser._parse_company_info(content)
        assert result['website'] is None


# =========================================================================
# TestParseBusinessContext
# =========================================================================

class TestParseBusinessContext:
    """Tests for _parse_business_context method."""

    @pytest.mark.unit
    def test_parse_business_context_all_lists(self, parser):
        """All three lists are parsed correctly."""
        content = (
            "### Текущие проблемы\n\n"
            "- Too many calls\n"
            "- Low conversion\n\n"
            "### Цели автоматизации\n\n"
            "- Reduce costs\n"
            "- 24/7 availability\n\n"
            "### Ограничения\n\n"
            "- Budget $5000\n"
            "- No technical team\n\n"
            "---\n"
        )
        result = parser._parse_business_context(content)

        assert result['current_problems'] == ['Too many calls', 'Low conversion']
        assert result['business_goals'] == ['Reduce costs', '24/7 availability']
        assert result['constraints'] == ['Budget $5000', 'No technical team']

    @pytest.mark.unit
    def test_parse_business_context_empty_lists(self, parser):
        """Empty or missing sections return empty lists."""
        content = "Some unrelated content\n\n---\n"
        result = parser._parse_business_context(content)

        assert result['current_problems'] == []
        assert result['business_goals'] == []
        assert result['constraints'] == []

    @pytest.mark.unit
    def test_parse_business_context_partial_data(self, parser):
        """Only present sections are filled; missing sections remain empty."""
        content = (
            "### Текущие проблемы\n\n"
            "- Problem one\n\n"
            "### Цели автоматизации\n\n"
            "*Не указано*\n\n"
            "---\n"
        )
        result = parser._parse_business_context(content)

        assert result['current_problems'] == ['Problem one']
        assert result['business_goals'] == []
        assert result['constraints'] == []

    @pytest.mark.unit
    def test_parse_business_context_returns_dict(self, parser):
        """Result is always a dict with the three expected keys."""
        content = ""
        result = parser._parse_business_context(content)

        assert isinstance(result, dict)
        assert 'current_problems' in result
        assert 'business_goals' in result
        assert 'constraints' in result


# =========================================================================
# TestParseVoiceAgent
# =========================================================================

class TestParseVoiceAgent:
    """Tests for _parse_voice_agent method."""

    @pytest.mark.unit
    def test_parse_voice_agent_full_table(self, parser):
        """All voice agent table fields are extracted."""
        content = (
            "## 3. Голосовой агент\n\n"
            "| Поле | Значение |\n"
            "| --- | --- |\n"
            "| Имя агента | Ассистент Мария |\n"
            "| Назначение | Обработка заявок |\n"
            "| Язык | ru |\n"
            "| Голос | female, professional |\n"
            "| Тип звонков | Входящие |\n\n"
            "### Типичные вопросы (FAQ)\n\n"
            "- Сколько стоит?\n"
            "- Какие сроки?\n\n"
            "---\n"
        )
        result = parser._parse_voice_agent(content)

        assert result['agent_name'] == 'Ассистент Мария'
        assert result['agent_purpose'] == 'Обработка заявок'
        assert result['language'] == 'ru'
        assert result['voice_gender'] == 'female'
        assert result['voice_tone'] == 'professional'
        assert result['call_direction'] == 'inbound'
        assert result['typical_questions'] == ['Сколько стоит?', 'Какие сроки?']

    @pytest.mark.unit
    def test_parse_voice_agent_voice_parsing(self, parser):
        """Voice string 'female, professional' is split into gender and tone."""
        content = "| Голос | male, friendly |\n\n---\n"
        result = parser._parse_voice_agent(content)

        assert result['voice_gender'] == 'male'
        assert result['voice_tone'] == 'friendly'

    @pytest.mark.unit
    def test_parse_voice_agent_voice_gender_only(self, parser):
        """When voice has no comma, only gender is set."""
        content = "| Голос | female |\n\n---\n"
        result = parser._parse_voice_agent(content)

        assert result['voice_gender'] == 'female'
        assert 'voice_tone' not in result

    @pytest.mark.unit
    def test_parse_voice_agent_call_direction_inbound(self, parser):
        """Входящие maps to inbound."""
        content = "| Тип звонков | Входящие |\n\n---\n"
        result = parser._parse_voice_agent(content)
        assert result['call_direction'] == 'inbound'

    @pytest.mark.unit
    def test_parse_voice_agent_call_direction_outbound(self, parser):
        """Исходящие maps to outbound."""
        content = "| Тип звонков | Исходящие |\n\n---\n"
        result = parser._parse_voice_agent(content)
        assert result['call_direction'] == 'outbound'

    @pytest.mark.unit
    def test_parse_voice_agent_call_direction_both(self, parser):
        """Входящие и исходящие maps to both."""
        content = "| Тип звонков | Входящие и исходящие |\n\n---\n"
        result = parser._parse_voice_agent(content)
        assert result['call_direction'] == 'both'

    @pytest.mark.unit
    def test_parse_voice_agent_missing_fields(self, parser):
        """Missing table rows produce no keys in result."""
        content = "Some random text\n\n---\n"
        result = parser._parse_voice_agent(content)

        assert 'agent_name' not in result
        assert 'agent_purpose' not in result
        assert 'language' not in result

    @pytest.mark.unit
    def test_parse_voice_agent_typical_questions(self, parser):
        """Typical questions bullet list is parsed."""
        content = (
            "### Типичные вопросы (FAQ)\n\n"
            "- What are your hours?\n"
            "- How much does it cost?\n"
            "- Do you deliver?\n\n"
            "---\n"
        )
        result = parser._parse_voice_agent(content)
        assert result['typical_questions'] == [
            'What are your hours?',
            'How much does it cost?',
            'Do you deliver?',
        ]


# =========================================================================
# TestParseAgentFunctions
# =========================================================================

class TestParseAgentFunctions:
    """Tests for _parse_agent_functions method."""

    @pytest.mark.unit
    def test_parse_agent_functions_multiple(self, parser):
        """Multiple functions are parsed from numbered sections."""
        content = (
            "## 4. Все функции агента\n\n"
            "### 1. Прием заявок\n\n"
            "Обработка входящих обращений клиентов\n\n"
            "*Приоритет: high*\n\n"
            "### 2. Консультация\n\n"
            "Предоставление информации о продуктах\n\n"
            "*Приоритет: medium*\n\n"
            "---\n"
        )
        result = parser._parse_agent_functions(content)

        assert len(result['agent_functions']) == 2
        assert result['agent_functions'][0].name == 'Прием заявок'
        assert result['agent_functions'][0].description == 'Обработка входящих обращений клиентов'
        assert result['agent_functions'][0].priority == 'high'
        assert result['agent_functions'][1].name == 'Консультация'
        assert result['agent_functions'][1].priority == 'medium'

    @pytest.mark.unit
    def test_parse_agent_functions_with_priority(self, parser):
        """Priority labels are correctly extracted."""
        content = (
            "## 4. Все функции агента\n\n"
            "### 1. Booking\n\n"
            "Manage appointments\n\n"
            "*Приоритет: low*\n\n"
            "---\n"
        )
        result = parser._parse_agent_functions(content)

        assert len(result['agent_functions']) == 1
        assert result['agent_functions'][0].priority == 'low'

    @pytest.mark.unit
    def test_parse_agent_functions_empty_section(self, parser):
        """Section found but no functions inside."""
        content = (
            "## 4. Все функции агента\n\n"
            "No functions yet.\n\n"
            "---\n"
        )
        result = parser._parse_agent_functions(content)
        assert result['agent_functions'] == []
        assert result['main_function'] is None
        assert result['additional_functions'] == []

    @pytest.mark.unit
    def test_parse_agent_functions_sets_main_and_additional(self, parser):
        """First function becomes main, rest become additional."""
        content = (
            "## 4. Все функции агента\n\n"
            "### 1. Main Function\n\n"
            "Main description\n\n"
            "*Приоритет: high*\n\n"
            "### 2. Secondary\n\n"
            "Secondary description\n\n"
            "*Приоритет: medium*\n\n"
            "### 3. Tertiary\n\n"
            "Tertiary description\n\n"
            "*Приоритет: low*\n\n"
            "---\n"
        )
        result = parser._parse_agent_functions(content)

        assert result['main_function'].name == 'Main Function'
        assert len(result['additional_functions']) == 2
        assert result['additional_functions'][0].name == 'Secondary'
        assert result['additional_functions'][1].name == 'Tertiary'

    @pytest.mark.unit
    def test_parse_agent_functions_single_function(self, parser):
        """Single function is both main and in the functions list, additional is empty."""
        content = (
            "## 4. Все функции агента\n\n"
            "### 1. Only Function\n\n"
            "The only function description\n\n"
            "*Приоритет: high*\n\n"
            "---\n"
        )
        result = parser._parse_agent_functions(content)

        assert len(result['agent_functions']) == 1
        assert result['main_function'].name == 'Only Function'
        assert result['additional_functions'] == []

    @pytest.mark.unit
    def test_parse_agent_functions_no_section(self, parser):
        """No matching section returns defaults."""
        content = "Some unrelated text\n\n---\n"
        result = parser._parse_agent_functions(content)

        assert result['agent_functions'] == []
        assert result['main_function'] is None
        assert result['additional_functions'] == []


# =========================================================================
# TestParseIntegrations
# =========================================================================

class TestParseIntegrations:
    """Tests for _parse_integrations method."""

    @pytest.mark.unit
    def test_parse_integrations_table(self, parser):
        """Integrations are parsed from a table with required status."""
        content = (
            "## 5. Интеграции\n\n"
            "| Система | Назначение | Требуется |\n"
            "| ------ | ------ | ------ |\n"
            "| CRM Bitrix | Управление клиентами | Да |\n"
            "| Telegram | Уведомления | Нет |\n\n"
            "---\n"
        )
        result = parser._parse_integrations(content)
        integrations = result['integrations']

        assert len(integrations) == 2
        assert integrations[0].name == 'CRM Bitrix'
        assert integrations[0].purpose == 'Управление клиентами'
        assert integrations[0].required is True
        assert integrations[1].name == 'Telegram'
        assert integrations[1].required is False

    @pytest.mark.unit
    def test_parse_integrations_not_required(self, parser):
        """Integration with 'Нет' is marked as not required."""
        content = (
            "## 5. Интеграции\n\n"
            "| Система | Назначение | Требуется |\n"
            "| ------ | ------ | ------ |\n"
            "| Slack | Alerts | Нет |\n\n"
            "---\n"
        )
        result = parser._parse_integrations(content)
        assert result['integrations'][0].required is False

    @pytest.mark.unit
    def test_parse_integrations_none_required(self, parser):
        """Section with 'не требуются' returns empty list."""
        content = (
            "## 5. Интеграции\n\n"
            "Интеграции не требуются на текущем этапе.\n\n"
            "---\n"
        )
        result = parser._parse_integrations(content)
        assert result['integrations'] == []

    @pytest.mark.unit
    def test_parse_integrations_no_section(self, parser):
        """Missing section returns empty list."""
        content = "No integrations section here.\n\n---\n"
        result = parser._parse_integrations(content)
        assert result['integrations'] == []

    @pytest.mark.unit
    def test_parse_integrations_skip_header(self, parser):
        """Table header row 'Система' is not included in results."""
        content = (
            "## 5. Интеграции\n\n"
            "| Система | Назначение | Требуется |\n"
            "| ------ | ------ | ------ |\n"
            "| Google Sheets | Отчёты | Да |\n\n"
            "---\n"
        )
        result = parser._parse_integrations(content)
        assert len(result['integrations']) == 1
        assert result['integrations'][0].name == 'Google Sheets'


# =========================================================================
# TestParseListSection
# =========================================================================

class TestParseListSection:
    """Tests for _parse_list_section method."""

    @pytest.mark.unit
    def test_parse_list_section_normal(self, parser):
        """Bullet list items are extracted correctly."""
        content = (
            "### Test Section\n\n"
            "- Item one\n"
            "- Item two\n"
            "- Item three\n\n"
            "### Next Section\n\n"
            "Other content\n\n"
            "---\n"
        )
        result = parser._parse_list_section(content, 'Test Section')
        assert result == ['Item one', 'Item two', 'Item three']

    @pytest.mark.unit
    def test_parse_list_section_not_specified(self, parser):
        """Section with '*He указано*' returns empty list."""
        content = (
            "### Test Section\n\n"
            "*Не указано*\n\n"
            "### Next Section\n\n"
            "---\n"
        )
        result = parser._parse_list_section(content, 'Test Section')
        assert result == []

    @pytest.mark.unit
    def test_parse_list_section_empty(self, parser):
        """Section with no bullet items returns empty list."""
        content = (
            "### Test Section\n\n"
            "Just some text without bullets\n\n"
            "### Next Section\n\n"
            "---\n"
        )
        result = parser._parse_list_section(content, 'Test Section')
        assert result == []

    @pytest.mark.unit
    def test_parse_list_section_no_section(self, parser):
        """Missing section returns empty list."""
        content = "### Different Section\n\nContent\n\n---\n"
        result = parser._parse_list_section(content, 'Nonexistent Section')
        assert result == []


# =========================================================================
# TestParseFAQItems
# =========================================================================

class TestParseFAQItems:
    """Tests for _parse_faq_items method."""

    @pytest.mark.unit
    def test_parse_faq_items_with_category(self, parser):
        """FAQ items with explicit category are parsed."""
        content = (
            "## 6. FAQ с ответами\n\n"
            "### 1. Сколько стоит подключение? [pricing]\n\n"
            "> Стоимость зависит от объема. Базовый тариф от 5000 руб/мес.\n\n"
            "### 2. Как начать? [process]\n\n"
            "> Оставьте заявку на сайте, мы свяжемся в течение часа.\n\n"
            "---\n"
        )
        result = parser._parse_faq_items(content)
        items = result['faq_items']

        assert len(items) == 2
        assert items[0].question == 'Сколько стоит подключение?'
        assert items[0].category == 'pricing'
        assert items[0].answer == 'Стоимость зависит от объема. Базовый тариф от 5000 руб/мес.'
        assert items[1].question == 'Как начать?'
        assert items[1].category == 'process'

    @pytest.mark.unit
    def test_parse_faq_items_default_category(self, parser):
        """FAQ items without category default to 'general'."""
        content = (
            "## 6. FAQ с ответами\n\n"
            "### 1. Какой график работы?\n\n"
            "> Мы работаем с 9 до 18 по будням.\n\n"
            "---\n"
        )
        result = parser._parse_faq_items(content)
        items = result['faq_items']

        assert len(items) == 1
        assert items[0].category == 'general'

    @pytest.mark.unit
    def test_parse_faq_items_empty(self, parser):
        """No FAQ section returns empty list."""
        content = "Some other content\n\n---\n"
        result = parser._parse_faq_items(content)
        assert result['faq_items'] == []

    @pytest.mark.unit
    def test_parse_faq_items_not_generated(self, parser):
        """Section with 'не сгенерирован' text returns empty list."""
        content = (
            "## 6. FAQ с ответами\n\n"
            "Раздел не сгенерирован — недостаточно данных.\n\n"
            "---\n"
        )
        result = parser._parse_faq_items(content)
        assert result['faq_items'] == []


# =========================================================================
# TestParseObjectionHandlers
# =========================================================================

class TestParseObjectionHandlers:
    """Tests for _parse_objection_handlers method."""

    @pytest.mark.unit
    def test_parse_objection_handlers_with_followup(self, parser):
        """Objections with follow-up actions are parsed."""
        content = (
            "## 7. Работа с возражениями\n\n"
            "### 1. «Слишком дорого»\n\n"
            "**Ответ:** Я понимаю. Давайте разберём, какую экономию вы получите.\n\n"
            "**Далее:** Предложить демо бесплатно\n\n"
            "---\n"
        )
        result = parser._parse_objection_handlers(content)
        handlers = result['objection_handlers']

        assert len(handlers) == 1
        assert handlers[0].objection == 'Слишком дорого'
        assert handlers[0].response == 'Я понимаю. Давайте разберём, какую экономию вы получите.'
        assert handlers[0].follow_up == 'Предложить демо бесплатно'

    @pytest.mark.unit
    def test_parse_objection_handlers_without_followup(self, parser):
        """Objections without follow-up get None."""
        content = (
            "## 7. Работа с возражениями\n\n"
            "### 1. «Мне нужно подумать»\n\n"
            "**Ответ:** Конечно, я оставлю вам наши контакты.\n\n"
            "---\n"
        )
        result = parser._parse_objection_handlers(content)
        handlers = result['objection_handlers']

        assert len(handlers) == 1
        assert handlers[0].objection == 'Мне нужно подумать'
        assert handlers[0].follow_up is None

    @pytest.mark.unit
    def test_parse_objection_handlers_empty(self, parser):
        """Missing section returns empty list."""
        content = "No objections here\n\n---\n"
        result = parser._parse_objection_handlers(content)
        assert result['objection_handlers'] == []

    @pytest.mark.unit
    def test_parse_objection_handlers_not_generated(self, parser):
        """Section with 'не проработаны' returns empty list."""
        content = (
            "## 7. Работа с возражениями\n\n"
            "Возражения не проработаны.\n\n"
            "---\n"
        )
        result = parser._parse_objection_handlers(content)
        assert result['objection_handlers'] == []


# =========================================================================
# TestParseSampleDialogue
# =========================================================================

class TestParseSampleDialogue:
    """Tests for _parse_sample_dialogue method."""

    @pytest.mark.unit
    def test_parse_sample_dialogue_agent_and_client(self, parser):
        """Both agent and client turns are parsed."""
        content = (
            "## 8. Пример диалога\n\n"
            "**Агент:** Здравствуйте! Чем могу помочь? *(приветствие)*\n\n"
            "**Клиент:** Хочу узнать цены *(запрос_цены)*\n\n"
            "**Агент:** Конечно! Базовый тариф от 5000 руб. *(информация)*\n\n"
            "---\n"
        )
        result = parser._parse_sample_dialogue(content)
        dialogue = result['sample_dialogue']

        assert len(dialogue) == 3
        assert dialogue[0].role == 'bot'
        assert dialogue[1].role == 'client'
        assert dialogue[2].role == 'bot'

    @pytest.mark.unit
    def test_parse_sample_dialogue_with_intent(self, parser):
        """Intent tags in parentheses are extracted."""
        content = (
            "## 8. Пример диалога\n\n"
            "**Агент:** Здравствуйте! *(greeting)*\n\n"
            "---\n"
        )
        result = parser._parse_sample_dialogue(content)
        dialogue = result['sample_dialogue']

        assert len(dialogue) == 1
        assert dialogue[0].intent == 'greeting'

    @pytest.mark.unit
    def test_parse_sample_dialogue_empty(self, parser):
        """Missing section returns empty list."""
        content = "No dialogue\n\n---\n"
        result = parser._parse_sample_dialogue(content)
        assert result['sample_dialogue'] == []

    @pytest.mark.unit
    def test_parse_sample_dialogue_role_mapping(self, parser):
        """Agent maps to 'bot', Client maps to 'client'."""
        content = (
            "## 8. Пример диалога\n\n"
            "**Агент Мария:** Добрый день!\n\n"
            "**Клиент:** Привет\n\n"
            "---\n"
        )
        result = parser._parse_sample_dialogue(content)
        dialogue = result['sample_dialogue']

        assert dialogue[0].role == 'bot'
        assert dialogue[1].role == 'client'


# =========================================================================
# TestParseFinancialMetrics
# =========================================================================

class TestParseFinancialMetrics:
    """Tests for _parse_financial_metrics method."""

    @pytest.mark.unit
    def test_parse_financial_metrics_full_table(self, parser):
        """Financial metrics are parsed from a table."""
        content = (
            "## 9. Финансовая модель\n\n"
            "| Метрика | Значение | Источник | Примечание |\n"
            "| ------- | ------- | ------- | ------- |\n"
            "| Средний чек | 15 000 руб | Клиент | Для B2B сегмента |\n"
            "| ROI | 250% | AI-бенчмарк | За первый год |\n\n"
            "---\n"
        )
        result = parser._parse_financial_metrics(content)
        metrics = result['financial_metrics']

        assert len(metrics) == 2
        assert metrics[0].name == 'Средний чек'
        assert metrics[0].value == '15 000 руб'
        assert metrics[0].source == 'client'
        assert metrics[0].note == 'Для B2B сегмента'
        assert metrics[1].source == 'ai_benchmark'

    @pytest.mark.unit
    def test_parse_financial_metrics_source_mapping(self, parser):
        """Source labels are mapped to internal values."""
        content = (
            "## 9. Финансовая модель\n\n"
            "| Метрика | Значение | Источник | Примечание |\n"
            "| ------- | ------- | ------- | ------- |\n"
            "| CAC | 1000 руб | Расчёт | — |\n\n"
            "---\n"
        )
        result = parser._parse_financial_metrics(content)
        metrics = result['financial_metrics']

        assert len(metrics) == 1
        assert metrics[0].source == 'calculated'

    @pytest.mark.unit
    def test_parse_financial_metrics_empty(self, parser):
        """Missing section returns empty list."""
        content = "No financial data\n\n---\n"
        result = parser._parse_financial_metrics(content)
        assert result['financial_metrics'] == []

    @pytest.mark.unit
    def test_parse_financial_metrics_note_dash(self, parser):
        """Note with '---' value becomes None."""
        content = (
            "## 9. Финансовая модель\n\n"
            "| Метрика | Значение | Источник | Примечание |\n"
            "| ------- | ------- | ------- | ------- |\n"
            "| LTV | 50 000 руб | Клиент | — |\n\n"
            "---\n"
        )
        result = parser._parse_financial_metrics(content)
        assert result['financial_metrics'][0].note is None


# =========================================================================
# TestParseMarketAnalysis
# =========================================================================

class TestParseMarketAnalysis:
    """Tests for _parse_market_analysis method."""

    @pytest.mark.unit
    def test_parse_competitors_with_strengths_weaknesses(self, parser):
        """Competitors with strengths and weaknesses are parsed."""
        content = (
            "## 10. Анализ рынка\n\n"
            "### Конкуренты\n\n"
            "#### CompanyX\n"
            "*Цены: 5000-15000 руб/мес*\n\n"
            "✅ Быстрая поддержка\n"
            "✅ Низкие цены\n"
            "❌ Мало интеграций\n\n"
            "### Рыночные инсайты\n\n"
            "---\n"
        )
        result = parser._parse_market_analysis(content)
        competitors = result['competitors']

        assert len(competitors) == 1
        assert competitors[0].name == 'CompanyX'
        assert competitors[0].price_range == '5000-15000 руб/мес'
        assert competitors[0].strengths == ['Быстрая поддержка', 'Низкие цены']
        assert competitors[0].weaknesses == ['Мало интеграций']

    @pytest.mark.unit
    def test_parse_competitors_with_price_range(self, parser):
        """Price range is extracted from *Цены: ...* line."""
        content = (
            "## 10. Анализ рынка\n\n"
            "### Конкуренты\n\n"
            "#### RivalCo\n"
            "*Цены: от 10 000 руб*\n\n"
            "✅ Хороший UI\n"
            "❌ Дорого\n\n"
            "### Рыночные инсайты\n\n"
            "---\n"
        )
        result = parser._parse_market_analysis(content)
        assert result['competitors'][0].price_range == 'от 10 000 руб'

    @pytest.mark.unit
    def test_parse_market_insights_relevance_by_emoji(self, parser):
        """Relevance is determined by emoji prefix."""
        content = (
            "## 10. Анализ рынка\n\n"
            "### Конкуренты\n\n"
            "*Не определены*\n\n"
            "### Рыночные инсайты\n\n"
            "- \U0001f525 AI-рынок растёт на 40% в год\n"
            "- \U0001f4ca 70% компаний используют чат-ботов\n"
            "- \U0001f4dd Новые регуляции ожидаются в 2025\n\n"
            "### Конкурентные преимущества клиента\n\n"
            "---\n"
        )
        result = parser._parse_market_analysis(content)
        insights = result['market_insights']

        assert len(insights) == 3
        assert insights[0].relevance == 'high'
        assert insights[1].relevance == 'medium'
        assert insights[2].relevance == 'low'
        # Emoji should be cleaned from text
        assert '\U0001f525' not in insights[0].insight
        assert 'AI-рынок растёт на 40% в год' == insights[0].insight

    @pytest.mark.unit
    def test_parse_competitive_advantages(self, parser):
        """Competitive advantages are parsed as bullet list."""
        content = (
            "## 10. Анализ рынка\n\n"
            "### Конкуренты\n\n"
            "*Не определены*\n\n"
            "### Рыночные инсайты\n\n"
            "*Не сгенерированы*\n\n"
            "### Конкурентные преимущества клиента\n\n"
            "- 10 лет опыта\n"
            "- Уникальная технология\n\n"
            "---\n"
        )
        result = parser._parse_market_analysis(content)
        assert result['competitive_advantages'] == ['10 лет опыта', 'Уникальная технология']

    @pytest.mark.unit
    def test_parse_market_analysis_empty(self, parser):
        """Missing section returns all empty."""
        content = "No market data\n\n---\n"
        result = parser._parse_market_analysis(content)

        assert result['competitors'] == []
        assert result['market_insights'] == []
        assert result['competitive_advantages'] == []

    @pytest.mark.unit
    def test_parse_competitors_not_determined(self, parser):
        """Competitors section with 'не определены' returns empty list."""
        content = (
            "## 10. Анализ рынка\n\n"
            "### Конкуренты\n\n"
            "*Конкуренты не определены*\n\n"
            "### Рыночные инсайты\n\n"
            "---\n"
        )
        result = parser._parse_market_analysis(content)
        assert result['competitors'] == []


# =========================================================================
# TestParseTargetSegments
# =========================================================================

class TestParseTargetSegments:
    """Tests for _parse_target_segments method."""

    @pytest.mark.unit
    def test_parse_target_segments_with_pain_and_triggers(self, parser):
        """Segments with pain points and triggers are parsed."""
        content = (
            "## 11. Целевые сегменты\n\n"
            "### 1. Малый бизнес\n\n"
            "Компании до 50 сотрудников\n\n"
            "**Болевые точки:**\n"
            "\U0001f613 Нет бюджета на колл-центр\n"
            "\U0001f613 Пропущенные звонки\n\n"
            "**Триггеры:**\n"
            "\u26a1 Рост обращений\n"
            "\u26a1 Потеря клиентов\n\n"
            "---\n"
        )
        result = parser._parse_target_segments(content)
        segments = result['target_segments']

        assert len(segments) == 1
        assert segments[0].name == 'Малый бизнес'
        assert segments[0].description == 'Компании до 50 сотрудников'
        assert segments[0].pain_points == ['Нет бюджета на колл-центр', 'Пропущенные звонки']
        assert segments[0].triggers == ['Рост обращений', 'Потеря клиентов']

    @pytest.mark.unit
    def test_parse_target_segments_empty(self, parser):
        """Missing section returns empty list."""
        content = "No segments\n\n---\n"
        result = parser._parse_target_segments(content)
        assert result['target_segments'] == []

    @pytest.mark.unit
    def test_parse_target_segments_not_determined(self, parser):
        """Section with 'не определены' returns empty list."""
        content = (
            "## 11. Целевые сегменты\n\n"
            "Целевые сегменты не определены.\n\n"
            "---\n"
        )
        result = parser._parse_target_segments(content)
        assert result['target_segments'] == []

    @pytest.mark.unit
    def test_parse_target_segments_multiple(self, parser):
        """Multiple segments are all parsed."""
        content = (
            "## 11. Целевые сегменты\n\n"
            "### 1. B2B клиенты\n\n"
            "Корпоративные клиенты\n\n"
            "**Болевые точки:**\n"
            "\U0001f613 Долгие процессы\n\n"
            "**Триггеры:**\n"
            "\u26a1 Срочный проект\n\n"
            "### 2. B2C клиенты\n\n"
            "Физические лица\n\n"
            "**Болевые точки:**\n"
            "\U0001f613 Сложный интерфейс\n\n"
            "**Триггеры:**\n"
            "\u26a1 Рекомендация друга\n\n"
            "---\n"
        )
        result = parser._parse_target_segments(content)
        segments = result['target_segments']

        assert len(segments) == 2
        assert segments[0].name == 'B2B клиенты'
        assert segments[1].name == 'B2C клиенты'


# =========================================================================
# TestParseEscalationRules
# =========================================================================

class TestParseEscalationRules:
    """Tests for _parse_escalation_rules method."""

    @pytest.mark.unit
    def test_parse_escalation_rules_urgency_mapping(self, parser):
        """Urgency labels with emojis are mapped correctly."""
        content = (
            "## 12. Правила эскалации\n\n"
            "| Триггер | Срочность | Действие |\n"
            "| ------- | ------- | ------- |\n"
            "| Жалоба клиента | \U0001f6a8 Немедленно | Перевести на менеджера |\n"
            "| Технический вопрос | \u23f0 В течение часа | Создать тикет |\n"
            "| Запрос документов | \U0001f4c5 В течение дня | Отправить email |\n\n"
            "---\n"
        )
        result = parser._parse_escalation_rules(content)
        rules = result['escalation_rules']

        assert len(rules) == 3
        assert rules[0].trigger == 'Жалоба клиента'
        assert rules[0].urgency == 'immediate'
        assert rules[0].action == 'Перевести на менеджера'
        assert rules[1].urgency == 'hour'
        assert rules[2].urgency == 'day'

    @pytest.mark.unit
    def test_parse_escalation_rules_empty(self, parser):
        """Missing section returns empty list."""
        content = "No escalation rules\n\n---\n"
        result = parser._parse_escalation_rules(content)
        assert result['escalation_rules'] == []

    @pytest.mark.unit
    def test_parse_escalation_rules_table_header_skipped(self, parser):
        """Table header 'Триггер' row is not included as a rule."""
        content = (
            "## 12. Правила эскалации\n\n"
            "| Триггер | Срочность | Действие |\n"
            "| ------- | ------- | ------- |\n"
            "| Ошибка оплаты | \U0001f6a8 Немедленно | Перевод на оператора |\n\n"
            "---\n"
        )
        result = parser._parse_escalation_rules(content)
        assert len(result['escalation_rules']) == 1
        assert result['escalation_rules'][0].trigger == 'Ошибка оплаты'

    @pytest.mark.unit
    def test_parse_escalation_rules_not_determined(self, parser):
        """Section with 'не определены' returns empty list."""
        content = (
            "## 12. Правила эскалации\n\n"
            "Правила эскалации не определены.\n\n"
            "---\n"
        )
        result = parser._parse_escalation_rules(content)
        assert result['escalation_rules'] == []


# =========================================================================
# TestParseSuccessKPIs
# =========================================================================

class TestParseSuccessKPIs:
    """Tests for _parse_success_kpis method."""

    @pytest.mark.unit
    def test_parse_success_kpis_full_table(self, parser):
        """KPI metrics are parsed from table."""
        content = (
            "## 13. KPI и метрики успеха\n\n"
            "| KPI | Цель | Бенчмарк | Измерение |\n"
            "| ---- | ---- | ---- | ---- |\n"
            "| CSAT | > 4.5 | 4.2 | Опрос после звонка |\n"
            "| Время ответа | < 3 сек | 5 сек | Автоматически |\n\n"
            "---\n"
        )
        result = parser._parse_success_kpis(content)
        kpis = result['success_kpis']

        assert len(kpis) == 2
        assert kpis[0].name == 'CSAT'
        assert kpis[0].target == '> 4.5'
        assert kpis[0].benchmark == '4.2'
        assert kpis[0].measurement == 'Опрос после звонка'
        assert kpis[1].name == 'Время ответа'

    @pytest.mark.unit
    def test_parse_success_kpis_empty(self, parser):
        """Missing section returns empty list."""
        content = "No KPIs\n\n---\n"
        result = parser._parse_success_kpis(content)
        assert result['success_kpis'] == []

    @pytest.mark.unit
    def test_parse_success_kpis_optional_fields_dash(self, parser):
        """Benchmark and measurement with '---' become None."""
        content = (
            "## 13. KPI и метрики успеха\n\n"
            "| KPI | Цель | Бенчмарк | Измерение |\n"
            "| ---- | ---- | ---- | ---- |\n"
            "| Конверсия | 15% | — | — |\n\n"
            "---\n"
        )
        result = parser._parse_success_kpis(content)
        kpis = result['success_kpis']

        assert len(kpis) == 1
        assert kpis[0].name == 'Конверсия'
        assert kpis[0].target == '15%'
        assert kpis[0].benchmark is None
        assert kpis[0].measurement is None

    @pytest.mark.unit
    def test_parse_success_kpis_not_determined(self, parser):
        """Section with 'не определены' returns empty list."""
        content = (
            "## 13. KPI и метрики успеха\n\n"
            "KPI не определены.\n\n"
            "---\n"
        )
        result = parser._parse_success_kpis(content)
        assert result['success_kpis'] == []


# =========================================================================
# TestParseLaunchChecklist
# =========================================================================

class TestParseLaunchChecklist:
    """Tests for _parse_launch_checklist method."""

    @pytest.mark.unit
    def test_parse_launch_checklist_required_optional(self, parser):
        """Required items (checkbox) and optional items (circle) are distinguished."""
        content = (
            "## 14. Чеклист запуска\n\n"
            "- \u2610 Подготовить базу знаний \u2014 \U0001f464 Клиент **(обязательно)**\n"
            "- \u25cb Настроить интеграции \u2014 \U0001f465 Команда\n\n"
            "---\n"
        )
        result = parser._parse_launch_checklist(content)
        checklist = result['launch_checklist']

        assert len(checklist) == 2
        assert checklist[0].item == 'Подготовить базу знаний'
        assert checklist[0].required is True
        assert checklist[0].responsible == 'client'
        assert checklist[1].item == 'Настроить интеграции'
        assert checklist[1].required is False
        assert checklist[1].responsible == 'team'

    @pytest.mark.unit
    def test_parse_launch_checklist_responsible_mapping(self, parser):
        """Responsible person markers map correctly."""
        content = (
            "## 14. Чеклист запуска\n\n"
            "- \u2610 Клиентская задача \u2014 \U0001f464 Клиент **(обязательно)**\n"
            "- \u2610 Командная задача \u2014 \U0001f465 Команда **(обязательно)**\n"
            "- \u2610 Совместная задача \u2014 \U0001f91d Совместно **(обязательно)**\n\n"
            "---\n"
        )
        result = parser._parse_launch_checklist(content)
        checklist = result['launch_checklist']

        assert checklist[0].responsible == 'client'
        assert checklist[1].responsible == 'team'
        assert checklist[2].responsible == 'both'

    @pytest.mark.unit
    def test_parse_launch_checklist_empty(self, parser):
        """Missing section returns empty list."""
        content = "No checklist\n\n---\n"
        result = parser._parse_launch_checklist(content)
        assert result['launch_checklist'] == []

    @pytest.mark.unit
    def test_parse_launch_checklist_not_determined(self, parser):
        """Section with 'не определён' returns empty list."""
        content = (
            "## 14. Чеклист запуска\n\n"
            "Чеклист не определён.\n\n"
            "---\n"
        )
        result = parser._parse_launch_checklist(content)
        assert result['launch_checklist'] == []


# =========================================================================
# TestParseAIRecommendations
# =========================================================================

class TestParseAIRecommendations:
    """Tests for _parse_ai_recommendations method."""

    @pytest.mark.unit
    def test_parse_ai_recommendations_with_effort_mapping(self, parser):
        """Recommendations with effort labels mapped to internal values."""
        content = (
            "## 15. Рекомендации AI-эксперта\n\n"
            "### 1. \U0001f534 Внедрить CRM-интеграцию\n\n"
            "**Ожидаемый эффект:** Увеличение конверсии на 30%\n\n"
            "*Приоритет: high | Затраты: Низкие*\n\n"
            "### 2. \U0001f7e1 Добавить чат-бот\n\n"
            "**Ожидаемый эффект:** Снижение нагрузки на операторов\n\n"
            "*Приоритет: medium | Затраты: Средние*\n\n"
            "### 3. \U0001f7e2 Настроить аналитику\n\n"
            "**Ожидаемый эффект:** Улучшение отчётности\n\n"
            "*Приоритет: low | Затраты: Высокие*\n\n"
            "---\n"
        )
        result = parser._parse_ai_recommendations(content)
        recs = result['ai_recommendations']

        assert len(recs) == 3
        assert recs[0].recommendation == 'Внедрить CRM-интеграцию'
        assert recs[0].impact == 'Увеличение конверсии на 30%'
        assert recs[0].priority == 'high'
        assert recs[0].effort == 'low'
        assert recs[1].effort == 'medium'
        assert recs[2].effort == 'high'

    @pytest.mark.unit
    def test_parse_ai_recommendations_empty(self, parser):
        """Missing section returns empty list."""
        content = "No recommendations\n\n---\n"
        result = parser._parse_ai_recommendations(content)
        assert result['ai_recommendations'] == []

    @pytest.mark.unit
    def test_parse_ai_recommendations_not_generated(self, parser):
        """Section with 'не сгенерированы' returns empty list."""
        content = (
            "## 15. Рекомендации AI-эксперта\n\n"
            "Рекомендации не сгенерированы — недостаточно данных.\n\n"
            "---\n"
        )
        result = parser._parse_ai_recommendations(content)
        assert result['ai_recommendations'] == []

    @pytest.mark.unit
    def test_parse_ai_recommendations_without_emoji(self, parser):
        """Recommendations without priority emoji are also parsed."""
        content = (
            "## 15. Рекомендации AI-эксперта\n\n"
            "### 1. Оптимизировать скрипты\n\n"
            "**Ожидаемый эффект:** Быстрее обработка\n\n"
            "*Приоритет: medium | Затраты: Низкие*\n\n"
            "---\n"
        )
        result = parser._parse_ai_recommendations(content)
        recs = result['ai_recommendations']

        assert len(recs) == 1
        assert recs[0].recommendation == 'Оптимизировать скрипты'
        assert recs[0].effort == 'low'


# =========================================================================
# TestParseToneOfVoice
# =========================================================================

class TestParseToneOfVoice:
    """Tests for _parse_tone_of_voice method."""

    @pytest.mark.unit
    def test_parse_tone_do_and_dont(self, parser):
        """Both Do and Don't guidelines are parsed."""
        content = (
            "## 16. Тон коммуникации\n\n"
            "### \u2705 Делать\n\n"
            "Использовать вежливый тон, обращаться по имени\n\n"
            "### \u274c Не делать\n\n"
            "Не использовать жаргон, не перебивать\n\n"
            "---\n"
        )
        result = parser._parse_tone_of_voice(content)
        tone = result['tone_of_voice']

        assert 'do' in tone
        assert 'dont' in tone
        assert tone['do'] == 'Использовать вежливый тон, обращаться по имени'
        assert tone['dont'] == 'Не использовать жаргон, не перебивать'

    @pytest.mark.unit
    def test_parse_tone_empty(self, parser):
        """Missing section returns empty dict."""
        content = "No tone guidelines\n\n---\n"
        result = parser._parse_tone_of_voice(content)
        assert result['tone_of_voice'] == {}

    @pytest.mark.unit
    def test_parse_tone_not_determined(self, parser):
        """Section with 'не определён' returns empty dict."""
        content = (
            "## 16. Тон коммуникации\n\n"
            "Тон коммуникации не определён.\n\n"
            "---\n"
        )
        result = parser._parse_tone_of_voice(content)
        assert result['tone_of_voice'] == {}


# =========================================================================
# TestParseErrorHandlingScripts
# =========================================================================

class TestParseErrorHandlingScripts:
    """Tests for _parse_error_handling_scripts method."""

    @pytest.mark.unit
    def test_parse_error_scripts_all_three(self, parser):
        """All three error scripts are parsed."""
        content = (
            "## 17. Скрипты обработки ошибок\n\n"
            "**\U0001f914 Не понял запрос:**\n"
            "> \u00abИзвините, я не совсем понял. Можете повторить?\u00bb\n\n"
            "**\u26a0\ufe0f Техническая проблема:**\n"
            "> \u00abК сожалению, возникла техническая проблема. Попробуйте позже.\u00bb\n\n"
            "**\U0001f6ab Вне компетенции:**\n"
            "> \u00abЭтот вопрос лучше обсудить с менеджером. Перевожу вас.\u00bb\n\n"
            "---\n"
        )
        result = parser._parse_error_handling_scripts(content)
        scripts = result['error_handling_scripts']

        assert len(scripts) == 3
        assert scripts['not_understood'] == 'Извините, я не совсем понял. Можете повторить?'
        assert scripts['technical_issue'] == 'К сожалению, возникла техническая проблема. Попробуйте позже.'
        assert scripts['out_of_scope'] == 'Этот вопрос лучше обсудить с менеджером. Перевожу вас.'

    @pytest.mark.unit
    def test_parse_error_scripts_empty(self, parser):
        """Missing section returns empty dict."""
        content = "No error scripts\n\n---\n"
        result = parser._parse_error_handling_scripts(content)
        assert result['error_handling_scripts'] == {}

    @pytest.mark.unit
    def test_parse_error_scripts_not_determined(self, parser):
        """Section with 'не определены' returns empty dict."""
        content = (
            "## 17. Скрипты обработки ошибок\n\n"
            "Скрипты не определены.\n\n"
            "---\n"
        )
        result = parser._parse_error_handling_scripts(content)
        assert result['error_handling_scripts'] == {}


# =========================================================================
# TestParseFollowUpSequence
# =========================================================================

class TestParseFollowUpSequence:
    """Tests for _parse_follow_up_sequence method."""

    @pytest.mark.unit
    def test_parse_follow_up_sequence_bullets(self, parser):
        """Follow-up items are parsed from bullets."""
        content = (
            "## 18. Последовательность follow-up\n\n"
            "- Отправить email с итогами звонка\n"
            "- Через 2 дня: напомнить о предложении\n"
            "- Через неделю: финальный follow-up\n\n"
            "---\n"
        )
        result = parser._parse_follow_up_sequence(content)
        items = result['follow_up_sequence']

        assert len(items) == 3
        assert items[0] == 'Отправить email с итогами звонка'
        assert items[1] == 'Через 2 дня: напомнить о предложении'
        assert items[2] == 'Через неделю: финальный follow-up'

    @pytest.mark.unit
    def test_parse_follow_up_sequence_empty(self, parser):
        """Missing section returns empty list."""
        content = "No follow-up\n\n---\n"
        result = parser._parse_follow_up_sequence(content)
        assert result['follow_up_sequence'] == []


# =========================================================================
# TestHelperMethods
# =========================================================================

class TestHelperMethods:
    """Tests for helper methods _extract_section and _parse_bullets."""

    @pytest.mark.unit
    def test_extract_section_found(self, parser):
        """Section content is extracted by header pattern."""
        content = (
            "## 6. FAQ с ответами\n\n"
            "Some FAQ content here.\n\n"
            "---\n"
        )
        section = parser._extract_section(content, r'## 6\. FAQ с ответами')
        assert section == 'Some FAQ content here.'

    @pytest.mark.unit
    def test_extract_section_not_found(self, parser):
        """Non-existent section returns None."""
        content = "Some random text\n\n---\n"
        section = parser._extract_section(content, r'## 99\. Nonexistent')
        assert section is None

    @pytest.mark.unit
    def test_parse_bullets_with_emoji_cleanup(self, parser):
        """Bullet parser removes known emoji prefixes."""
        text = (
            "- \u2705 Good practice\n"
            "- \u274c Bad practice\n"
            "- \U0001f525 Hot trend\n"
            "- Plain item\n"
            "- *Не указано*\n"
        )
        result = parser._parse_bullets(text)

        assert 'Good practice' in result
        assert 'Bad practice' in result
        assert 'Hot trend' in result
        assert 'Plain item' in result
        # '*He указано*' should be excluded
        assert '*Не указано*' not in result
        assert len(result) == 4


# =========================================================================
# TestFullParse
# =========================================================================

class TestFullParse:
    """Tests for the main parse() method and convenience function."""

    @pytest.mark.unit
    def test_parse_full_document(self, parser):
        """End-to-end parse of a complete markdown document."""
        base = _make_base_anketa()
        content = (
            "# Анкета\n\n"
            "## 1. Информация о компании\n\n"
            "| Поле | Значение |\n"
            "| --- | --- |\n"
            "| Компания | New Corp |\n"
            "| Отрасль | Healthcare |\n"
            "| Специализация | Telemedicine |\n"
            "| Сайт | https://newcorp.com |\n"
            "| Контактное лицо | Jane Smith |\n"
            "| Должность | CTO |\n\n"
            "### Описание бизнеса\n\n"
            "Telemedicine platform.\n\n"
            "### Услуги / Продукты\n\n"
            "- Online consultations\n"
            "- Lab results\n\n"
            "### Типы клиентов\n\n"
            "- Patients\n"
            "- Doctors\n\n"
            "---\n\n"
            "## 2. Бизнес-контекст\n\n"
            "### Текущие проблемы\n\n"
            "- Long wait times\n\n"
            "### Цели автоматизации\n\n"
            "- Reduce wait times\n\n"
            "### Ограничения\n\n"
            "- HIPAA compliance\n\n"
            "---\n\n"
            "## 3. Голосовой агент\n\n"
            "| Поле | Значение |\n"
            "| --- | --- |\n"
            "| Имя агента | Dr. Bot |\n"
            "| Назначение | Patient scheduling |\n"
            "| Язык | en |\n"
            "| Голос | female, calm |\n"
            "| Тип звонков | Входящие и исходящие |\n\n"
            "### Типичные вопросы (FAQ)\n\n"
            "- How to book?\n\n"
            "---\n\n"
            "## 4. Все функции агента\n\n"
            "### 1. Scheduling\n\n"
            "Book appointments\n\n"
            "*Приоритет: high*\n\n"
            "### 2. Reminders\n\n"
            "Send reminders\n\n"
            "*Приоритет: medium*\n\n"
            "---\n\n"
            "## 5. Интеграции\n\n"
            "| Система | Назначение | Требуется |\n"
            "| ------ | ------ | ------ |\n"
            "| EHR | Patient records | Да |\n\n"
            "---\n\n"
            "## 6. FAQ с ответами\n\n"
            "### 1. How to book an appointment? [process]\n\n"
            "> Call us or use the app.\n\n"
            "---\n\n"
            "## 7. Работа с возражениями\n\n"
            "### 1. \u00abI don't trust AI\u00bb\n\n"
            "**Ответ:** Our AI is supervised by doctors.\n\n"
            "**Далее:** Offer human callback\n\n"
            "---\n\n"
            "## 8. Пример диалога\n\n"
            "**Агент:** Hello! How can I help? *(greeting)*\n\n"
            "**Клиент:** I need an appointment *(booking)*\n\n"
            "---\n\n"
            "## 9. Финансовая модель\n\n"
            "| Метрика | Значение | Источник | Примечание |\n"
            "| ------- | ------- | ------- | ------- |\n"
            "| Cost per call | $0.50 | AI-бенчмарк | — |\n\n"
            "---\n\n"
            "## 10. Анализ рынка\n\n"
            "### Конкуренты\n\n"
            "#### MedBot\n"
            "*Цены: $500-1000/mo*\n\n"
            "\u2705 Good NLU\n"
            "\u274c Expensive\n\n"
            "### Рыночные инсайты\n\n"
            "- \U0001f525 Telehealth growing 25% YoY\n\n"
            "### Конкурентные преимущества клиента\n\n"
            "- HIPAA certified\n\n"
            "---\n\n"
            "## 11. Целевые сегменты\n\n"
            "### 1. Elderly patients\n\n"
            "People over 65\n\n"
            "**Болевые точки:**\n"
            "\U0001f613 Difficulty with apps\n\n"
            "**Триггеры:**\n"
            "\u26a1 Need for regular checkups\n\n"
            "---\n\n"
            "## 12. Правила эскалации\n\n"
            "| Триггер | Срочность | Действие |\n"
            "| ------- | ------- | ------- |\n"
            "| Emergency | \U0001f6a8 Немедленно | Transfer to nurse |\n\n"
            "---\n\n"
            "## 13. KPI и метрики успеха\n\n"
            "| KPI | Цель | Бенчмарк | Измерение |\n"
            "| ---- | ---- | ---- | ---- |\n"
            "| Call completion | 90% | 85% | Auto |\n\n"
            "---\n\n"
            "## 14. Чеклист запуска\n\n"
            "- \u2610 Upload patient FAQ \u2014 \U0001f464 Клиент **(обязательно)**\n\n"
            "---\n\n"
            "## 15. Рекомендации AI-эксперта\n\n"
            "### 1. \U0001f534 Add voice biometrics\n\n"
            "**Ожидаемый эффект:** Improve security\n\n"
            "*Приоритет: high | Затраты: Средние*\n\n"
            "---\n\n"
            "## 16. Тон коммуникации\n\n"
            "### \u2705 Делать\n\n"
            "Be empathetic\n\n"
            "### \u274c Не делать\n\n"
            "Don't rush\n\n"
            "---\n\n"
            "## 17. Скрипты обработки ошибок\n\n"
            "**\U0001f914 Не понял запрос:**\n"
            "> \u00abCould you please repeat that?\u00bb\n\n"
            "**\u26a0\ufe0f Техническая проблема:**\n"
            "> \u00abWe're experiencing issues. Please hold.\u00bb\n\n"
            "**\U0001f6ab Вне компетенции:**\n"
            "> \u00abLet me transfer you to a specialist.\u00bb\n\n"
            "---\n\n"
            "## 18. Последовательность follow-up\n\n"
            "- Send appointment confirmation\n"
            "- Reminder 24h before\n\n"
            "---\n"
        )
        result = parser.parse(content, base)

        # Verify it returns a FinalAnketa
        assert isinstance(result, FinalAnketa)

        # Company info
        assert result.company_name == 'New Corp'
        assert result.industry == 'Healthcare'
        assert result.specialization == 'Telemedicine'
        assert result.website == 'https://newcorp.com'
        assert result.contact_name == 'Jane Smith'
        assert result.contact_role == 'CTO'
        assert result.business_description == 'Telemedicine platform.'
        assert result.services == ['Online consultations', 'Lab results']
        assert result.client_types == ['Patients', 'Doctors']

        # Business context
        assert result.current_problems == ['Long wait times']
        assert result.business_goals == ['Reduce wait times']
        assert result.constraints == ['HIPAA compliance']

        # Voice agent
        assert result.agent_name == 'Dr. Bot'
        assert result.agent_purpose == 'Patient scheduling'
        assert result.language == 'en'
        assert result.voice_gender == 'female'
        assert result.voice_tone == 'calm'
        assert result.call_direction == 'both'
        assert result.typical_questions == ['How to book?']

        # Functions
        assert len(result.agent_functions) == 2
        assert result.main_function.name == 'Scheduling'
        assert len(result.additional_functions) == 1

        # Integrations
        assert len(result.integrations) == 1
        assert result.integrations[0].name == 'EHR'

        # FAQ
        assert len(result.faq_items) == 1
        assert result.faq_items[0].category == 'process'

        # Objections
        assert len(result.objection_handlers) == 1

        # Dialogue
        assert len(result.sample_dialogue) == 2

        # Financial
        assert len(result.financial_metrics) == 1

        # Market
        assert len(result.competitors) == 1
        assert len(result.market_insights) == 1
        assert result.competitive_advantages == ['HIPAA certified']

        # Target segments
        assert len(result.target_segments) == 1

        # Escalation
        assert len(result.escalation_rules) == 1

        # KPIs
        assert len(result.success_kpis) == 1

        # Checklist
        assert len(result.launch_checklist) == 1

        # AI Recommendations
        assert len(result.ai_recommendations) == 1

        # Tone
        assert result.tone_of_voice.get('do') == 'Be empathetic'
        assert result.tone_of_voice.get('dont') == "Don't rush"

        # Error scripts
        assert len(result.error_handling_scripts) == 3

        # Follow-up
        assert len(result.follow_up_sequence) == 2

        # Metadata is preserved from base
        assert result.anketa_version == base.anketa_version
        assert result.created_at == base.created_at

    @pytest.mark.unit
    def test_parse_empty_document(self, parser):
        """Parsing empty string preserves base anketa values."""
        base = _make_base_anketa(
            company_name="Original",
            industry="Finance",
            agent_name="Advisor",
        )
        result = parser.parse("", base)

        assert isinstance(result, FinalAnketa)
        # Base values preserved when not overwritten
        assert result.company_name == 'Original'
        assert result.industry == 'Finance'
        assert result.agent_name == 'Advisor'

    @pytest.mark.unit
    def test_parse_anketa_markdown_convenience(self, parser):
        """Module-level convenience function works same as parser.parse()."""
        base = _make_base_anketa()
        content = (
            "| Компания | Convenience Corp |\n"
            "| Отрасль | Retail |\n\n"
            "---\n"
        )
        result = parse_anketa_markdown(content, base)

        assert isinstance(result, FinalAnketa)
        assert result.company_name == 'Convenience Corp'
        assert result.industry == 'Retail'
