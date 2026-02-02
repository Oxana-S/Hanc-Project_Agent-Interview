"""
Consultant Interviewer.

Главный класс AI-консультанта с 4 фазами.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.models import InterviewPattern, CompletedAnketa
from src.interview.phases import (
    FieldStatus, FieldPriority, CollectedInfo, ANKETA_FIELDS
)
from src.consultant.phases import ConsultantPhase
from src.consultant.models import (
    BusinessAnalysis, PainPoint, Opportunity,
    ProposedSolution, ProposedFunction, ProposedIntegration
)
from src.llm.deepseek import DeepSeekClient
from src.config.prompt_loader import get_prompt, render_prompt
from src.config.locale_loader import t

console = Console()


class ConsultantInterviewer:
    """
    AI-Консультант с 4 фазами.

    DISCOVERY → ANALYSIS → PROPOSAL → REFINEMENT

    Использует:
    - DeepSeek для reasoning и анализа
    - Research Engine для внешних данных (опционально)
    - YAML промпты (вне кода)
    """

    def __init__(
        self,
        pattern: InterviewPattern = InterviewPattern.INTERACTION,
        deepseek_client: Optional[DeepSeekClient] = None,
        research_engine: Optional[Any] = None,  # ResearchEngine
        locale: str = "ru"
    ):
        """
        Инициализация консультанта.

        Args:
            pattern: Паттерн интервью (INTERACTION/MANAGEMENT)
            deepseek_client: Клиент DeepSeek API
            research_engine: Research Engine (опционально)
            locale: Локаль для UI текстов
        """
        self.pattern = pattern
        self.deepseek = deepseek_client or DeepSeekClient()
        self.research_engine = research_engine
        self.locale = locale

        # Состояние
        self.session_id = str(uuid.uuid4())
        self.phase = ConsultantPhase.DISCOVERY
        self.start_time = datetime.now(timezone.utc)

        # Собранные данные
        self.collected = CollectedInfo()
        self.dialogue_history: List[Dict[str, str]] = []

        # Результаты фаз
        self.business_analysis: Optional[BusinessAnalysis] = None
        self.proposed_solution: Optional[ProposedSolution] = None

        # Настройки
        self.discovery_min_turns = 5
        self.discovery_max_turns = 15

    # ===== MAIN RUN =====

    async def run(self) -> Dict[str, Any]:
        """
        Запуск консультации.

        Returns:
            Результат: anketa, files, stats
        """
        self._show_welcome()

        try:
            # Фаза 1: Discovery
            await self._discovery_phase()

            # Фаза 2: Analysis
            await self._analysis_phase()

            # Фаза 3: Proposal
            await self._proposal_phase()

            # Фаза 4: Refinement
            return await self._refinement_phase()

        except KeyboardInterrupt:
            console.print("\n[yellow]Консультация прервана[/yellow]")
            return {"status": "interrupted", "collected": self.collected.to_anketa_dict()}

    def _show_welcome(self):
        """Показать приветствие."""
        phase_flow = " → ".join([
            f"[magenta]{ConsultantPhase.DISCOVERY.display_name}[/magenta]",
            f"[cyan]{ConsultantPhase.ANALYSIS.display_name}[/cyan]",
            f"[yellow]{ConsultantPhase.PROPOSAL.display_name}[/yellow]",
            f"[green]{ConsultantPhase.REFINEMENT.display_name}[/green]",
        ])

        console.print(Panel(
            f"[bold cyan]AI-КОНСУЛЬТАНТ[/bold cyan]\n\n"
            f"Паттерн: [green]{self.pattern.value}[/green]\n\n"
            f"[bold]Как это работает:[/bold]\n"
            f"{phase_flow}\n\n"
            f"[dim]Команды: 'done' - дальше, 'status' - прогресс, 'quit' - выход[/dim]",
            title="Voice Interviewer v3.0",
            border_style="cyan"
        ))

    # ===== PHASE 1: DISCOVERY =====

    async def _discovery_phase(self):
        """Фаза Discovery — свободный диалог."""
        self._show_phase_banner(ConsultantPhase.DISCOVERY)

        system_prompt = get_prompt("consultant/discovery", "system_prompt")
        turn_count = 0

        # Начальное сообщение
        initial_message = get_prompt("consultant/discovery", "initial_message")
        self._show_ai_message(initial_message)
        self.dialogue_history.append({"role": "assistant", "content": initial_message})

        while self.phase == ConsultantPhase.DISCOVERY:
            turn_count += 1

            # Получаем ввод
            user_input = Prompt.ask("\n[green]Вы[/green]")

            if self._handle_command(user_input, turn_count):
                continue

            if not user_input.strip():
                continue

            # Добавляем в историю
            self.dialogue_history.append({"role": "user", "content": user_input})

            # Проверяем упоминание сайта
            website = self._extract_website(user_input)
            if website:
                self.collected.update_field("website", website, source="discovery")

            # Получаем ответ AI
            console.print("[dim]Думаю...[/dim]")

            ai_response = await self._get_discovery_response(system_prompt, user_input)

            # Фоново извлекаем информацию
            await self._extract_info_from_dialogue(user_input, ai_response)

            # Показываем ответ
            self._show_ai_message(ai_response)
            self.dialogue_history.append({"role": "assistant", "content": ai_response})

            # Проверяем готовность к переходу
            if turn_count >= self.discovery_max_turns:
                console.print("\n[yellow]Достаточно информации для анализа![/yellow]")
                break

            if self._ready_for_analysis(turn_count):
                if self._confirm_transition("Перейти к анализу?"):
                    break

        self._transition_phase(ConsultantPhase.ANALYSIS)

    async def _get_discovery_response(self, system_prompt: str, user_input: str) -> str:
        """Получить ответ AI в фазе Discovery."""
        # Формируем контекст
        context = f"""
