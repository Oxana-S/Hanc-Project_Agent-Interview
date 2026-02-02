#!/usr/bin/env python3
"""
Maximum Interview Mode — объединение Smart + Brainstormer.

Три фазы:
1. DISCOVERY - свободный консультативный диалог
2. STRUCTURED - целенаправленный сбор недостающих данных
3. SYNTHESIS - генерация полной анкеты

Ключевые принципы:
- Адаптивность: AI сам решает когда переходить между фазами
- Контекст: вся информация из Discovery используется в Structured
- Минимум вопросов: не спрашиваем то, что уже узнали
- Естественность: диалог, а не допрос
"""

import asyncio
import os
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.markdown import Markdown
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich import box

from src.models import InterviewPattern, CompletedAnketa
from src.interview.phases import (
    InterviewPhase, FieldStatus, FieldPriority,
    CollectedInfo, PhaseTransition, ANKETA_FIELDS
)
from src.llm.deepseek import DeepSeekClient
from src.llm.anketa_generator import export_full_anketa

load_dotenv()
console = Console()


class MaximumInterviewer:
    """
    Объединённый режим интервью: Discovery + Structured + Synthesis.

    Сочетает лучшее из Brainstormer (консультативный диалог) и
    Smart Interview (структурированный сбор данных с анализом).
    """

    def __init__(
        self,
        pattern: InterviewPattern = InterviewPattern.INTERACTION,
        deepseek_client: Optional[DeepSeekClient] = None
    ):
        self.pattern = pattern
        self.deepseek = deepseek_client or DeepSeekClient()

        # Состояние
        self.session_id = str(uuid.uuid4())
        self.phase = InterviewPhase.DISCOVERY
        self.start_time = datetime.now(timezone.utc)

        # Собранные данные
        self.collected = CollectedInfo()

        # История диалога
        self.dialogue_history: List[Dict[str, str]] = []

        # Переходы между фазами
        self.phase_transitions: List[PhaseTransition] = []

        # Настройки
        self.discovery_min_turns = 5       # Минимум ходов в Discovery
        self.discovery_max_turns = 15      # Максимум ходов в Discovery
        self.max_clarifications = 3        # Макс. уточнений на вопрос

    # ===== MAIN RUN =====

    async def run(self) -> Dict[str, Any]:
        """
        Запуск Maximum интервью.

        Returns:
            Словарь с результатами: anketa, files, stats
        """
        self._show_welcome()

        try:
            # Фаза 1: Discovery
            await self._discovery_phase()

            # Фаза 2: Structured
            await self._structured_phase()

            # Фаза 3: Synthesis
            return await self._synthesis_phase()

        except KeyboardInterrupt:
            console.print("\n[yellow]Интервью прервано[/yellow]")
            return {"status": "interrupted", "collected": self.collected.to_anketa_dict()}

    def _show_welcome(self):
        """Показать приветствие."""
        console.print(Panel(
            f"[bold cyan]🎯 MAXIMUM INTERVIEW MODE[/bold cyan]\n\n"
            f"Паттерн: [green]{self.pattern.value}[/green]\n\n"
            f"[bold]Как это работает:[/bold]\n"
            f"[dim]1.[/dim] [magenta]Discovery[/magenta] — свободный диалог о вашем бизнесе\n"
            f"[dim]2.[/dim] [yellow]Structured[/yellow] — уточняем недостающие детали\n"
            f"[dim]3.[/dim] [green]Synthesis[/green] — генерируем полную анкету\n\n"
            f"[dim]Команды: 'done' - завершить фазу, 'status' - прогресс, 'quit' - выход[/dim]",
            title="🤖 AI Interview Agent",
            border_style="cyan"
        ))

    # ===== PHASE 1: DISCOVERY =====

    async def _discovery_phase(self):
        """
        Фаза Discovery — свободный консультативный диалог.

        AI ведёт беседу, изучает бизнес, предлагает идеи.
        Фоново извлекает информацию в структуру.
        """
        self._show_phase_banner("DISCOVERY", "magenta",
            "Давайте познакомимся с вашим бизнесом!\n"
            "Расскажите о компании, и я помогу определить,\n"
            "какой голосовой агент вам нужен."
        )

        system_prompt = self._get_discovery_system_prompt()
        turn_count = 0

        # Начальное сообщение AI
        initial_message = await self._get_ai_response(
            system_prompt,
            "Привет! Я хочу создать голосового агента для бизнеса."
        )
        self._show_ai_message(initial_message)

        # Основной цикл Discovery
        while self.phase == InterviewPhase.DISCOVERY:
            turn_count += 1

            # Получаем ввод пользователя
            user_input = Prompt.ask("\n[green]Вы[/green]")

            # Обработка команд
            if user_input.lower() == 'quit':
                raise KeyboardInterrupt()

            if user_input.lower() == 'status':
                self._show_status()
                continue

            if user_input.lower() == 'done':
                if turn_count >= self.discovery_min_turns:
                    break
                else:
                    console.print(f"[yellow]Давайте ещё немного пообщаемся (ход {turn_count}/{self.discovery_min_turns})[/yellow]")
                    continue

            if not user_input.strip():
                continue

            # Получаем ответ AI
            console.print("[dim]🤖 Думаю...[/dim]")

            ai_response = await self._get_ai_response(system_prompt, user_input)

            # Фоново извлекаем информацию
            await self._extract_info_from_dialogue(user_input, ai_response)

            # Показываем ответ
            self._show_ai_message(ai_response)

            # Проверяем готовность к переходу
            if turn_count >= self.discovery_max_turns:
                console.print("\n[yellow]📊 Достаточно информации для продолжения![/yellow]")
                break

            if self._ready_for_structured(turn_count):
                console.print("\n[cyan]💡 Кажется, у меня достаточно информации о бизнесе.[/cyan]")
                console.print("[cyan]   Хотите перейти к уточняющим вопросам? (да/нет)[/cyan]")

                confirm = Prompt.ask("", default="да")
                if confirm.lower() in ['да', 'yes', 'y', 'д']:
                    break

        # Переход к следующей фазе
        self._transition_phase(InterviewPhase.DISCOVERY, InterviewPhase.STRUCTURED,
                               f"Завершено {turn_count} ходов диалога")

    def _get_discovery_system_prompt(self) -> str:
        """Системный промпт для фазы Discovery."""
        return """Ты - опытный бизнес-консультант по созданию голосовых AI-агентов.

ТВОЯ РОЛЬ:
Вместе с клиентом изучить его бизнес и помочь определить, какой голосовой агент ему нужен.

СТИЛЬ ОБЩЕНИЯ:
- Дружелюбный и заинтересованный
- Задаёшь уточняющие вопросы
- Предлагаешь конкретные идеи и варианты
- Приводишь примеры из похожих бизнесов
- Помогаешь клиенту увидеть возможности

СТРУКТУРА ДИАЛОГА:
1. Узнай о бизнесе (компания, чем занимается, клиенты)
2. Выясни текущие проблемы (что отнимает время, что хотят автоматизировать)
3. Предложи 2-3 варианта использования агента
4. Уточни детали по выбранному направлению

ВАЖНО:
- Не задавай больше 2 вопросов за раз
- После ответа клиента - предлагай что-то конкретное
- Если клиент не знает что ответить - предложи варианты
- Веди к конкретике, но не дави

Отвечай естественно, как в разговоре. В конце каждого ответа задай 1-2 вопроса или предложи варианты."""

    def _ready_for_structured(self, turn_count: int) -> bool:
        """Проверить готовность к переходу в Structured фазу."""
        if turn_count < self.discovery_min_turns:
            return False

        # Проверяем заполненность ключевых полей
        stats = self.collected.get_completion_stats()

        # Если заполнено хотя бы 30% обязательных полей
        if stats['required_percentage'] >= 30:
            return True

        # Если есть информация о компании и назначении
        has_company = self.collected.fields['company_name'].status != FieldStatus.EMPTY
        has_purpose = self.collected.fields['agent_purpose'].status != FieldStatus.EMPTY

        return has_company and has_purpose

    # ===== PHASE 2: STRUCTURED =====

    async def _structured_phase(self):
        """
        Фаза Structured — целенаправленный сбор недостающих данных.

        AI определяет какие поля не заполнены и задаёт конкретные вопросы.
        Каждый ответ анализируется, при необходимости задаются уточнения.
        """
        missing = self.collected.get_missing_required_fields()
        missing_important = self.collected.get_missing_important_fields()

        self._show_phase_banner("STRUCTURED", "yellow",
            f"Осталось уточнить {len(missing)} обязательных\n"
            f"и {len(missing_important)} важных параметров."
        )

        # Обрабатываем сначала обязательные, потом важные поля
        fields_to_ask = missing + missing_important[:5]  # Лимитируем важные

        for i, field in enumerate(fields_to_ask, 1):
            self._show_field_question(field, i, len(fields_to_ask))

            # Генерируем контекстный вопрос
            question = await self._generate_contextual_question(field)
            console.print(Panel(question, border_style="yellow"))

            # Получаем ответ
            answer = Prompt.ask("\n[green]Ваш ответ[/green]")

            if answer.lower() == 'quit':
                raise KeyboardInterrupt()

            if answer.lower() == 'skip':
                console.print("[dim]Пропущено[/dim]")
                continue

            if answer.lower() == 'status':
                self._show_status()
                continue

            # Анализируем ответ
            console.print("[dim]🤖 Анализирую...[/dim]")

            analysis = await self._analyze_answer(field, answer)

            # Показываем оценку
            score = analysis.get('completeness_score', 0.5)
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            console.print(f"[dim]Полнота: [{bar}] {score * 100:.0f}%[/dim]")

            # Сохраняем ответ
            self.collected.update_field(field.field_id, answer, source="structured", confidence=score)

            # Если нужны уточнения
            if analysis.get('needs_clarification') and analysis.get('clarification_questions'):
                await self._handle_clarifications(field, analysis, answer)
            else:
                console.print(f"[green]✓ {analysis.get('reasoning', 'Принято')}[/green]")

            # Показываем прогресс
            self._show_mini_progress()

        # Переход к Synthesis
        self._transition_phase(InterviewPhase.STRUCTURED, InterviewPhase.SYNTHESIS,
                               f"Обработано {len(fields_to_ask)} полей")

    async def _generate_contextual_question(self, field) -> str:
        """Генерировать вопрос с учётом уже собранной информации."""
        context = self.collected.to_anketa_dict()

        prompt = f"""На основе уже собранной информации о бизнесе, сформулируй вопрос для получения значения поля.

СОБРАННАЯ ИНФОРМАЦИЯ:
{json.dumps(context, ensure_ascii=False, indent=2)}

ПОЛЕ ДЛЯ ЗАПОЛНЕНИЯ:
- ID: {field.field_id}
- Название: {field.display_name}
- Описание: {field.description}
- Примеры значений: {', '.join(field.examples[:3])}

Сформулируй один дружелюбный вопрос, который поможет получить нужную информацию.
Учитывай контекст - не спрашивай то, что уже известно.
Если можешь предложить варианты на основе контекста - предложи.

Верни только текст вопроса, без пояснений."""

        response = await self.deepseek.chat([
            {"role": "user", "content": prompt}
        ], temperature=0.5, max_tokens=256)

        return response.strip()

    async def _analyze_answer(self, field, answer: str) -> Dict[str, Any]:
        """Анализировать ответ через LLM."""
        return await self.deepseek.analyze_answer(
            question=field.display_name,
            answer=answer,
            question_context={
                "field_id": field.field_id,
                "description": field.description,
                "priority": field.priority.value,
                "examples": field.examples
            },
            previous_answers=self.collected.to_anketa_dict()
        )

    async def _handle_clarifications(self, field, analysis: Dict, original_answer: str):
        """Обработать уточняющие вопросы."""
        clarifications = analysis.get('clarification_questions', [])[:self.max_clarifications]
        full_answer = original_answer

        for i, clarification in enumerate(clarifications, 1):
            console.print(f"\n[yellow]🔍 Уточнение {i}/{len(clarifications)}:[/yellow]")
            console.print(Panel(clarification, border_style="yellow"))

            clar_answer = Prompt.ask("[yellow]Ваш ответ (или 'skip')[/yellow]")

            if clar_answer.lower() == 'skip':
                break

            full_answer += f"\n{clar_answer}"

            # Переанализируем
            console.print("[dim]🤖 Проверяю...[/dim]")
            new_analysis = await self._analyze_answer(field, full_answer)

            new_score = new_analysis.get('completeness_score', 0)
            bar = "█" * int(new_score * 10) + "░" * (10 - int(new_score * 10))
            console.print(f"[dim]Полнота: [{bar}] {new_score * 100:.0f}%[/dim]")

            if new_analysis.get('is_complete'):
                console.print("[green]✓ Достаточно информации![/green]")
                self.collected.update_field(field.field_id, full_answer,
                                           source="structured", confidence=new_score)
                break

    def _show_field_question(self, field, current: int, total: int):
        """Показать информацию о поле перед вопросом."""
        priority_icon = "⭐" if field.priority == FieldPriority.REQUIRED else "○"
        console.print(f"\n[dim]━━━ Поле {current}/{total} ━━━[/dim]")
        console.print(f"[cyan]{priority_icon} {field.display_name}[/cyan]")

    # ===== PHASE 3: SYNTHESIS =====

    async def _synthesis_phase(self) -> Dict[str, Any]:
        """
        Фаза Synthesis — генерация полной анкеты.

        AI резюмирует собранную информацию, заполняет пропуски,
        генерирует структурированную анкету.
        """
        self._show_phase_banner("SYNTHESIS", "green",
            "Генерирую полную анкету на основе\n"
            "собранной информации..."
        )

        # Показываем текущее резюме
        console.print("\n[bold]📋 Собранная информация:[/bold]\n")
        await self._show_summary()

        # Подтверждение
        console.print("\n[cyan]Хотите что-то скорректировать перед генерацией? (да/нет)[/cyan]")
        if Prompt.ask("", default="нет").lower() in ['да', 'yes', 'y', 'д']:
            await self._handle_corrections()

        # Генерация полной анкеты
        console.print("\n[dim]🤖 Генерирую полную анкету через AI...[/dim]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Анализ и генерация...", total=None)

            # Создаём CompletedAnketa из собранных данных
            interview_data = self._create_completed_anketa()

            # Генерируем полную анкету через LLM
            try:
                result = await export_full_anketa(interview_data)
                progress.update(task, completed=True)
            except Exception as e:
                console.print(f"[red]Ошибка генерации: {e}[/red]")
                return {"status": "error", "error": str(e)}

        # Показываем результаты
        self._show_results(result)

        return {
            "status": "completed",
            "anketa": result.get('anketa'),
            "files": {
                "json": result.get('json'),
                "markdown": result.get('markdown')
            },
            "stats": self._get_session_stats()
        }

    async def _show_summary(self):
        """Показать резюме собранной информации."""
        data = self.collected.to_anketa_dict()

        table = Table(box=box.SIMPLE)
        table.add_column("Поле", style="cyan")
        table.add_column("Значение", style="white")
        table.add_column("Статус", style="green")

        for field_id, field in self.collected.fields.items():
            if field.status != FieldStatus.EMPTY:
                value = str(field.value or field.ai_suggested_value)[:50]
                if len(str(field.value or "")) > 50:
                    value += "..."

                status_icon = {
                    FieldStatus.COMPLETE: "✓",
                    FieldStatus.PARTIAL: "◐",
                    FieldStatus.AI_SUGGESTED: "💡"
                }.get(field.status, "?")

                table.add_row(field.display_name, value, status_icon)

        console.print(table)

    async def _handle_corrections(self):
        """Обработать корректировки от пользователя."""
        console.print("\n[yellow]Какое поле хотите изменить?[/yellow]")

        # Показываем доступные поля
        filled_fields = [f for f in self.collected.fields.values()
                        if f.status != FieldStatus.EMPTY]

        for i, field in enumerate(filled_fields, 1):
            console.print(f"  {i}. {field.display_name}")

        console.print(f"  0. Готово, продолжить")

        while True:
            choice = Prompt.ask("Номер поля", default="0")

            if choice == "0":
                break

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(filled_fields):
                    field = filled_fields[idx]
                    console.print(f"\n[cyan]Текущее значение:[/cyan] {field.value}")
                    new_value = Prompt.ask("[green]Новое значение[/green]")

                    if new_value.strip():
                        self.collected.update_field(field.field_id, new_value,
                                                   source="user_correction", confidence=1.0)
                        console.print("[green]✓ Обновлено[/green]")
            except ValueError:
                pass

    def _create_completed_anketa(self) -> CompletedAnketa:
        """Создать CompletedAnketa из собранных данных."""
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

    def _show_results(self, result: Dict[str, Any]):
        """Показать финальные результаты."""
        duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()

        console.print("\n" + "=" * 50)
        console.print("[bold green]✅ ИНТЕРВЬЮ ЗАВЕРШЕНО![/bold green]")
        console.print("=" * 50)

        # Статистика
        table = Table(title="📊 Статистика", box=box.SIMPLE)
        table.add_column("Параметр", style="cyan")
        table.add_column("Значение", style="green")

        table.add_row("Длительность", f"{duration/60:.1f} мин")
        table.add_row("Сообщений в диалоге", str(len(self.dialogue_history)))
        table.add_row("Фаз пройдено", str(len(self.phase_transitions) + 1))

        stats = self.collected.get_completion_stats()
        table.add_row("Полей заполнено", f"{stats['complete']}/{stats['total']}")
        table.add_row("AI дополнил", str(stats['ai_suggested']))

        console.print(table)

        # Файлы
        console.print(f"\n[bold]📁 Сохранённые файлы:[/bold]")
        console.print(f"  JSON: [cyan]{result.get('json', 'N/A')}[/cyan]")
        console.print(f"  Markdown: [cyan]{result.get('markdown', 'N/A')}[/cyan]")

        # Что LLM добавил
        anketa = result.get('anketa')
        if anketa:
            console.print(f"\n[bold]🤖 AI сгенерировал:[/bold]")
            console.print(f"  • Услуг: {len(anketa.services)}")
            console.print(f"  • Типичных вопросов: {len(anketa.typical_questions)}")
            console.print(f"  • Примеров диалогов: {len(anketa.example_dialogues)}")
            console.print(f"  • Ограничений: {len(anketa.restrictions)}")

    def _get_session_stats(self) -> Dict[str, Any]:
        """Получить статистику сессии."""
        duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()

        return {
            "session_id": self.session_id,
            "duration_seconds": duration,
            "dialogue_turns": len(self.dialogue_history),
            "phase_transitions": len(self.phase_transitions),
            "completion_stats": self.collected.get_completion_stats()
        }

    # ===== HELPERS =====

    async def _get_ai_response(self, system_prompt: str, user_message: str) -> str:
        """Получить ответ AI."""
        # Добавляем в историю
        self.dialogue_history.append({"role": "user", "content": user_message})

        # Формируем контекст
        context = f"""
ТЕКУЩАЯ СОБРАННАЯ ИНФОРМАЦИЯ:
{json.dumps(self.collected.to_anketa_dict(), ensure_ascii=False, indent=2)}

Учитывай эту информацию в диалоге.
"""

        messages = [
            {"role": "system", "content": system_prompt + "\n\n" + context}
        ] + self.dialogue_history[-10:]  # Последние 10 сообщений

        response = await self.deepseek.chat(messages, temperature=0.7, max_tokens=1024)

        # Добавляем ответ в историю
        self.dialogue_history.append({"role": "assistant", "content": response})

        return response

    async def _extract_info_from_dialogue(self, user_message: str, ai_response: str):
        """Извлечь информацию из диалога."""
        prompt = f"""Проанализируй диалог и извлеки информацию о бизнесе клиента.

СООБЩЕНИЕ КЛИЕНТА: {user_message}

ОТВЕТ КОНСУЛЬТАНТА: {ai_response}

Верни JSON с извлечённой информацией. Только те поля, которые ЯВНО упомянуты:
{{
    "company_name": "название или null",
    "industry": "отрасль или null",
    "business_description": "описание или null",
    "agent_purpose": "назначение агента или null",
    "services": ["услуги если упомянуты"],
    "client_types": ["типы клиентов если упомянуты"],
    "current_problems": ["проблемы если упомянуты"],
    "agent_goals": ["цели если упомянуты"]
}}

Возвращай только JSON."""

        try:
            response = await self.deepseek.chat([
                {"role": "user", "content": prompt}
            ], temperature=0.1, max_tokens=512)

            # Парсим JSON
            json_text = response.strip()
            start = json_text.find('{')
            end = json_text.rfind('}')
            if start != -1 and end != -1:
                json_text = json_text[start:end+1]

            info = json.loads(json_text)

            # Обновляем поля
            for field_id in ['company_name', 'industry', 'business_description', 'agent_purpose']:
                if info.get(field_id):
                    self.collected.update_field(field_id, info[field_id],
                                               source="discovery", confidence=0.8)

            # Списковые поля
            for field_id in ['services', 'client_types', 'current_problems', 'agent_goals']:
                if info.get(field_id):
                    current = self.collected.fields[field_id].value or []
                    if isinstance(current, list):
                        current.extend(info[field_id])
                        self.collected.update_field(field_id, list(set(current)),
                                                   source="discovery", confidence=0.7)

        except Exception:
            pass  # Извлечение не критично

    def _show_phase_banner(self, phase_name: str, color: str, message: str):
        """Показать баннер фазы."""
        console.print()
        console.print(Panel(
            f"[bold {color}]═══ ФАЗА: {phase_name} ═══[/bold {color}]\n\n{message}",
            border_style=color
        ))

    def _show_ai_message(self, message: str):
        """Показать сообщение AI."""
        console.print(Panel(
            Markdown(message),
            title="[magenta]🤖 AI[/magenta]",
            border_style="magenta"
        ))

    def _show_status(self):
        """Показать текущий статус."""
        stats = self.collected.get_completion_stats()

        console.print(f"\n[bold]📊 Текущий прогресс:[/bold]")
        console.print(f"  Фаза: [cyan]{self.phase.value}[/cyan]")
        console.print(f"  Заполнено: {stats['complete']}/{stats['total']} ({stats['completion_percentage']:.0f}%)")
        console.print(f"  Обязательных: {stats['required_filled']}/{stats['required_total']}")
        console.print(f"  AI предложил: {stats['ai_suggested']}")

    def _show_mini_progress(self):
        """Показать мини-прогресс."""
        stats = self.collected.get_completion_stats()
        bar = "█" * int(stats['required_percentage'] / 10) + "░" * (10 - int(stats['required_percentage'] / 10))
        console.print(f"[dim]Прогресс: [{bar}] {stats['required_percentage']:.0f}%[/dim]")

    def _transition_phase(self, from_phase: InterviewPhase, to_phase: InterviewPhase, reason: str):
        """Выполнить переход между фазами."""
        self.phase_transitions.append(PhaseTransition(
            from_phase=from_phase,
            to_phase=to_phase,
            reason=reason,
            stats_at_transition=self.collected.get_completion_stats()
        ))
        self.phase = to_phase

        console.print(f"\n[dim]━━━ Переход: {from_phase.value} → {to_phase.value} ━━━[/dim]")


