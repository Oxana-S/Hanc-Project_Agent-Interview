"""
Consultation Tester - runs simulated consultations.

Orchestrates the interaction between ConsultantInterviewer and SimulatedClient.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from unittest.mock import patch, MagicMock

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.models import InterviewPattern
from src.consultant.interviewer import ConsultantInterviewer
from src.consultant.phases import ConsultantPhase
from src.anketa.extractor import AnketaExtractor
from src.anketa.generator import AnketaGenerator
from src.anketa.schema import FinalAnketa
from .client import SimulatedClient


console = Console()


@dataclass
class TestResult:
    """Result of a consultation test."""
    scenario_name: str
    status: str  # "completed", "failed", "interrupted"
    duration_seconds: float

    # Phase results
    phases_completed: List[str] = field(default_factory=list)
    current_phase: str = ""

    # Collected data (raw from interviewer)
    anketa: Dict[str, Any] = field(default_factory=dict)
    business_analysis: Optional[Dict[str, Any]] = None
    proposed_solution: Optional[Dict[str, Any]] = None

    # Final extracted anketa
    final_anketa: Optional[Dict[str, Any]] = None
    anketa_files: Dict[str, str] = field(default_factory=dict)

    # Validation results
    validation: Optional[Dict[str, Any]] = None

    # Dialogue
    dialogue_history: List[Dict[str, str]] = field(default_factory=list)
    turn_count: int = 0

    # Errors
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scenario_name": self.scenario_name,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "phases_completed": self.phases_completed,
            "current_phase": self.current_phase,
            "anketa": self.anketa,
            "final_anketa": self.final_anketa,
            "anketa_files": self.anketa_files,
            "validation": self.validation,
            "business_analysis": self.business_analysis,
            "proposed_solution": self.proposed_solution,
            "turn_count": self.turn_count,
            "errors": self.errors,
        }


class ConsultationTester:
    """
    Runs simulated consultations for testing.

    Uses SimulatedClient to play the role of client.
    Patches Rich Prompt.ask to inject simulated responses.
    """

    def __init__(
        self,
        client: SimulatedClient,
        pattern: InterviewPattern = InterviewPattern.INTERACTION,
        max_turns_per_phase: int = 20,
        verbose: bool = True,
    ):
        """
        Initialize tester.

        Args:
            client: Simulated client instance
            pattern: Interview pattern to use
            max_turns_per_phase: Safety limit for turns per phase
            verbose: Show detailed output
        """
        self.client = client
        self.pattern = pattern
        self.max_turns_per_phase = max_turns_per_phase
        self.verbose = verbose

        self.interviewer: Optional[ConsultantInterviewer] = None
        self.current_phase = ConsultantPhase.DISCOVERY
        self.turn_count = 0
        self.prompt_queue: List[str] = []

    async def run(self, scenario_name: str = "test") -> TestResult:
        """
        Run a full consultation test.

        Args:
            scenario_name: Name for this test run

        Returns:
            TestResult with all collected data
        """
        start_time = datetime.now()
        errors = []
        phases_completed = []

        if self.verbose:
            console.print(Panel(
                f"[bold cyan]ТЕСТОВАЯ СИМУЛЯЦИЯ[/bold cyan]\n\n"
                f"Сценарий: [green]{scenario_name}[/green]\n"
                f"Клиент: {self.client.persona.name}\n"
                f"Компания: {self.client.persona.company}",
                title="Consultation Tester",
                border_style="cyan"
            ))

        try:
            # Create interviewer
            self.interviewer = ConsultantInterviewer(
                pattern=self.pattern,
                locale="ru"
            )

            # Run with mocked input
            with patch('rich.prompt.Prompt.ask', side_effect=self._mock_prompt_ask):
                result = await self.interviewer.run()

            status = result.get('status', 'completed')
            phases_completed = ["discovery", "analysis", "proposal", "refinement"]

        except Exception as e:
            status = "failed"
            errors.append(str(e))
            if self.verbose:
                console.print(f"[red]Ошибка: {e}[/red]")

        duration = (datetime.now() - start_time).total_seconds()

        # Extract final anketa
        final_anketa = None
        anketa_files = {}
        validation_result = None

        if self.interviewer and status == "completed":
            try:
                if self.verbose:
                    console.print("\n[dim]Извлекаю структурированную анкету...[/dim]")

                # Extract anketa using LLM
                extractor = AnketaExtractor()
                final_anketa_obj = await extractor.extract(
                    dialogue_history=self.interviewer.dialogue_history,
                    business_analysis=self.interviewer.business_analysis,
                    proposed_solution=self.interviewer.proposed_solution,
                    duration_seconds=duration
                )

                # Generate files
                generator = AnketaGenerator(output_dir="output/tests")
                md_path = generator.to_markdown(final_anketa_obj)
                json_path = generator.to_json(final_anketa_obj)

                final_anketa = final_anketa_obj.model_dump()
                anketa_files = {
                    "markdown": str(md_path),
                    "json": str(json_path)
                }

                if self.verbose:
                    console.print(f"[green]Анкета сохранена:[/green] {md_path}")

                # Validate results
                from .validator import TestValidator

                # Build preliminary test result for validation
                prelim_result = TestResult(
                    scenario_name=scenario_name,
                    status=status,
                    duration_seconds=duration,
                    phases_completed=phases_completed,
                    current_phase=str(self.current_phase.value) if self.current_phase else "",
                    dialogue_history=self.interviewer.dialogue_history,
                    turn_count=self.turn_count,
                    errors=errors,
                )

                validator = TestValidator()
                validation = validator.validate(
                    result=prelim_result,
                    scenario={"persona": self.client.persona.__dict__},
                    anketa=final_anketa_obj
                )
                validation_result = validation.to_dict()

                if self.verbose:
                    self._show_validation(validation)

            except Exception as e:
                errors.append(f"Anketa extraction failed: {e}")
                if self.verbose:
                    console.print(f"[red]Ошибка извлечения анкеты: {e}[/red]")

        # Build final result
        test_result = TestResult(
            scenario_name=scenario_name,
            status=status,
            duration_seconds=duration,
            phases_completed=phases_completed,
            current_phase=str(self.current_phase.value) if self.current_phase else "",
            anketa=self.interviewer.collected.to_anketa_dict() if self.interviewer else {},
            final_anketa=final_anketa,
            anketa_files=anketa_files,
            validation=validation_result,
            business_analysis=self.interviewer.business_analysis.model_dump() if self.interviewer and self.interviewer.business_analysis else None,
            proposed_solution=self.interviewer.proposed_solution.model_dump() if self.interviewer and self.interviewer.proposed_solution else None,
            dialogue_history=self.interviewer.dialogue_history if self.interviewer else [],
            turn_count=self.turn_count,
            errors=errors,
        )

        if self.verbose:
            self._show_summary(test_result)

        return test_result

    def _show_validation(self, validation):
        """Show validation results."""
        status_icon = "[green]✓[/green]" if validation.passed else "[red]✗[/red]"
        console.print(f"\n{status_icon} Валидация: {validation.score:.0f}%")

        if validation.errors:
            console.print("[red]Ошибки:[/red]")
            for err in validation.errors:
                console.print(f"  - {err}")

        if validation.warnings:
            console.print("[yellow]Предупреждения:[/yellow]")
            for warn in validation.warnings:
                console.print(f"  - {warn}")

    def _mock_prompt_ask(self, prompt_text: str, **kwargs) -> str:
        """
        Mock for Rich Prompt.ask.

        Generates responses using SimulatedClient based on the prompt.
        """
        self.turn_count += 1

        # Detect phase from interviewer state
        if self.interviewer:
            self.current_phase = self.interviewer.phase

        # Safety check
        if self.turn_count > self.max_turns_per_phase * 4:
            if self.verbose:
                console.print("[yellow]Превышен лимит ходов, завершаю...[/yellow]")
            return "done"

        # Clean prompt text (remove Rich markup)
        import re
        clean_prompt = re.sub(r'\[.*?\]', '', prompt_text).strip().lower()

        # Debug: show what prompt we're receiving
        if self.verbose:
            console.print(f"[dim]PROMPT: '{clean_prompt}' kwargs={list(kwargs.keys())}[/dim]")

        # Selection prompts (choices) - check first
        if 'choices' in kwargs:
            choices = kwargs.get('choices', [])
            if choices:
                if self.verbose:
                    console.print(f"[dim]→ Choice prompt, selecting: {choices[0]}[/dim]")
                return choices[0]

        # Confirmation with default value - return the default
        if 'default' in kwargs and clean_prompt in ['', 'вы', 'you']:
            default_val = kwargs.get('default', 'да')
            if self.verbose:
                console.print(f"[dim]→ Confirmation with default, returning: {default_val}[/dim]")
            return default_val

        # User dialogue prompt - just a label like "Вы"
        # This is where the user should provide their full response
        dialogue_labels = ['вы', 'you']
        if clean_prompt in dialogue_labels:
            if self.verbose:
                console.print("[dim]→ Dialogue prompt, generating client response[/dim]")
            return self._generate_client_response(prompt_text)

        # Confirmation prompts - contains question words
        confirmation_keywords = [
            'да/нет', 'yes/no', 'правильно', 'подтвер', 'перейти',
            'согласен', 'готов', 'продолж', 'далее', 'верно',
            'уточнить', 'исправить', '?'
        ]
        if any(kw in clean_prompt for kw in confirmation_keywords):
            if self.verbose:
                console.print("[dim]→ Confirmation prompt, returning 'да'[/dim]")
            return self._handle_confirmation(prompt_text)

        # Default: treat as dialogue
        if self.verbose:
            console.print("[dim]→ Default: generating client response[/dim]")
        return self._generate_client_response(prompt_text)

    def _handle_confirmation(self, prompt_text: str) -> str:
        """Handle confirmation prompts."""
        # Usually confirm positively to proceed with the test
        return "да"

    def _generate_client_response(self, consultant_prompt: str) -> str:
        """Generate client response using SimulatedClient."""
        # Get the last AI message from interviewer's dialogue history
        if self.interviewer and self.interviewer.dialogue_history:
            last_messages = self.interviewer.dialogue_history[-2:]
            for msg in reversed(last_messages):
                if msg.get('role') == 'assistant':
                    consultant_message = msg.get('content', '')
                    break
            else:
                consultant_message = consultant_prompt
        else:
            consultant_message = consultant_prompt

        # Generate response synchronously (for mock compatibility)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new task in the existing loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.client.respond(consultant_message, self.current_phase.value)
                    )
                    response = future.result(timeout=30)
            else:
                response = loop.run_until_complete(
                    self.client.respond(consultant_message, self.current_phase.value)
                )
        except Exception as e:
            if self.verbose:
                console.print(f"[yellow]Ошибка генерации ответа: {e}[/yellow]")
            # Fallback response
            response = "Да, продолжайте, пожалуйста."

        if self.verbose:
            console.print(f"[dim]Клиент:[/dim] {response[:100]}...")

        return response

    def _show_summary(self, result: TestResult):
        """Show test summary."""
        console.print("\n" + "=" * 50)
        console.print("[bold]РЕЗУЛЬТАТЫ ТЕСТА[/bold]")
        console.print("=" * 50)

        status_color = "green" if result.status == "completed" else "red"
        console.print(f"Статус: [{status_color}]{result.status}[/{status_color}]")
        console.print(f"Длительность: {result.duration_seconds:.1f} сек")
        console.print(f"Ходов: {result.turn_count}")
        console.print(f"Фазы: {', '.join(result.phases_completed)}")

        if result.anketa:
            console.print("\n[bold]Заполненные поля анкеты:[/bold]")
            for field, value in result.anketa.items():
                if value:
                    console.print(f"  • {field}: {str(value)[:50]}...")

        if result.errors:
            console.print("\n[red]Ошибки:[/red]")
            for error in result.errors:
                console.print(f"  • {error}")


async def run_test_scenario(scenario_path: str, verbose: bool = True) -> TestResult:
    """
    Convenience function to run a test from a scenario file.

    Args:
        scenario_path: Path to YAML scenario file
        verbose: Show detailed output

    Returns:
        TestResult
    """
    client = SimulatedClient.from_yaml(scenario_path)
    tester = ConsultationTester(client=client, verbose=verbose)

    scenario_name = Path(scenario_path).stem
    return await tester.run(scenario_name=scenario_name)