СОБРАННАЯ ИНФОРМАЦИЯ:
{json.dumps(self.collected.to_anketa_dict(), ensure_ascii=False, indent=2)}
"""
        full_system = system_prompt + "\n\n" + context

        messages = [
            {"role": "system", "content": full_system}
        ] + self.dialogue_history[-10:]

        response = await self.deepseek.chat(messages, temperature=0.7, max_tokens=1024)
        return response

    def _ready_for_analysis(self, turn_count: int) -> bool:
        """Проверить готовность к переходу в Analysis."""
        if turn_count < self.discovery_min_turns:
            return False

        stats = self.collected.get_completion_stats()

        # Если заполнено 30%+ обязательных полей
        if stats['required_percentage'] >= 30:
            return True

        # Если есть базовая информация
        has_company = self.collected.fields.get('company_name', {})
        has_industry = self.collected.fields.get('industry', {})

        if has_company and has_industry:
            return True

        return False

    # ===== PHASE 2: ANALYSIS =====

    async def _analysis_phase(self):
        """Фаза Analysis — анализ и исследование."""
        self._show_phase_banner(ConsultantPhase.ANALYSIS)

        # Запуск исследования (если есть Research Engine)
        research_data = None
        if self.research_engine:
            console.print("[dim]Провожу исследование...[/dim]")
            research_data = await self._run_research()

        # Формируем анализ
        console.print("[dim]Анализирую бизнес...[/dim]")
        self.business_analysis = await self._create_business_analysis(research_data)

        # Показываем анализ
        analysis_text = self._format_analysis(self.business_analysis, research_data)
        self._show_ai_message(analysis_text)

        # Получаем подтверждение
        while True:
            confirmation = Prompt.ask(
                "\n[cyan]Я правильно понял? (да/нет/уточнить)[/cyan]",
                default="да"
            )

            if confirmation.lower() in ['да', 'yes', 'y', 'д']:
                self.business_analysis.user_confirmed = True
                console.print("[green]Отлично! Перехожу к предложению.[/green]")
                break
            elif confirmation.lower() in ['нет', 'no', 'n', 'н']:
                correction = Prompt.ask("[yellow]Что я понял неверно?[/yellow]")
                await self._apply_analysis_correction(correction)
                # Показываем обновлённый анализ
                analysis_text = self._format_analysis(self.business_analysis, research_data)
                self._show_ai_message(analysis_text)
            else:
                clarification = Prompt.ask("[yellow]Что уточнить?[/yellow]")
                await self._apply_analysis_correction(clarification)

        self._transition_phase(ConsultantPhase.PROPOSAL)

    async def _create_business_analysis(self, research_data: Optional[Dict] = None) -> BusinessAnalysis:
        """Создать анализ бизнеса через LLM."""
        collected_data = self.collected.to_anketa_dict()
        dialogue_text = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in self.dialogue_history
        ])

        prompt = f"""Проанализируй диалог с клиентом и собранные данные.

