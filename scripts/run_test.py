#!/usr/bin/env python3
"""
Скрипт для запуска тестовых симуляций.

Использование:
    python scripts/run_test.py vitalbox              # Запустить сценарий vitalbox
    python scripts/run_test.py tests/scenarios/x.yaml  # Запустить из файла
    python scripts/run_test.py --list                # Список сценариев
    python scripts/run_test.py vitalbox --quiet      # Без подробного вывода
    python scripts/run_test.py vitalbox --input-dir input/test_docs  # С документами
"""

import asyncio
import sys
import os
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from src.agent_client_simulator.client import SimulatedClient
from src.agent_client_simulator.runner import ConsultationTester, run_test_scenario
from src.agent_client_simulator.reporter import TestReporter

load_dotenv()
console = Console()

SCENARIOS_DIR = Path(__file__).parent.parent / "tests" / "scenarios"


def list_scenarios():
    """List available test scenarios."""
    console.print("\n[bold]Доступные сценарии:[/bold]\n")

    for yaml_file in SCENARIOS_DIR.glob("*.yaml"):
        if yaml_file.name.startswith("_"):
            continue  # Skip templates

        console.print(f"  • [cyan]{yaml_file.stem}[/cyan]")
        console.print(f"    Путь: {yaml_file}")

    console.print(f"\n[dim]Директория: {SCENARIOS_DIR}[/dim]")
    console.print("[dim]Создайте новый сценарий из шаблона _template.yaml[/dim]\n")


def find_scenario(name: str) -> Path:
    """Find scenario file by name or path."""
    # Direct path
    if os.path.exists(name):
        return Path(name)

    # By name in scenarios dir
    scenario_path = SCENARIOS_DIR / f"{name}.yaml"
    if scenario_path.exists():
        return scenario_path

    # Try without extension
    scenario_path = SCENARIOS_DIR / name
    if scenario_path.exists():
        return scenario_path

    raise FileNotFoundError(f"Сценарий не найден: {name}")


@click.command()
@click.argument('scenario', required=False)
@click.option('--list', '-l', 'list_all', is_flag=True, help='Показать список сценариев')
@click.option('--quiet', '-q', is_flag=True, help='Минимальный вывод')
@click.option('--no-save', is_flag=True, help='Не сохранять отчёты в файлы')
@click.option('--input-dir', '-i', help='Путь к папке с документами клиента')
def main(scenario: str, list_all: bool, quiet: bool, no_save: bool, input_dir: str):
    """
    Запуск тестовой симуляции консультации.

    SCENARIO: имя сценария или путь к YAML файлу
    """
    if list_all:
        list_scenarios()
        return

    if not scenario:
        console.print("[yellow]Укажите сценарий для запуска[/yellow]")
        console.print("Используйте --list для просмотра доступных сценариев")
        return

    try:
        scenario_path = find_scenario(scenario)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        console.print("Используйте --list для просмотра доступных сценариев")
        return

    docs_info = ""
    if input_dir:
        docs_info = f"\nДокументы: [cyan]{input_dir}[/cyan]"

    console.print(Panel(
        f"[bold cyan]ЗАПУСК ТЕСТОВОЙ СИМУЛЯЦИИ[/bold cyan]\n\n"
        f"Сценарий: [green]{scenario_path.stem}[/green]\n"
        f"Файл: {scenario_path}{docs_info}",
        border_style="cyan"
    ))

    # Run test
    try:
        result = asyncio.run(run_test_scenario(
            str(scenario_path),
            verbose=not quiet,
            input_dir=input_dir
        ))

        # Generate report
        reporter = TestReporter()
        reporter.full_report(result, save_files=not no_save)

        # Exit code
        if result.status == "completed":
            console.print("\n[bold green]✓ Тест завершён успешно[/bold green]")
            sys.exit(0)
        else:
            console.print(f"\n[bold red]✗ Тест завершён со статусом: {result.status}[/bold red]")
            sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]Ошибка: {e}[/red]")
        import traceback
        if not quiet:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
