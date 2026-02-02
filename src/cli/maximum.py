"""
CLI интерфейс для Maximum Interview Mode.

Визуальный Rich-интерфейс с:
- Dashboard прогресса заполнения
- Индикаторами фаз
- Статусами полей
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
from rich import box
from typing import Dict, Any, Optional

from src.interview.phases import (
    InterviewPhase, FieldStatus, FieldPriority,
    CollectedInfo, ANKETA_FIELDS
)


console = Console()


class MaximumCLI:
    """CLI визуализация для Maximum Interview Mode."""

    # Цвета фаз
    PHASE_COLORS = {
        InterviewPhase.DISCOVERY: "magenta",
        InterviewPhase.STRUCTURED: "yellow",
        InterviewPhase.SYNTHESIS: "green"
    }

    # Иконки статусов
    STATUS_ICONS = {
        FieldStatus.EMPTY: "○",
        FieldStatus.PARTIAL: "◐",
        FieldStatus.COMPLETE: "✓",
        FieldStatus.AI_SUGGESTED: "💡"
    }

    @classmethod
    def show_header(cls, company_name: str = "", phase: InterviewPhase = InterviewPhase.DISCOVERY):
        """Показать заголовок с текущей фазой."""
        color = cls.PHASE_COLORS.get(phase, "cyan")

        # Фазы с индикатором текущей
        phases_text = ""
        for p in InterviewPhase:
            if p == phase:
                phases_text += f"[bold {cls.PHASE_COLORS[p]}][{p.value.upper()}][/bold {cls.PHASE_COLORS[p]}]"
            else:
                phases_text += f"[dim]{p.value}[/dim]"
            if p != InterviewPhase.SYNTHESIS:
                phases_text += " → "

        header_content = f"[bold cyan]🎯 MAXIMUM INTERVIEW MODE[/bold cyan]"
        if company_name:
            header_content += f"\n[white]{company_name}[/white]"
        header_content += f"\n\n{phases_text}"

        console.print(Panel(
            header_content,
            border_style=color,
            box=box.DOUBLE
        ))

    @classmethod
    def show_field_status_bar(cls, collected: CollectedInfo):
        """Показать панель статуса полей."""
        # Группируем поля по категориям
        categories = {
            "Базовое": ["company_name", "industry", "business_description", "language"],
            "Агент": ["agent_purpose", "agent_name", "tone", "call_direction"],
            "Клиенты": ["services", "client_types", "typical_questions"],
            "Другое": ["integrations", "restrictions", "contact_phone"]
        }

        status_parts = []
        for cat_name, field_ids in categories.items():
            cat_status = []
            for fid in field_ids:
                if fid in collected.fields:
                    field = collected.fields[fid]
                    icon = cls.STATUS_ICONS.get(field.status, "?")
                    cat_status.append(icon)

            # Сокращённое название
            short_name = cat_name[:3].lower()
            status_parts.append(f"{short_name}: {''.join(cat_status)}")

        status_line = " | ".join(status_parts)
        console.print(f"[dim]📊 {status_line}[/dim]")

    @classmethod
    def show_progress_dashboard(cls, collected: CollectedInfo, phase: InterviewPhase):
        """Показать полный dashboard прогресса."""
        stats = collected.get_completion_stats()

        # Создаём таблицу
        table = Table(title="📊 Прогресс заполнения", box=box.ROUNDED, show_header=True)
        table.add_column("Категория", style="cyan", width=20)
        table.add_column("Прогресс", width=30)
        table.add_column("Статус", width=15)

        # Группы полей
        groups = [
            ("Обязательные", FieldPriority.REQUIRED),
            ("Важные", FieldPriority.IMPORTANT),
            ("Опциональные", FieldPriority.OPTIONAL)
        ]

        for group_name, priority in groups:
            fields = [f for f in collected.fields.values() if f.priority == priority]
            filled = sum(1 for f in fields if f.status in [FieldStatus.COMPLETE, FieldStatus.AI_SUGGESTED])
            total = len(fields)

            # Прогресс-бар
            if total > 0:
                pct = filled / total
                bar = "█" * int(pct * 15) + "░" * (15 - int(pct * 15))
                progress_text = f"[{bar}] {filled}/{total}"

                # Статус
                if pct >= 1.0:
                    status = "[green]✓ Готово[/green]"
                elif pct >= 0.5:
                    status = "[yellow]◐ В процессе[/yellow]"
                else:
                    status = "[red]○ Не заполнено[/red]"
            else:
                progress_text = "N/A"
                status = "-"

            table.add_row(group_name, progress_text, status)

        # Общий прогресс
        table.add_row(
            "[bold]ИТОГО[/bold]",
            f"[bold][{'█' * int(stats['completion_percentage'] / 100 * 15)}{'░' * (15 - int(stats['completion_percentage'] / 100 * 15))}] {stats['completion_percentage']:.0f}%[/bold]",
            f"[bold]{stats['complete']}/{stats['total']}[/bold]"
        )

        console.print(table)

    @classmethod
    def show_field_details(cls, collected: CollectedInfo, show_empty: bool = False):
        """Показать детали по полям."""
        table = Table(title="📋 Детали полей", box=box.SIMPLE)
        table.add_column("Поле", style="cyan", width=25)
        table.add_column("Значение", width=35)
        table.add_column("Источник", width=12)
        table.add_column("", width=3)

        for field_id, field in collected.fields.items():
            if field.status == FieldStatus.EMPTY and not show_empty:
                continue

            # Значение (обрезаем длинные)
            value = field.value or field.ai_suggested_value or ""
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value[:3])
                if len(field.value or []) > 3:
                    value += "..."
            else:
                value = str(value)[:35]
                if len(str(field.value or "")) > 35:
                    value += "..."

            # Источник
            source = field.source or "-"
            source_color = {
                "discovery": "magenta",
                "structured": "yellow",
                "user_correction": "green",
                "ai": "blue"
            }.get(source, "dim")

            # Статус иконка
            icon = cls.STATUS_ICONS.get(field.status, "?")

            table.add_row(
                field.display_name,
                value or "[dim]—[/dim]",
                f"[{source_color}]{source}[/{source_color}]",
                icon
            )

        console.print(table)

    @classmethod
    def show_phase_transition(cls, from_phase: InterviewPhase, to_phase: InterviewPhase):
        """Показать переход между фазами."""
        from_color = cls.PHASE_COLORS.get(from_phase, "white")
        to_color = cls.PHASE_COLORS.get(to_phase, "white")

        console.print()
        console.print(Panel(
            f"[{from_color}]{from_phase.value.upper()}[/{from_color}] "
            f"[bold white]→[/bold white] "
            f"[bold {to_color}]{to_phase.value.upper()}[/bold {to_color}]",
            title="🔄 Переход фазы",
            border_style=to_color
        ))
        console.print()

    @classmethod
    def show_ai_thinking(cls, message: str = "Анализирую..."):
        """Показать индикатор работы AI."""
        console.print(f"[dim]🤖 {message}[/dim]")

    @classmethod
    def show_completeness_bar(cls, score: float, label: str = "Полнота"):
        """Показать бар полноты ответа."""
        bar_length = 20
        filled = int(score * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)

        if score >= 0.8:
            color = "green"
        elif score >= 0.5:
            color = "yellow"
        else:
            color = "red"

        console.print(f"[dim]{label}: [[{color}]{bar}[/{color}]] {score * 100:.0f}%[/dim]")

    @classmethod
    def show_clarification_prompt(cls, question: str, number: int, total: int):
        """Показать запрос на уточнение."""
        console.print(f"\n[yellow]🔍 Уточнение {number}/{total}:[/yellow]")
        console.print(Panel(question, border_style="yellow"))

    @classmethod
    def show_field_question(cls, field, current: int, total: int):
        """Показать вопрос по полю."""
        priority_icon = "⭐" if field.priority == FieldPriority.REQUIRED else "○"
        priority_color = "red" if field.priority == FieldPriority.REQUIRED else "dim"

        console.print(f"\n[dim]━━━ Вопрос {current}/{total} ━━━[/dim]")
        console.print(f"[cyan]{field.display_name}[/cyan] [{priority_color}]{priority_icon}[/{priority_color}]")

        if field.examples:
            console.print(f"[dim]💡 Примеры: {', '.join(field.examples[:2])}[/dim]")

    @classmethod
    def show_summary_table(cls, data: Dict[str, Any]):
        """Показать итоговую таблицу."""
        table = Table(title="📋 Итоговая информация", box=box.ROUNDED)
        table.add_column("Параметр", style="cyan", width=25)
        table.add_column("Значение", style="white")

        for key, value in data.items():
            if value:
                # Форматируем значение
                if isinstance(value, list):
                    display_value = "\n".join(f"• {v}" for v in value[:5])
                    if len(value) > 5:
                        display_value += f"\n... и ещё {len(value) - 5}"
                elif isinstance(value, dict):
                    display_value = str(value)[:50] + "..."
                else:
                    display_value = str(value)[:60]
                    if len(str(value)) > 60:
                        display_value += "..."

                # Отображаем название поля
                field_name = ANKETA_FIELDS.get(key, {})
                if hasattr(field_name, 'display_name'):
                    display_name = field_name.display_name
                else:
                    display_name = key.replace("_", " ").title()

                table.add_row(display_name, display_value)

        console.print(table)

    @classmethod
    def show_final_results(cls, anketa, files: Dict[str, str], stats: Dict[str, Any]):
        """Показать финальные результаты."""
        console.print()
        console.print("=" * 60)
        console.print("[bold green]✅ MAXIMUM INTERVIEW ЗАВЕРШЕНО![/bold green]")
        console.print("=" * 60)

        # Статистика
        stat_table = Table(title="📊 Статистика сессии", box=box.SIMPLE)
        stat_table.add_column("", style="cyan", width=25)
        stat_table.add_column("", style="white")

        stat_table.add_row("Длительность", f"{stats.get('duration_seconds', 0)/60:.1f} мин")
        stat_table.add_row("Ходов диалога", str(stats.get('dialogue_turns', 0)))
        stat_table.add_row("Переходов фаз", str(stats.get('phase_transitions', 0)))

        completion = stats.get('completion_stats', {})
        stat_table.add_row("Заполнено полей", f"{completion.get('complete', 0)}/{completion.get('total', 0)}")
        stat_table.add_row("AI дополнил", str(completion.get('ai_suggested', 0)))

        console.print(stat_table)

        # Файлы
        console.print("\n[bold]📁 Сохранённые файлы:[/bold]")
        if files.get('json'):
            console.print(f"  [cyan]JSON:[/cyan] {files['json']}")
        if files.get('markdown'):
            console.print(f"  [cyan]Markdown:[/cyan] {files['markdown']}")

        # Что сгенерировал AI
        if anketa:
            console.print("\n[bold]🤖 AI сгенерировал:[/bold]")
            if hasattr(anketa, 'services'):
                console.print(f"  • Услуг: {len(anketa.services)}")
            if hasattr(anketa, 'typical_questions'):
                console.print(f"  • Типичных вопросов: {len(anketa.typical_questions)}")
            if hasattr(anketa, 'example_dialogues'):
                console.print(f"  • Примеров диалогов: {len(anketa.example_dialogues)}")
            if hasattr(anketa, 'restrictions'):
                console.print(f"  • Ограничений: {len(anketa.restrictions)}")

    @classmethod
    def show_welcome_banner(cls):
        """Показать приветственный баннер."""
        banner = """