ДИАЛОГ:
{dialogue_text}

СОБРАННЫЕ ДАННЫЕ:
{json.dumps(collected_data, ensure_ascii=False, indent=2)}

{"ДАННЫЕ ИССЛЕДОВАНИЯ:" + json.dumps(research_data, ensure_ascii=False) if research_data else ""}

Верни JSON:
{{
    "company_name": "название компании",
    "industry": "отрасль",
    "specialization": "специализация",
    "business_scale": "small/medium/large",
    "client_type": "B2B/B2C/mixed",
    "pain_points": [
        {{"description": "описание боли", "severity": "high/medium/low"}}
    ],
    "opportunities": [
        {{"description": "возможность автоматизации", "expected_impact": "ожидаемый эффект"}}
    ],
    "constraints": ["ограничение 1", "ограничение 2"]
}}"""

        response = await self.deepseek.chat([
            {"role": "user", "content": prompt}
        ], temperature=0.3)

        try:
            # Парсим JSON
            json_text = response.strip()
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            start = json_text.find('{')
            end = json_text.rfind('}')
            if start != -1 and end != -1:
                json_text = json_text[start:end+1]

            data = json.loads(json_text)

            return BusinessAnalysis(
                company_name=data.get("company_name"),
                industry=data.get("industry"),
                specialization=data.get("specialization"),
                business_scale=data.get("business_scale", "unknown"),
                client_type=data.get("client_type", "unknown"),
                pain_points=[PainPoint(**p) for p in data.get("pain_points", [])],
                opportunities=[Opportunity(**o) for o in data.get("opportunities", [])],
                constraints=data.get("constraints", []),
            )
        except Exception as e:
            console.print(f"[red]Ошибка анализа: {e}[/red]")
            return BusinessAnalysis()

    def _format_analysis(self, analysis: BusinessAnalysis, research_data: Optional[Dict] = None) -> str:
        """Форматировать анализ для отображения."""
        lines = ["На основе нашего разговора, вот что я понял:"]
        lines.append("")

        # Профиль
        lines.append("**Ваша компания:**")
        if analysis.company_name:
            lines.append(f"- Название: {analysis.company_name}")
        if analysis.industry:
            lines.append(f"- Отрасль: {analysis.industry}")
        if analysis.specialization:
            lines.append(f"- Специализация: {analysis.specialization}")
        if analysis.client_type != "unknown":
            lines.append(f"- Тип клиентов: {analysis.client_type}")

        # Боли
        if analysis.pain_points:
            lines.append("")
            lines.append("**Главные боли, которые я услышал:**")
            for i, pain in enumerate(analysis.get_top_pains(5), 1):
                severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(pain.severity, "⚪")
                lines.append(f"{i}. {severity_icon} {pain.description}")

        # Возможности
        if analysis.opportunities:
            lines.append("")
            lines.append("**Возможности для автоматизации:**")
            for opp in analysis.opportunities[:3]:
                lines.append(f"- {opp.description}")
                if opp.expected_impact:
                    lines.append(f"  ↳ {opp.expected_impact}")

        # Ограничения
        if analysis.constraints:
            lines.append("")
            lines.append("**Ограничения:**")
            for constraint in analysis.constraints:
                lines.append(f"- {constraint}")

        # Исследование
        if research_data:
            lines.append("")
            lines.append("**Из исследования отрасли:**")
            for insight in research_data.get("industry_insights", [])[:3]:
                lines.append(f"- {insight}")

        return "\n".join(lines)

    async def _apply_analysis_correction(self, correction: str):
        """Применить корректировку к анализу."""
        prompt = f"""Пользователь хочет скорректировать анализ.

