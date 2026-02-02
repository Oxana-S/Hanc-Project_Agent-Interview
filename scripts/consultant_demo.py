#!/usr/bin/env python3
"""
Demo script for ConsultantInterviewer.

Запуск AI-консультанта с 4 фазами:
DISCOVERY → ANALYSIS → PROPOSAL → REFINEMENT
"""

import asyncio
import sys
import os

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from src.models import InterviewPattern
from src.consultant.interviewer import ConsultantInterviewer
from src.research.engine import ResearchEngine
from src.llm.deepseek import DeepSeekClient

load_dotenv()
console = Console()


def show_banner():
    """Показать приветственный баннер."""
    console.print(Panel(
        "[bold cyan]CONSULTANT INTERVIEWER v3.0[/bold cyan]\n\n"
        "[bold]AI-Консультант по созданию голосовых агентов[/bold]\n\n"
        "Фазы консультации:\n"
        "[magenta]1. DISCOVERY[/magenta] — свободный диалог о бизнесе\n"
        "[cyan]2. ANALYSIS[/cyan] — анализ + исследование\n"
        "[yellow]3. PROPOSAL[/yellow] — предложение решения\n"
        "[green]4. REFINEMENT[/green] — заполнение анкеты\n",
        title="Voice Interviewer Agent",
        border_style="cyan"
    ))


def check_dependencies() -> bool:
    """Проверить наличие зависимостей."""
    checks = []

    # DeepSeek
    try:
        deepseek = DeepSeekClient()
        checks.append(("DeepSeek API", True))
    except Exception as e:
        checks.append(("DeepSeek API", False))
        console.print(f"[red]✗ DeepSeek: {e}[/red]")

    # Показываем статус
    for name, ok in checks:
        if ok:
            console.print(f"[green]✓ {name} подключен[/green]")
        else:
            console.print(f"[red]✗ {name} недоступен[/red]")

    return all(ok for _, ok in checks)


async def run_consultant():
    """Запустить консультанта."""
    show_banner()

    # Проверяем зависимости
    console.print("\n[bold]Проверка подключений:[/bold]")
    if not check_dependencies():
        console.print("\n[red]Не все зависимости доступны![/red]")
        return

    console.print()

    # Выбор паттерна
    console.print("[bold]Выберите тип агента:[/bold]")
    console.print("  [cyan]1.[/cyan] INTERACTION — для работы с клиентами")
    console.print("  [cyan]2.[/cyan] MANAGEMENT — для работы с сотрудниками")

    choice = Prompt.ask("Выбор", choices=["1", "2"], default="1")
    pattern = InterviewPattern.INTERACTION if choice == "1" else InterviewPattern.MANAGEMENT

    console.print(f"\n[green]✓ Выбран: {pattern.value}[/green]")

    # Спрашиваем про Research Engine
    console.print("\n[bold]Включить исследование отрасли?[/bold]")
    console.print("  [dim]Парсинг сайтов, веб-поиск, анализ рынка[/dim]")

    use_research = Prompt.ask("Включить? (да/нет)", default="да")
    research_engine = None

    if use_research.lower() in ['да', 'yes', 'y', 'д']:
        try:
            research_engine = ResearchEngine()
            console.print("[green]✓ Research Engine включен[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ Research Engine недоступен: {e}[/yellow]")

    # Создаём консультанта
    consultant = ConsultantInterviewer(
        pattern=pattern,
        research_engine=research_engine,
        locale="ru"
    )

    console.print("\n" + "=" * 50)
    console.print("[bold]Начинаем консультацию...[/bold]")
    console.print("=" * 50 + "\n")

    # Запускаем
    result = await consultant.run()

    # Показываем итоги
    if result.get('status') == 'completed':
        console.print("\n[bold green]Консультация успешно завершена![/bold green]")
    else:
        console.print(f"\n[yellow]Статус: {result.get('status')}[/yellow]")

    return result


def main():
    """Entry point."""
    try:
        result = asyncio.run(run_consultant())
    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Ошибка: {e}[/red]")
        raise


if __name__ == "__main__":
    main()
