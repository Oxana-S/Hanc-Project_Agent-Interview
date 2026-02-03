#!/usr/bin/env python3
"""
Интегрированный pipeline: Test Agent → Document Reviewer.

Запускает автоматическое тестирование консультации,
затем предлагает проверить и отредактировать результат.

Использование:
    python scripts/run_pipeline.py vitalbox
    python scripts/run_pipeline.py vitalbox --auto-approve
    python scripts/run_pipeline.py vitalbox --skip-review
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Optional

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.agent_client_simulator.client import SimulatedClient
from src.agent_client_simulator.runner import ConsultationTester
from src.agent_client_simulator.reporter import TestReporter
from src.anketa.schema import FinalAnketa
from src.anketa.generator import AnketaGenerator
from src.anketa.review_service import AnketaReviewService

load_dotenv()
console = Console()

SCENARIOS_DIR = Path(__file__).parent.parent / "tests" / "scenarios"


def find_scenario(name: str) -> Path:
    """Find scenario file by name or path."""
    if os.path.exists(name):
        return Path(name)

    scenario_path = SCENARIOS_DIR / f"{name}.yaml"
    if scenario_path.exists():
        return scenario_path

    scenario_path = SCENARIOS_DIR / name
    if scenario_path.exists():
        return scenario_path

    raise FileNotFoundError(f"Сценарий не найден: {name}")


async def run_test_stage(scenario_path: Path, verbose: bool = True) -> dict:
    """
    Stage 1: Автоматическое тестирование.

    Returns:
        dict с результатами теста и FinalAnketa
    """
    console.print(Panel(
        "[bold cyan]STAGE 1: АВТОМАТИЧЕСКОЕ ТЕСТИРОВАНИЕ[/bold cyan]\n\n"
        f"Сценарий: [green]{scenario_path.stem}[/green]",
        border_style="cyan"
    ))

    client = SimulatedClient.from_yaml(str(scenario_path))
    tester = ConsultationTester(client=client, verbose=verbose)

    test_result = await tester.run(scenario_name=scenario_path.stem)

    # Генерируем отчёт
    reporter = TestReporter()
    reporter.report_to_console(test_result)

    return {
        "test_result": test_result,
        "passed": test_result.validation.get("passed", False) if test_result.validation else False,
        "anketa": test_result.final_anketa
    }


def run_review_stage(anketa_dict: dict, verbose: bool = True) -> Optional[FinalAnketa]:
    """
    Stage 2: Ревью анкеты в редакторе.

    Returns:
        Reviewed FinalAnketa or None if cancelled
    """
    console.print("\n")
    console.print(Panel(
        "[bold cyan]STAGE 2: РЕВЬЮ АНКЕТЫ[/bold cyan]\n\n"
        "Откроется редактор для проверки и корректировки",
        border_style="cyan"
    ))

    anketa = FinalAnketa(**anketa_dict)

    review_service = AnketaReviewService()
    reviewed_anketa = review_service.finalize(anketa)

    return reviewed_anketa


def save_final_anketa(anketa: FinalAnketa, output_dir: str = "output/final") -> dict:
    """Save final reviewed anketa."""
    generator = AnketaGenerator(output_dir=output_dir)

    md_path = generator.to_markdown(anketa)
    json_path = generator.to_json(anketa)

    return {
        "markdown": str(md_path),
        "json": str(json_path)
    }


@click.command()
@click.argument('scenario')
@click.option('--auto-approve', '-a', is_flag=True,
              help='Автоматически принять без ревью')
@click.option('--skip-review', '-s', is_flag=True,
              help='Пропустить этап ревью')
@click.option('--quiet', '-q', is_flag=True,
              help='Минимальный вывод')
@click.option('--output-dir', '-o', default='output/final',
              help='Директория для финальных файлов')
def main(scenario: str, auto_approve: bool, skip_review: bool,
         quiet: bool, output_dir: str):
    """
    Запуск интегрированного pipeline: Test → Review.

    SCENARIO: имя сценария или путь к YAML файлу
    """
    try:
        scenario_path = find_scenario(scenario)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    console.print(Panel(
        "[bold magenta]ИНТЕГРИРОВАННЫЙ PIPELINE[/bold magenta]\n\n"
        f"Сценарий: [green]{scenario_path.stem}[/green]\n"
        f"Режим: {'Автоматический' if auto_approve else 'С ревью'}",
        border_style="magenta"
    ))

    # ═══════════════════════════════════════════════════════════
    # STAGE 1: Автоматическое тестирование
    # ═══════════════════════════════════════════════════════════

    try:
        stage1_result = asyncio.run(run_test_stage(scenario_path, verbose=not quiet))
    except Exception as e:
        console.print(f"\n[red]Ошибка тестирования: {e}[/red]")
        if not quiet:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    # Проверяем результаты теста
    if not stage1_result["passed"]:
        console.print("\n[yellow]⚠️ Тест не прошёл валидацию[/yellow]")
        if stage1_result["test_result"].validation:
            errors = stage1_result["test_result"].validation.get("errors", [])
            for err in errors:
                console.print(f"  [red]• {err}[/red]")

        if not click.confirm("\nПродолжить с ревью несмотря на ошибки?", default=False):
            console.print("[yellow]Pipeline прерван[/yellow]")
            sys.exit(1)

    if not stage1_result["anketa"]:
        console.print("\n[red]Анкета не была сгенерирована[/red]")
        sys.exit(1)

    console.print("\n[green]✓ Stage 1 завершён[/green]")

    # ═══════════════════════════════════════════════════════════
    # STAGE 2: Ревью анкеты
    # ═══════════════════════════════════════════════════════════

    final_anketa = None

    if auto_approve or skip_review:
        console.print("\n[dim]Ревью пропущено (--auto-approve / --skip-review)[/dim]")
        final_anketa = FinalAnketa(**stage1_result["anketa"])
    else:
        try:
            final_anketa = run_review_stage(stage1_result["anketa"], verbose=not quiet)
        except KeyboardInterrupt:
            console.print("\n[yellow]Ревью прервано[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Ошибка ревью: {e}[/red]")
            if not quiet:
                import traceback
                traceback.print_exc()

    # ═══════════════════════════════════════════════════════════
    # Сохранение результата
    # ═══════════════════════════════════════════════════════════

    if final_anketa:
        console.print("\n[green]✓ Stage 2 завершён[/green]")

        files = save_final_anketa(final_anketa, output_dir)

        console.print(Panel(
            "[bold green]PIPELINE ЗАВЕРШЁН УСПЕШНО[/bold green]\n\n"
            f"Markdown: [cyan]{files['markdown']}[/cyan]\n"
            f"JSON: [cyan]{files['json']}[/cyan]",
            border_style="green"
        ))
        sys.exit(0)
    else:
        console.print(Panel(
            "[bold yellow]PIPELINE ЗАВЕРШЁН БЕЗ СОХРАНЕНИЯ[/bold yellow]\n\n"
            "Анкета не была сохранена (ревью отменено или пропущено)",
            border_style="yellow"
        ))
        sys.exit(0)


if __name__ == "__main__":
    main()