ТЕКУЩИЙ АНАЛИЗ:
{self.business_analysis.to_summary_text()}

КОРРЕКТИРОВКА ПОЛЬЗОВАТЕЛЯ:
{correction}

Обнови анализ с учётом корректировки. Верни обновлённый JSON."""

        # Для простоты пока просто добавляем корректировку в constraints
        self.business_analysis.constraints.append(f"Уточнение: {correction}")

    async def _run_research(self) -> Optional[Dict]:
        """Запустить Research Engine."""
        if not self.research_engine:
            return None

        try:
            website = self.collected.fields.get('website', {}).get('value')
            industry = self.collected.fields.get('industry', {}).get('value')

            return await self.research_engine.research(
                website=website,
                industry=industry,
                company_name=self.collected.fields.get('company_name', {}).get('value')
            )
        except Exception as e:
            console.print(f"[dim]Исследование недоступно: {e}[/dim]")
            return None

    # ===== PHASE 3: PROPOSAL =====

    async def _proposal_phase(self):
        """Фаза Proposal — предложение решения."""
        self._show_phase_banner(ConsultantPhase.PROPOSAL)

        console.print("[dim]Формирую предложение...[/dim]")

        # Генерируем предложение
        self.proposed_solution = await self._create_proposal()

        # Показываем
        proposal_text = self.proposed_solution.to_proposal_text()
        self._show_ai_message(proposal_text)

        # Обсуждение
        while True:
            response = Prompt.ask(
                "\n[cyan]Что думаете? (согласен/изменить/обсудить)[/cyan]",
                default="согласен"
            )

            if response.lower() in ['согласен', 'да', 'ok', 'ок', 'accept']:
                self.proposed_solution.user_confirmed = True
                console.print("[green]Отлично! Переходим к заполнению анкеты.[/green]")
                break
            elif response.lower() in ['изменить', 'modify', 'change']:
                change = Prompt.ask("[yellow]Что хотите изменить?[/yellow]")
                await self._apply_proposal_change(change)
                # Показываем обновлённое предложение
                proposal_text = self.proposed_solution.to_proposal_text()
                self._show_ai_message(proposal_text)
            else:
                discussion = Prompt.ask("[yellow]Что обсудить?[/yellow]")
                await self._discuss_proposal(discussion)

        self._transition_phase(ConsultantPhase.REFINEMENT)

    async def _create_proposal(self) -> ProposedSolution:
        """Создать предложение на основе анализа."""
        analysis_text = self.business_analysis.to_summary_text() if self.business_analysis else ""

        prompt = f"""На основе анализа бизнеса, создай предложение решения.

АНАЛИЗ:
{analysis_text}