# ===== MAIN =====

async def main():
    """Main entry point."""
    console.print(Panel(
        "[bold]🎯 MAXIMUM INTERVIEW MODE[/bold]\n\n"
        "Объединённый режим интервью:\n"
        "Discovery + Structured + Synthesis",
        title="🤖 Voice Agent Interview"
    ))

    # Проверяем DeepSeek
    try:
        deepseek = DeepSeekClient()
        console.print("[green]✓ DeepSeek AI подключен[/green]\n")
    except Exception as e:
        console.print(f"[red]✗ DeepSeek недоступен: {e}[/red]")
        console.print("[yellow]Maximum режим требует DeepSeek API![/yellow]")
        return

    # Выбор паттерна
    console.print("[bold]Выберите тип агента:[/bold]")
    console.print("  1. INTERACTION - для работы с клиентами компании")
    console.print("  2. MANAGEMENT - для работы с сотрудниками")

    choice = Prompt.ask("Выбор", choices=["1", "2"], default="1")
    pattern = InterviewPattern.INTERACTION if choice == "1" else InterviewPattern.MANAGEMENT

    console.print(f"\n[green]✓ Выбран: {pattern.value}[/green]")

    # Запуск
    interviewer = MaximumInterviewer(pattern=pattern, deepseek_client=deepseek)
    result = await interviewer.run()

    if result.get('status') == 'completed':
        console.print("\n[bold green]🎉 Интервью успешно завершено![/bold green]")
    else:
        console.print(f"\n[yellow]Статус: {result.get('status')}[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
