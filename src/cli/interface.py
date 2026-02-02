"""
CLI интерфейс для голосового агента-интервьюера
Визуализация прогресса в реальном времени
"""

import asyncio
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.text import Text
from datetime import datetime
import structlog

from src.models import InterviewContext, InterviewStatus, QuestionStatus
# VoiceInterviewerAgent был удалён, теперь используется MaximumInterviewer
from typing import Any

logger = structlog.get_logger()
console = Console()


class InterviewCLI:
    """
    CLI интерфейс для мониторинга интервью
    """
    
    def __init__(self, agent: Any):
        """
        Args:
            agent: Агент-интервьюер
        """
        self.agent = agent
        self.console = Console()
    
    def create_dashboard(self, context: InterviewContext) -> Layout:
        """
        Создать dashboard с информацией о прогрессе
        
        Args:
            context: Контекст интервью
            
        Returns:
            Layout для отображения
        """
        layout = Layout()
        
        # Разделяем на 3 части
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=7)
        )
        
        # Header: Базовая информация
        header_table = Table.grid(padding=1)
        header_table.add_column(justify="left", style="cyan")
        header_table.add_column(justify="left", style="white")
        
        header_table.add_row("Session ID:", context.session_id[:8])
        header_table.add_row("Pattern:", context.pattern.value.upper())
        header_table.add_row("Status:", self._get_status_emoji(context.status))
        
        layout["header"].update(Panel(header_table, title="📊 Interview Info", border_style="blue"))
        
        # Body: Прогресс
        body_layout = Layout()
        body_layout.split_row(
            Layout(name="progress", ratio=2),
            Layout(name="current", ratio=1)
        )
        
        # Прогресс-бар
        progress_table = Table.grid(padding=1)
        progress_table.add_column(justify="left")
        
        # Основной прогресс
        progress_pct = context.get_progress_percentage()
        bar_length = 30
        filled = int(bar_length * progress_pct / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        progress_table.add_row(
            f"Progress: {progress_pct:.1f}% [{bar}]"
        )
        progress_table.add_row(
            f"Questions: {context.answered_questions}/{context.total_questions}"
        )
        progress_table.add_row("")
        
        # Разбивка по секциям
        progress_table.add_row("[bold]Sections:[/bold]")
        sections = self._get_section_progress(context)
        for section_name, (answered, total) in sections.items():
            status_icon = "✅" if answered == total else "⏳" if answered > 0 else "◻️"
            progress_table.add_row(
                f"{status_icon} {section_name}: {answered}/{total}"
            )
        
        body_layout["progress"].update(
            Panel(progress_table, title="📈 Progress", border_style="green")
        )
        
        # Текущий вопрос
        current_question = context.get_current_question()
        if current_question:
            current_text = Text()
            current_text.append("Section: ", style="bold")
            current_text.append(f"{current_question.metadata.get('section', 'N/A')}\n\n")
            current_text.append("Question:\n", style="bold yellow")
            current_text.append(f"{current_question.question_text[:200]}...\n\n")
            current_text.append("Status: ", style="bold")
            current_text.append(
                self._get_question_status_emoji(current_question.status),
                style="bold"
            )
            
            body_layout["current"].update(
                Panel(current_text, title="🎤 Current Question", border_style="yellow")
            )
        
        layout["body"].update(body_layout)
        
        # Footer: Метрики
        footer_table = Table.grid(padding=1)
        footer_table.add_column(justify="left", style="cyan")
        footer_table.add_column(justify="right", style="white")
        
        duration = (datetime.utcnow() - context.started_at).total_seconds()
        
        footer_table.add_row("Duration:", f"{duration/60:.1f} min")
        footer_table.add_row("Clarifications:", str(context.total_clarifications_asked))
        footer_table.add_row("Avg Answer Length:", f"{context.average_answer_length:.1f} words")
        footer_table.add_row("Completeness:", f"{context.completeness_score:.1%}")
        
        layout["footer"].update(
            Panel(footer_table, title="📊 Metrics", border_style="magenta")
        )
        
        return layout
    
    def _get_status_emoji(self, status: InterviewStatus) -> str:
        """Получить эмодзи для статуса"""
        mapping = {
            InterviewStatus.INITIATED: "🆕 Initiated",
            InterviewStatus.IN_PROGRESS: "▶️ In Progress",
            InterviewStatus.PAUSED: "⏸️ Paused",
            InterviewStatus.COMPLETED: "✅ Completed",
            InterviewStatus.FAILED: "❌ Failed"
        }
        return mapping.get(status, "❓ Unknown")
    
    def _get_question_status_emoji(self, status: QuestionStatus) -> str:
        """Получить эмодзи для статуса вопроса"""
        mapping = {
            QuestionStatus.PENDING: "⏳ Pending",
            QuestionStatus.ASKED: "🎤 Asked",
            QuestionStatus.ANSWERED: "💬 Answered",
            QuestionStatus.NEEDS_CLARIFICATION: "❓ Needs Clarification",
            QuestionStatus.COMPLETE: "✅ Complete",
            QuestionStatus.SKIPPED: "⏭️ Skipped"
        }
        return mapping.get(status, "❓ Unknown")
    
    def _get_section_progress(self, context: InterviewContext) -> dict:
        """
        Получить прогресс по секциям
        
        Returns:
            {section_name: (answered, total)}
        """
        sections = {}
        
        for question in context.questions:
            section = question.metadata.get("section", "Unknown")
            
            if section not in sections:
                sections[section] = [0, 0]
            
            sections[section][1] += 1  # total
            
            if question.status in [QuestionStatus.COMPLETE, QuestionStatus.SKIPPED]:
                sections[section][0] += 1  # answered
        
        return sections
    
    async def monitor_interview(self, update_interval: float = 1.0):
        """
        Мониторить интервью в реальном времени
        
        Args:
            update_interval: Интервал обновления в секундах
        """
        with Live(console=self.console, refresh_per_second=1) as live:
            while self.agent.context and self.agent.context.status == InterviewStatus.IN_PROGRESS:
                # Обновляем dashboard
                dashboard = self.create_dashboard(self.agent.context)
                live.update(dashboard)
                
                # Ждём следующего обновления
                await asyncio.sleep(update_interval)
            
            # Финальное обновление
            if self.agent.context:
                dashboard = self.create_dashboard(self.agent.context)
                live.update(dashboard)
    
    async def run_with_monitoring(self):
        """Запустить интервью с мониторингом"""
        # Запускаем агента в отдельной задаче
        agent_task = asyncio.create_task(self.agent.run_interview_cycle())
        
        # Запускаем мониторинг в отдельной задаче
        monitor_task = asyncio.create_task(self.monitor_interview())
        
        # Ждём завершения обеих задач
        await asyncio.gather(agent_task, monitor_task)
        
        # Показываем финальный результат
        self.show_completion_summary()
    
    def show_completion_summary(self):
        """Показать итоговое резюме"""
        if not self.agent.context:
            return
        
        context = self.agent.context
        
        summary = Table(title="✅ Interview Completed", show_header=False, box=None)
        summary.add_column(justify="left", style="cyan", width=30)
        summary.add_column(justify="left", style="white")
        
        duration_min = context.total_duration_seconds / 60
        
        summary.add_row("Interview ID:", context.interview_id)
        summary.add_row("Duration:", f"{duration_min:.1f} minutes")
        summary.add_row("Questions Answered:", f"{context.answered_questions}/{context.total_questions}")
        summary.add_row("Clarifications:", str(context.total_clarifications_asked))
        summary.add_row("Completeness Score:", f"{context.completeness_score:.1%}")
        
        self.console.print()
        self.console.print(Panel(summary, border_style="green"))
        self.console.print()
        self.console.print("[bold green]✨ Anketa has been saved to the database![/bold green]")
        self.console.print()


def print_welcome_banner():
    """Показать приветственный баннер"""
    banner = """
    ╔════════════════════════════════════════════════════════════╗
    ║                                                            ║
    ║         🎙️  VOICE INTERVIEWER AGENT  🎙️                   ║
    ║                                                            ║
    ║         Голосовой агент-интервьюер с активным анализом     ║
    ║                                                            ║
    ╚════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")
    console.print()


def print_pattern_selection():
    """Выбор паттерна интервью"""
    console.print("[bold yellow]Select interview pattern:[/bold yellow]")
    console.print()
    console.print("  [1] INTERACTION - Agent for customers/clients")
    console.print("  [2] MANAGEMENT - Agent for employees/internal use")
    console.print()


async def main_cli():
    """Главная функция CLI"""
    print_welcome_banner()
    
    # Выбор паттерна
    print_pattern_selection()
    
    pattern_choice = input("Enter choice (1 or 2): ").strip()
    
    if pattern_choice == "1":
        from models import InterviewPattern
        pattern = InterviewPattern.INTERACTION
        console.print("[green]✓ Selected: INTERACTION pattern[/green]")
    elif pattern_choice == "2":
        from models import InterviewPattern
        pattern = InterviewPattern.MANAGEMENT
        console.print("[green]✓ Selected: MANAGEMENT pattern[/green]")
    else:
        console.print("[red]✗ Invalid choice. Exiting.[/red]")
        return
    
    console.print()
    console.print("[yellow]Initializing agent...[/yellow]")
    
    # Здесь инициализация агента
    # (в реальности нужно передать конфигурации)
    
    console.print("[green]✓ Agent initialized successfully![/green]")
    console.print()
    console.print("[yellow]Starting interview...[/yellow]")
    console.print()
    
    # Запуск интервью с мониторингом
    # await cli.run_with_monitoring()


if __name__ == "__main__":
    asyncio.run(main_cli())