Создай JSON:
{{
    "main_function": {{
        "name": "название главной функции",
        "description": "как работает",
        "reason": "почему это решит главную боль"
    }},
    "additional_functions": [
        {{"name": "функция", "description": "описание", "reason": "зачем"}}
    ],
    "integrations": [
        {{"name": "email/calendar/whatsapp/sms/crm", "needed": true/false, "reason": "зачем"}}
    ],
    "expected_results": "ожидаемый результат с метриками если возможно"
}}"""

        response = await self.deepseek.chat([
            {"role": "user", "content": prompt}
        ], temperature=0.4)

        try:
            json_text = response.strip()
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            start = json_text.find('{')
            end = json_text.rfind('}')
            if start != -1 and end != -1:
                json_text = json_text[start:end+1]

            data = json.loads(json_text)

            main_func = data.get("main_function", {})

            return ProposedSolution(
                main_function=ProposedFunction(
                    name=main_func.get("name", "Основная функция"),
                    description=main_func.get("description", ""),
                    reason=main_func.get("reason", ""),
                    is_main=True
                ),
                additional_functions=[
                    ProposedFunction(**f, is_main=False)
                    for f in data.get("additional_functions", [])
                ],
                integrations=[
                    ProposedIntegration(**i)
                    for i in data.get("integrations", [])
                ],
                expected_results=data.get("expected_results")
            )
        except Exception as e:
            console.print(f"[red]Ошибка создания предложения: {e}[/red]")
            return ProposedSolution(
                main_function=ProposedFunction(
                    name="Голосовой агент",
                    description="Автоматизация общения с клиентами",
                    reason="Решение выявленных проблем",
                    is_main=True
                )
            )

    async def _apply_proposal_change(self, change: str):
        """Применить изменение к предложению."""
        self.proposed_solution.modifications.append(change)
        console.print(f"[dim]Учтено: {change}[/dim]")

    async def _discuss_proposal(self, topic: str):
        """Обсудить аспект предложения."""
        prompt = f"""Клиент хочет обсудить: {topic}

Текущее предложение: {self.proposed_solution.to_proposal_text()}

