"""
Test Reporter - generates reports from test results.

Outputs:
- Console summary
- JSON report
- Markdown report
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from .runner import TestResult


console = Console()


class TestReporter:
    """
    Generates reports from consultation test results.

    Formats:
    - Console (Rich)
    - JSON
    - Markdown
    """

    def __init__(self, output_dir: str = "output/tests"):
        """
        Initialize reporter.

        Args:
            output_dir: Directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_company_name(self, result: TestResult) -> str:
        """
        Извлечь название компании из результата для именования файлов.

        Защита от dialogue contamination - если company_name содержит
        длинный текст (ответ клиента), используем scenario_name.
        """
        company = None

        # Приоритет: final_anketa > anketa > scenario_name
        if result.final_anketa:
            company = result.final_anketa.get('company_name')

        if not company and result.anketa:
            company = result.anketa.get('company_name')

        # Защита от dialogue contamination:
        # Если company_name слишком длинный (>50 символов) или содержит
        # признаки диалога - это не название компании, а текст ответа
        if company:
            company = str(company)
            dialogue_markers = [
                'отлично', 'спасибо', 'хорошо', 'план', 'согласен',
                'понедельник', 'жду', 'рад', 'супер', 'идеально',
                '\n', '...'
            ]
            is_contaminated = (
                len(company) > 50 or
                any(marker in company.lower() for marker in dialogue_markers)
            )
            if is_contaminated:
                company = None

        if not company:
            company = result.scenario_name

        # Нормализация для имени файла
        company = self._sanitize_filename(str(company))
        return company

    def _sanitize_filename(self, name: str) -> str:
        """Очистить строку для использования в имени файла."""
        import re
        import unicodedata

        # Нормализуем Unicode
        name = unicodedata.normalize('NFKD', name)

        # Приводим к нижнему регистру
        name = name.lower()

        # Заменяем пробелы и специальные символы
        name = re.sub(r'[^\w\s-]', '', name)
        name = re.sub(r'[\s_-]+', '_', name)

        # Убираем начальные/конечные подчёркивания
        name = name.strip('_')

        # Ограничиваем длину (файловые системы обычно ограничивают ~255 символов)
        return name[:40] if name else "unnamed"

    def _format_dialogue(self, dialogue: List[Dict[str, str]], truncate: bool = True) -> None:
        """Форматированный вывод диалога в консоль."""
        console.print("\n" + "=" * 60)
        console.print("[bold cyan]ДИАЛОГ КОНСУЛЬТАЦИИ[/bold cyan]")
        console.print("=" * 60)

        for i, msg in enumerate(dialogue, 1):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')

            if role == 'assistant':
                console.print(f"\n[bold blue]🤖 Консультант (#{i}):[/bold blue]")
            else:
                console.print(f"\n[bold green]👤 Клиент (#{i}):[/bold green]")

            if truncate and len(content) > 300:
                console.print(f"  {content[:300]}...")
            else:
                console.print(f"  {content}")

        console.print("\n" + "=" * 60)

    def report_to_console(self, result: TestResult):
        """
        Print detailed report to console.

        Args:
            result: Test result to report
        """
        # Header
        console.print("\n")
        console.print(Panel(
            f"[bold cyan]ОТЧЁТ О ТЕСТИРОВАНИИ[/bold cyan]\n\n"
            f"Сценарий: [green]{result.scenario_name}[/green]\n"
            f"Дата: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
            border_style="cyan"
        ))

        # Status
        status_color = "green" if result.status == "completed" else "red"
        console.print(f"\n[bold]Статус:[/bold] [{status_color}]{result.status}[/{status_color}]")

        # Metrics table
        metrics_table = Table(title="Метрики", show_header=True)
        metrics_table.add_column("Параметр", style="cyan")
        metrics_table.add_column("Значение", style="green")

        metrics_table.add_row("Длительность", f"{result.duration_seconds:.1f} сек")
        metrics_table.add_row("Всего ходов", str(result.turn_count))
        metrics_table.add_row("Фаз пройдено", str(len(result.phases_completed)))

        console.print(metrics_table)

        # Anketa summary
        if result.anketa:
            self._print_anketa_summary(result.anketa)

        # Business Analysis
        if result.business_analysis:
            self._print_analysis_summary(result.business_analysis)

        # Proposed Solution
        if result.proposed_solution:
            self._print_solution_summary(result.proposed_solution)

        # Errors
        if result.errors:
            console.print("\n[bold red]Ошибки:[/bold red]")
            for error in result.errors:
                console.print(f"  ❌ {error}")

        # Dialogue
        if result.dialogue_history:
            self._format_dialogue(result.dialogue_history)

    def _print_anketa_summary(self, anketa: Dict[str, Any]):
        """Print anketa fields summary."""
        console.print("\n[bold]Заполненная анкета:[/bold]")

        table = Table(show_header=True)
        table.add_column("Поле", style="cyan")
        table.add_column("Значение", style="white")
        table.add_column("Статус", style="green")

        filled = 0
        total = 0

        for field, value in anketa.items():
            total += 1
            if value:
                filled += 1
                status = "✓"
                value_str = str(value)[:50] + ("..." if len(str(value)) > 50 else "")
            else:
                status = "—"
                value_str = "[dim]не заполнено[/dim]"

            table.add_row(field, value_str, status)

        console.print(table)
        console.print(f"\nЗаполнено: [green]{filled}[/green] из [cyan]{total}[/cyan] ({filled/total*100:.0f}%)")

    def _print_analysis_summary(self, analysis: Dict[str, Any]):
        """Print business analysis summary."""
        console.print("\n[bold]Анализ бизнеса:[/bold]")

        if 'pain_points' in analysis and analysis['pain_points']:
            console.print("\n[yellow]Болевые точки:[/yellow]")
            for pain in analysis['pain_points']:
                desc = pain.get('description', pain) if isinstance(pain, dict) else pain
                console.print(f"  • {desc}")

        if 'opportunities' in analysis and analysis['opportunities']:
            console.print("\n[green]Возможности:[/green]")
            for opp in analysis['opportunities']:
                desc = opp.get('description', opp) if isinstance(opp, dict) else opp
                console.print(f"  • {desc}")

    def _print_solution_summary(self, solution: Dict[str, Any]):
        """Print proposed solution summary."""
        console.print("\n[bold]Предложенное решение:[/bold]")

        if 'main_function' in solution:
            main = solution['main_function']
            name = main.get('name', 'N/A') if isinstance(main, dict) else main
            console.print(f"\n[cyan]Основная функция:[/cyan] {name}")

        if 'additional_functions' in solution:
            console.print("\n[cyan]Дополнительные функции:[/cyan]")
            for func in solution['additional_functions']:
                name = func.get('name', func) if isinstance(func, dict) else func
                console.print(f"  • {name}")

    def save_json(self, result: TestResult, filename: Optional[str] = None) -> Path:
        """
        Save result as JSON file.

        Args:
            result: Test result
            filename: Optional custom filename

        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            company = self._get_company_name(result)
            filename = f"{company}_{timestamp}.json"

        filepath = self.output_dir / filename

        def json_serializer(obj):
            """Custom JSON serializer for datetime objects."""
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2, default=json_serializer)

        console.print(f"\n[green]JSON сохранён:[/green] {filepath}")
        return filepath

    def save_markdown(self, result: TestResult, filename: Optional[str] = None) -> Path:
        """
        Save result as Markdown file.

        Args:
            result: Test result
            filename: Optional custom filename

        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            company = self._get_company_name(result)
            filename = f"{company}_{timestamp}.md"

        filepath = self.output_dir / filename

        md_content = self._generate_markdown(result)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)

        console.print(f"[green]Markdown сохранён:[/green] {filepath}")
        return filepath

    def _generate_markdown(self, result: TestResult) -> str:
        """Generate Markdown report content."""
        lines = [
            f"# Отчёт о тестировании: {result.scenario_name}",
            "",
            f"**Дата:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
            f"**Статус:** {result.status}",
            f"**Длительность:** {result.duration_seconds:.1f} сек",
            f"**Ходов:** {result.turn_count}",
            "",
            "## Заполненная анкета",
            "",
        ]

        # Anketa
        if result.anketa:
            lines.append("| Поле | Значение |")
            lines.append("|------|----------|")
            for field, value in result.anketa.items():
                value_str = str(value)[:100] if value else "—"
                lines.append(f"| {field} | {value_str} |")
        else:
            lines.append("*Анкета не заполнена*")

        # Business Analysis
        lines.extend(["", "## Анализ бизнеса", ""])
        if result.business_analysis:
            if result.business_analysis.get('pain_points'):
                lines.append("### Болевые точки")
                for pain in result.business_analysis['pain_points']:
                    desc = pain.get('description', pain) if isinstance(pain, dict) else pain
                    lines.append(f"- {desc}")

            if result.business_analysis.get('opportunities'):
                lines.append("\n### Возможности")
                for opp in result.business_analysis['opportunities']:
                    desc = opp.get('description', opp) if isinstance(opp, dict) else opp
                    lines.append(f"- {desc}")
        else:
            lines.append("*Анализ не выполнен*")

        # Proposed Solution
        lines.extend(["", "## Предложенное решение", ""])
        if result.proposed_solution:
            if result.proposed_solution.get('main_function'):
                main = result.proposed_solution['main_function']
                name = main.get('name', main) if isinstance(main, dict) else main
                desc = main.get('description', '') if isinstance(main, dict) else ''
                lines.append(f"**Основная функция:** {name}")
                if desc:
                    lines.append(f"\n{desc}")

            if result.proposed_solution.get('additional_functions'):
                lines.append("\n### Дополнительные функции")
                for func in result.proposed_solution['additional_functions']:
                    name = func.get('name', func) if isinstance(func, dict) else func
                    lines.append(f"- {name}")
        else:
            lines.append("*Решение не предложено*")

        # Errors
        if result.errors:
            lines.extend(["", "## Ошибки", ""])
            for error in result.errors:
                lines.append(f"- ❌ {error}")

        # Полный диалог
        if result.dialogue_history:
            lines.extend(["", "---", "", "## Полный диалог", ""])
            for i, msg in enumerate(result.dialogue_history, 1):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')

                if role == 'assistant':
                    lines.append(f"### 🤖 Консультант (реплика {i})")
                else:
                    lines.append(f"### 👤 Клиент (реплика {i})")

                lines.append("")
                lines.append(content)
                lines.append("")

        return "\n".join(lines)

    def full_report(self, result: TestResult, save_files: bool = True) -> Dict[str, Path]:
        """
        Generate full report: console + JSON + Markdown.

        Args:
            result: Test result
            save_files: Whether to save JSON and Markdown files

        Returns:
            Dict with paths to saved files
        """
        self.report_to_console(result)

        files = {}
        if save_files:
            files['json'] = self.save_json(result)
            files['markdown'] = self.save_markdown(result)

        return files