[bold cyan]
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║            🎯 MAXIMUM INTERVIEW MODE                         ║
║                                                              ║
║        Объединённый режим интервью:                          ║
║        Discovery + Structured + Synthesis                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
[/bold cyan]
"""
        console.print(banner)

    @classmethod
    def show_help(cls):
        """Показать справку по командам."""
        help_table = Table(title="📖 Доступные команды", box=box.SIMPLE)
        help_table.add_column("Команда", style="cyan", width=15)
        help_table.add_column("Описание", style="white")

        commands = [
            ("status", "Показать текущий прогресс"),
            ("done", "Завершить текущую фазу"),
            ("skip", "Пропустить текущий вопрос"),
            ("summary", "Показать собранную информацию"),
            ("help", "Показать эту справку"),
            ("quit", "Выйти из интервью")
        ]

        for cmd, desc in commands:
            help_table.add_row(cmd, desc)

        console.print(help_table)


# Удобные функции для быстрого доступа
def show_header(company_name: str = "", phase: InterviewPhase = InterviewPhase.DISCOVERY):
    MaximumCLI.show_header(company_name, phase)

def show_progress(collected: CollectedInfo, phase: InterviewPhase):
    MaximumCLI.show_progress_dashboard(collected, phase)

def show_status_bar(collected: CollectedInfo):
    MaximumCLI.show_field_status_bar(collected)

def show_phase_transition(from_phase: InterviewPhase, to_phase: InterviewPhase):
    MaximumCLI.show_phase_transition(from_phase, to_phase)

def show_completeness(score: float, label: str = "Полнота"):
    MaximumCLI.show_completeness_bar(score, label)

def show_results(anketa, files: Dict[str, str], stats: Dict[str, Any]):
    MaximumCLI.show_final_results(anketa, files, stats)