Ответь на вопрос клиента кратко и по делу."""

        response = await self.deepseek.chat([
            {"role": "user", "content": prompt}
        ], temperature=0.5)

        self._show_ai_message(response)

    # ===== PHASE 4: REFINEMENT =====

    async def _refinement_phase(self) -> Dict[str, Any]:
        """Фаза Refinement — заполнение анкеты."""
        self._show_phase_banner(ConsultantPhase.REFINEMENT)

        # Переносим данные из анализа и предложения
        self._populate_from_analysis()
        self._populate_from_proposal()

        # Показываем прогресс
        stats = self.collected.get_completion_stats()
        console.print(f"\n[bold]Уже заполнено: {stats['complete']}/{stats['total']} полей[/bold]")

        # Собираем недостающие поля
        missing_required = self.collected.get_missing_required_fields()
        missing_important = self.collected.get_missing_important_fields()

        fields_to_ask = missing_required + missing_important[:5]

        if fields_to_ask:
            intro = get_prompt("consultant/refinement", "intro_message")
            console.print(Panel(intro, border_style="green"))

            for i, field in enumerate(fields_to_ask, 1):
                await self._ask_refinement_question(field, i, len(fields_to_ask))

        # Генерация финальной анкеты
        console.print("\n[dim]Генерирую финальную анкету...[/dim]")

        from src.llm.anketa_generator import export_full_anketa

        interview_data = self._create_completed_anketa()

        try:
            result = await export_full_anketa(interview_data)
        except Exception as e:
            console.print(f"[red]Ошибка генерации: {e}[/red]")
            return {"status": "error", "error": str(e)}

        # Показываем результаты
        self._show_completion(result)

        self._transition_phase(ConsultantPhase.COMPLETED)

        return {
            "status": "completed",
            "anketa": result.get('anketa'),
            "files": {
                "json": result.get('json'),
                "markdown": result.get('markdown')
            },
            "stats": self._get_session_stats()
        }

    async def _ask_refinement_question(self, field, current: int, total: int):
        """Задать вопрос для поля."""
        console.print(f"\n[dim]━━━ Поле {current}/{total} ━━━[/dim]")

        priority_icon = "⭐" if field.priority == FieldPriority.REQUIRED else "○"
        console.print(f"[cyan]{priority_icon} {field.display_name}[/cyan]")

        # Предложение на основе контекста
        suggestion = self._get_field_suggestion(field)
        if suggestion:
            console.print(f"[dim]Предлагаю: {suggestion}[/dim]")

        answer = Prompt.ask("[green]Ваш ответ (или Enter для предложения)[/green]")

        if not answer.strip() and suggestion:
            answer = suggestion

        if answer.lower() == 'skip':
            return

        self.collected.update_field(field.field_id, answer, source="refinement", confidence=1.0)
        console.print("[green]✓[/green]")

    def _get_field_suggestion(self, field) -> Optional[str]:
        """Получить предложение для поля."""
        # На основе собранных данных
        if field.field_id == "company_name" and self.business_analysis:
            return self.business_analysis.company_name
        if field.field_id == "industry" and self.business_analysis:
            return self.business_analysis.industry

        # Из примеров в поле
        if field.examples:
            return field.examples[0]

        return None

    def _populate_from_analysis(self):
        """Заполнить поля из анализа."""
        if not self.business_analysis:
            return

        if self.business_analysis.company_name:
            self.collected.update_field("company_name", self.business_analysis.company_name,
                                        source="analysis", confidence=0.9)
        if self.business_analysis.industry:
            self.collected.update_field("industry", self.business_analysis.industry,
                                        source="analysis", confidence=0.9)
        if self.business_analysis.specialization:
            self.collected.update_field("specialization", self.business_analysis.specialization,
                                        source="analysis", confidence=0.8)

        # Боли → current_problems
        if self.business_analysis.pain_points:
            problems = [p.description for p in self.business_analysis.pain_points]
            self.collected.update_field("current_problems", problems,
                                        source="analysis", confidence=0.8)

    def _populate_from_proposal(self):
        """Заполнить поля из предложения."""
        if not self.proposed_solution:
            return

        # Назначение агента
        self.collected.update_field(
            "agent_purpose",
            self.proposed_solution.main_function.description,
            source="proposal",
            confidence=0.9
        )

        # Интеграции
        integrations = [i.name for i in self.proposed_solution.get_needed_integrations()]
        if integrations:
            self.collected.update_field("integrations", integrations,
                                        source="proposal", confidence=0.8)

    def _create_completed_anketa(self) -> CompletedAnketa:
        """Создать CompletedAnketa для экспорта."""
        data = self.collected.to_anketa_dict()
        duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()

        return CompletedAnketa(
            anketa_id=str(uuid.uuid4()),
            interview_id=self.session_id,
            pattern=self.pattern,
            created_at=datetime.now(timezone.utc),
            interview_duration_seconds=duration,
            company_name=data.get("company_name", "Не указано"),
            industry=data.get("industry", "Не указано"),
            language=data.get("language", "Русский"),
            agent_purpose=data.get("agent_purpose", "Не указано"),
            agent_name=data.get("agent_name", "Агент"),
            tone=data.get("tone", "Дружелюбный"),
            contact_person="",
            contact_email=data.get("contact_email", ""),
            contact_phone=data.get("contact_phone", ""),
            full_responses=data,
            quality_metrics=self.collected.get_completion_stats()
        )

    def _show_completion(self, result: Dict[str, Any]):
        """Показать результаты."""
        duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()

        console.print("\n" + "=" * 50)
        console.print("[bold green]КОНСУЛЬТАЦИЯ ЗАВЕРШЕНА![/bold green]")
        console.print("=" * 50)

        console.print(f"\n[bold]Статистика:[/bold]")
        console.print(f"  Длительность: {duration/60:.1f} мин")
        console.print(f"  Сообщений: {len(self.dialogue_history)}")

        stats = self.collected.get_completion_stats()
        console.print(f"  Полей заполнено: {stats['complete']}/{stats['total']}")

        console.print(f"\n[bold]Файлы:[/bold]")
        console.print(f"  JSON: [cyan]{result.get('json', 'N/A')}[/cyan]")
        console.print(f"  Markdown: [cyan]{result.get('markdown', 'N/A')}[/cyan]")

    def _get_session_stats(self) -> Dict[str, Any]:
        """Статистика сессии."""
        duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        return {
            "session_id": self.session_id,
            "duration_seconds": duration,
            "dialogue_turns": len(self.dialogue_history),
            "completion_stats": self.collected.get_completion_stats()
        }

    # ===== HELPERS =====

    def _handle_command(self, user_input: str, turn_count: int) -> bool:
        """Обработать команду. Возвращает True если команда обработана."""
        cmd = user_input.lower().strip()

        if cmd == 'quit':
            raise KeyboardInterrupt()

        if cmd == 'status':
            self._show_status()
            return True

        if cmd == 'done':
            if turn_count >= self.discovery_min_turns:
                self.phase = ConsultantPhase.ANALYSIS
            else:
                console.print(f"[yellow]Минимум {self.discovery_min_turns} ходов (сейчас {turn_count})[/yellow]")
            return True

        return False

    def _show_phase_banner(self, phase: ConsultantPhase):
        """Показать баннер фазы."""
        colors = {
            ConsultantPhase.DISCOVERY: "magenta",
            ConsultantPhase.ANALYSIS: "cyan",
            ConsultantPhase.PROPOSAL: "yellow",
            ConsultantPhase.REFINEMENT: "green",
        }
        color = colors.get(phase, "white")

        description = t(f"phases.{phase.value}.description")

        console.print()
        console.print(Panel(
            f"[bold {color}]═══ {phase.display_name.upper()} ═══[/bold {color}]\n\n{description}",
            border_style=color
        ))

    def _show_ai_message(self, message: str):
        """Показать сообщение AI."""
        console.print(Panel(
            Markdown(message),
            title="[magenta]AI-Консультант[/magenta]",
            border_style="magenta"
        ))

    def _show_status(self):
        """Показать статус."""
        stats = self.collected.get_completion_stats()
        console.print(f"\n[bold]Статус:[/bold]")
        console.print(f"  Фаза: [cyan]{self.phase.display_name}[/cyan]")
        console.print(f"  Заполнено: {stats['complete']}/{stats['total']} ({stats['completion_percentage']:.0f}%)")

    def _transition_phase(self, new_phase: ConsultantPhase):
        """Перейти в новую фазу."""
        old_phase = self.phase
        self.phase = new_phase
        console.print(f"\n[dim]━━━ {old_phase.display_name} → {new_phase.display_name} ━━━[/dim]")

    def _confirm_transition(self, message: str) -> bool:
        """Запросить подтверждение перехода."""
        console.print(f"\n[cyan]{message} (да/нет)[/cyan]")
        response = Prompt.ask("", default="да")
        return response.lower() in ['да', 'yes', 'y', 'д']

    def _extract_website(self, text: str) -> Optional[str]:
        """Извлечь URL сайта из текста."""
        import re
        pattern = r'https?://[^\s]+'
        match = re.search(pattern, text)
        if match:
            return match.group(0)

        # Простые домены
        pattern = r'\b[\w-]+\.(ru|com|org|net|io)\b'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return f"https://{match.group(0)}"

        return None

    async def _extract_info_from_dialogue(self, user_message: str, ai_response: str):
        """Извлечь информацию из диалога."""
        prompt = f"""Извлеки информацию из диалога.

СООБЩЕНИЕ КЛИЕНТА: {user_message}

Верни JSON с извлечёнными данными (только явно упомянутые):
{{
    "company_name": "название или null",
    "industry": "отрасль или null",
    "business_description": "описание или null",
    "agent_purpose": "назначение или null"
}}"""

        try:
            response = await self.deepseek.chat([
                {"role": "user", "content": prompt}
            ], temperature=0.1, max_tokens=256)

            json_text = response.strip()
            start = json_text.find('{')
            end = json_text.rfind('}')
            if start != -1 and end != -1:
                json_text = json_text[start:end+1]

            info = json.loads(json_text)

            for field_id in ['company_name', 'industry', 'business_description', 'agent_purpose']:
                if info.get(field_id):
                    self.collected.update_field(field_id, info[field_id],
                                                source="discovery", confidence=0.7)
        except Exception:
            pass  # Извлечение не критично
