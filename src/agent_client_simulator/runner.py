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
from src.output import OutputManager
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

    # Documents (v1.1)
    documents_loaded: List[str] = field(default_factory=list)
    document_context_summary: Optional[str] = None

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
            "dialogue_history": self.dialogue_history,
            "turn_count": self.turn_count,
            "documents_loaded": self.documents_loaded,
            "document_context_summary": self.document_context_summary,
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
        input_dir: Optional[Path] = None,
    ):
        """
        Initialize tester.

        Args:
            client: Simulated client instance
            pattern: Interview pattern to use
            max_turns_per_phase: Safety limit for turns per phase
            verbose: Show detailed output
            input_dir: Path to documents folder (for document analysis)
        """
        self.client = client
        self.pattern = pattern
        self.max_turns_per_phase = max_turns_per_phase
        self.verbose = verbose
        self.input_dir = Path(input_dir) if input_dir else None

        self.interviewer: Optional[ConsultantInterviewer] = None
        self.current_phase = ConsultantPhase.DISCOVERY
        self.turn_count = 0
        self.prompt_queue: List[str] = []

        # Document context (v1.1)
        self.document_context = None
        self.documents_loaded: List[str] = []

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

        # Load documents if input_dir is specified (v1.1)
        if self.input_dir and self.input_dir.exists():
            self._load_documents()

        if self.verbose:
            docs_info = ""
            if self.documents_loaded:
                docs_info = f"\nДокументы: [cyan]{len(self.documents_loaded)}[/cyan] файлов"

            console.print(Panel(
                f"[bold cyan]ТЕСТОВАЯ СИМУЛЯЦИЯ[/bold cyan]\n\n"
                f"Сценарий: [green]{scenario_name}[/green]\n"
                f"Клиент: {self.client.persona.name}\n"
                f"Компания: {self.client.persona.company}{docs_info}",
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
                # Use anketa from interview result (already extracted by interviewer)
                # This avoids duplicate LLM extraction
                final_anketa = result.get('anketa')
                interview_files = result.get('files', {})

                # Get company name from anketa or persona
                company_name = self.client.persona.company
                if final_anketa and final_anketa.get('company', {}).get('name'):
                    company_name = final_anketa['company']['name']

                # Save dialogue using OutputManager (new structure)
                output_manager = OutputManager()
                company_dir = output_manager.get_company_dir(company_name, start_time)

                # Save dialogue
                dialogue_path = output_manager.save_dialogue(
                    company_dir=company_dir,
                    dialogue_history=self.interviewer.dialogue_history,
                    company_name=company_name,
                    client_name=self.client.persona.name,
                    duration_seconds=duration,
                    start_time=start_time
                )

                # Copy anketa files to new structure if available
                if interview_files:
                    import shutil
                    for file_type, src_path in interview_files.items():
                        if src_path and Path(src_path).exists():
                            dest_path = company_dir / Path(src_path).name
                            shutil.copy2(src_path, dest_path)

                anketa_files = {
                    "dialogue": str(dialogue_path),
                    "company_dir": str(company_dir),
                    "original_md": interview_files.get("markdown", ""),
                    "original_json": interview_files.get("json", "")
                }

                if self.verbose:
                    console.print(f"[green]Результаты сохранены:[/green] {company_dir}")

                # Validate results
                if final_anketa:
                    from .validator import TestValidator
                    from src.anketa.schema import FinalAnketa

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

                    # Convert dict to FinalAnketa for validation
                    try:
                        anketa_obj = FinalAnketa.model_validate(final_anketa)
                        validator = TestValidator()
                        validation = validator.validate(
                            result=prelim_result,
                            scenario={"persona": self.client.persona.__dict__},
                            anketa=anketa_obj
                        )
                        validation_result = validation.to_dict()

                        if self.verbose:
                            self._show_validation(validation)

                        # Update industry knowledge base with learnings
                        self._update_knowledge_base(
                            anketa_obj,
                            validation,
                            scenario_name
                        )
                    except Exception as val_err:
                        if self.verbose:
                            console.print(f"[yellow]Валидация пропущена: {val_err}[/yellow]")

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
            documents_loaded=self.documents_loaded,
            document_context_summary=self.document_context.summary if self.document_context else None,
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
                # Special case: anketa review prompt - select "s" (save) instead of "o" (open editor)
                # This avoids editor issues in non-interactive test mode
                review_keywords = ['выберите действие', 'choose action', 'действие']
                if any(kw in clean_prompt for kw in review_keywords) and 's' in choices:
                    if self.verbose:
                        console.print("[dim]→ Review prompt, selecting: s (save without editing)[/dim]")
                    return 's'

                if self.verbose:
                    console.print(f"[dim]→ Choice prompt, selecting: {choices[0]}[/dim]")
                return choices[0]

        # REFINEMENT PHASE: Field input prompts
        # Prompts like "ваш ответ (или enter для предложения)" should accept suggested value
        refinement_keywords = [
            'ваш ответ', 'enter для предложения', 'your answer',
            'или enter', 'нажмите enter', '(или enter'
        ]
        if any(kw in clean_prompt for kw in refinement_keywords):
            if self.verbose:
                console.print("[dim]→ Refinement field prompt, accepting suggested value[/dim]")
            # Return empty string to accept the suggested/default value
            return ""

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

        if result.documents_loaded:
            console.print(f"\n[bold]Документы:[/bold] {len(result.documents_loaded)}")
            for doc in result.documents_loaded[:5]:
                console.print(f"  • {doc}")

        if result.anketa:
            console.print("\n[bold]Заполненные поля анкеты:[/bold]")
            for field, value in result.anketa.items():
                if value:
                    console.print(f"  • {field}: {str(value)[:50]}...")

        if result.errors:
            console.print("\n[red]Ошибки:[/red]")
            for error in result.errors:
                console.print(f"  • {error}")

    def _update_knowledge_base(self, anketa, validation, scenario_name: str):
        """
        Update industry knowledge base with learnings from this test.

        Records:
        - Validation score (update_metrics)
        - Any errors or warnings as learnings (record_learning)
        """
        try:
            from src.knowledge import IndustryKnowledgeManager

            manager = IndustryKnowledgeManager()
            industry_id = manager.detect_industry(anketa.industry or "")

            if not industry_id:
                if self.verbose:
                    console.print("[dim]Отрасль не определена для записи обучения[/dim]")
                return

            # Update metrics with validation score
            if validation and hasattr(validation, 'score'):
                score = validation.score / 100.0  # Convert to 0-1 range
                manager.update_metrics(industry_id, score)
                if self.verbose:
                    console.print(f"[dim]Метрики обновлены для {industry_id}: {score:.2f}[/dim]")

            # Record learnings from errors/warnings
            if validation:
                if hasattr(validation, 'errors') and validation.errors:
                    for error in validation.errors[:3]:  # Max 3 learnings
                        manager.record_learning(
                            industry_id,
                            f"Ошибка валидации: {error}",
                            f"test_{scenario_name}"
                        )

                if hasattr(validation, 'warnings') and validation.warnings:
                    for warning in validation.warnings[:2]:  # Max 2 warnings
                        manager.record_learning(
                            industry_id,
                            f"Предупреждение: {warning}",
                            f"test_{scenario_name}"
                        )

            if self.verbose:
                console.print(f"[dim]База знаний обновлена для отрасли: {industry_id}[/dim]")

        except ImportError:
            if self.verbose:
                console.print("[dim]Модуль knowledge недоступен[/dim]")
        except Exception as e:
            if self.verbose:
                console.print(f"[yellow]Не удалось обновить базу знаний: {e}[/yellow]")

    def _load_documents(self):
        """Load and analyze documents from input_dir."""
        if not self.input_dir:
            return

        try:
            from src.documents import DocumentLoader, DocumentAnalyzer

            loader = DocumentLoader()
            documents = loader.load_all(self.input_dir)

            if documents:
                self.documents_loaded = [doc.filename for doc in documents]

                if self.verbose:
                    console.print(f"[cyan]Загружено {len(documents)} документов[/cyan]")
                    for doc in documents[:3]:
                        console.print(f"  • {doc.filename} ({doc.word_count} слов)")

                # Analyze documents (sync mode - without LLM for speed)
                analyzer = DocumentAnalyzer()
                self.document_context = analyzer.analyze_sync(documents)

                if self.verbose and self.document_context.all_contacts:
                    console.print(f"[dim]Извлечённые контакты: {self.document_context.all_contacts}[/dim]")

        except Exception as e:
            if self.verbose:
                console.print(f"[yellow]Ошибка загрузки документов: {e}[/yellow]")


async def run_test_scenario(
    scenario_path: str,
    verbose: bool = True,
    input_dir: Optional[str] = None
) -> TestResult:
    """
    Convenience function to run a test from a scenario file.

    Args:
        scenario_path: Path to YAML scenario file
        verbose: Show detailed output
        input_dir: Path to documents folder (overrides scenario config)

    Returns:
        TestResult
    """
    import yaml

    # Load scenario to check for documents config
    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario = yaml.safe_load(f)

    # Determine documents directory
    docs_dir = None
    if input_dir:
        docs_dir = Path(input_dir)
    elif "documents" in scenario:
        docs_config = scenario["documents"]
        if "input_dir" in docs_config:
            docs_dir = Path(docs_config["input_dir"])

    client = SimulatedClient.from_yaml(scenario_path)
    tester = ConsultationTester(
        client=client,
        verbose=verbose,
        input_dir=docs_dir
    )

    scenario_name = Path(scenario_path).stem
    return await tester.run(scenario_name=scenario_name)
