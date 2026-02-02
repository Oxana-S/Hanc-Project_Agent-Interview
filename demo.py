"""
Демо-скрипт для тестирования Voice Interviewer Agent без реальных API
Использует MOCK данные для всех внешних сервисов
"""

import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console

from models import (
    InterviewPattern, InterviewContext, InterviewStatus,
    QuestionResponse, QuestionStatus, AnswerAnalysis, AnalysisStatus,
    CompletedAnketa
)
from redis_storage import RedisStorageManager
from postgres_storage import PostgreSQLStorageManager
from cli_interface import InterviewCLI, print_welcome_banner

console = Console()
load_dotenv()


class MockVoiceInterviewerAgent:
    """MOCK версия агента для демонстрации"""
    
    def __init__(self, pattern: InterviewPattern, redis_manager, postgres_manager):
        self.pattern = pattern
        self.redis_manager = redis_manager
        self.postgres_manager = postgres_manager
        self.context = None
        
        # Загружаем вопросы
        if pattern == InterviewPattern.INTERACTION:
            from interview_questions_interaction import get_all_questions
            self.questions = get_all_questions()[:10]  # Берём первые 10 для демо
        else:
            from interview_questions_management import get_all_questions
            self.questions = get_all_questions()[:10]
    
    async def start_interview(self, session_id=None):
        """Начать демо-интервью"""
        self.context = InterviewContext(
            pattern=self.pattern,
            status=InterviewStatus.IN_PROGRESS,
            total_questions=len(self.questions)
        )
        
        # Инициализируем вопросы
        for q in self.questions:
            question_response = QuestionResponse(
                question_id=q.id,
                question_text=q.text,
                status=QuestionStatus.PENDING,
                metadata={
                    "section": q.section,
                    "priority": q.priority.value,
                    "type": q.question_type.value,
                    "min_answer_length": q.min_answer_length
                }
            )
            self.context.questions.append(question_response)
        
        await self.redis_manager.save_context(self.context)
        await self.postgres_manager.save_interview_session(
            session_id=self.context.session_id,
            interview_id=self.context.interview_id,
            pattern=self.pattern,
            status=InterviewStatus.IN_PROGRESS.value
        )
        
        return self.context
    
    async def run_interview_cycle(self):
        """Симуляция интервью"""
        console.print("\n[yellow]🎤 Starting DEMO interview (simulated)...[/yellow]\n")
        
        mock_answers = [
            "TechSolutions Inc., компания занимается разработкой программного обеспечения",
            "IT и технологии, специализируемся на веб-разработке и мобильных приложениях",
            "Русский язык для общения с клиентами",
            "Агент должен принимать звонки от клиентов, отвечать на вопросы о наших услугах, записывать на консультации с нашими специалистами, и помогать с технической поддержкой",
            "Мы предлагаем веб-разработку - от 2 недель - от 100000 рублей, мобильные приложения - от 4 недель - от 200000 рублей, техническую консультацию - 2 часа - 5000 рублей",
            "Нет, всё стандартно, но цены могут варьироваться в зависимости от сложности проекта",
            "Фиксированные базовые цены, но итоговая стоимость определяется после консультации",
            "В основном работаем с компаниями B2B, но есть и частные клиенты",
            "Средний возраст 30-50 лет, это владельцы бизнеса и менеджеры",
            "Клиенты часто спрашивают: сколько стоит разработка сайта, какие технологии используем, есть ли портфолио, как долго займёт проект, предоставляете ли поддержку после запуска"
        ]
        
        for i, question in enumerate(self.context.questions):
            if i >= len(mock_answers):
                break
            
            # Симуляция задавания вопроса
            question.status = QuestionStatus.ASKED
            question.asked_at = datetime.utcnow()
            
            await asyncio.sleep(0.5)  # Имитация времени на вопрос
            
            # Симуляция ответа
            answer = mock_answers[i]
            self.context.add_response(
                question_id=question.question_id,
                question_text=question.question_text,
                answer=answer
            )
            
            await asyncio.sleep(0.5)  # Имитация времени на ответ
            
            # Симуляция анализа
            word_count = len(answer.split())
            completeness = 0.9 if word_count > 20 else 0.6
            
            analysis = AnswerAnalysis(
                status=AnalysisStatus.COMPLETE if completeness > 0.8 else AnalysisStatus.INCOMPLETE,
                completeness_score=completeness,
                word_count=word_count,
                has_examples=True if word_count > 20 else False,
                has_specifics=True if word_count > 15 else False,
                clarification_questions=[],
                confidence=0.9,
                reasoning="Ответ достаточно подробный" if completeness > 0.8 else "Нужно больше деталей"
            )
            
            self.context.update_analysis(question.question_id, analysis)
            self.context.mark_question_complete(question.question_id)
            
            # Обновляем прогресс
            await self.redis_manager.update_context(self.context)
            
            await asyncio.sleep(0.3)  # Небольшая пауза
        
        # Завершение
        await self._complete_interview()
    
    async def _complete_interview(self):
        """Завершить демо-интервью"""
        self.context.status = InterviewStatus.COMPLETED
        self.context.completed_at = datetime.utcnow()
        self.context.total_duration_seconds = (
            self.context.completed_at - self.context.started_at
        ).total_seconds()
        
        await self.redis_manager.update_context(self.context)
        
        # Генерируем анкету
        responses = {q.question_id: q.answer for q in self.context.questions if q.answer}
        
        anketa = CompletedAnketa(
            interview_id=self.context.interview_id,
            pattern=self.pattern,
            interview_duration_seconds=self.context.total_duration_seconds,
            company_name=responses.get("1.1", "TechSolutions Inc."),
            industry=responses.get("1.2", "IT / Технологии"),
            language=responses.get("1.3", "Русский"),
            agent_purpose=responses.get("1.4", "Поддержка клиентов"),
            agent_name="Алекс",
            tone="Адаптивный",
            contact_person="Иван Петров",
            contact_email="ivan@techsolutions.com",
            contact_phone="+79991234567",
            company_website="https://techsolutions.com",
            full_responses=responses,
            quality_metrics={
                "completeness_score": 0.87,
                "total_clarifications": 0,
                "average_answer_length": 25.4
            }
        )
        
        await self.postgres_manager.save_anketa(anketa)
        
        await self.postgres_manager.update_interview_session(
            session_id=self.context.session_id,
            completed_at=self.context.completed_at,
            duration=self.context.total_duration_seconds,
            questions_asked=self.context.total_questions,
            questions_answered=self.context.answered_questions,
            clarifications=0,
            completeness_score=0.87,
            status=InterviewStatus.COMPLETED.value
        )
        
        console.print("\n[green]✅ DEMO interview completed![/green]\n")


async def main():
    """Главная функция демо"""
    print_welcome_banner()
    
    console.print("[bold yellow]🎬 DEMO MODE[/bold yellow]")
    console.print("[yellow]This is a simulated demo without real API calls[/yellow]\n")
    
    # Выбор паттерна
    console.print("[bold]Select pattern:[/bold]")
    console.print("  [1] INTERACTION")
    console.print("  [2] MANAGEMENT\n")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        pattern = InterviewPattern.INTERACTION
        console.print("[green]✓ Selected: INTERACTION[/green]\n")
    elif choice == "2":
        pattern = InterviewPattern.MANAGEMENT
        console.print("[green]✓ Selected: MANAGEMENT[/green]\n")
    else:
        console.print("[red]Invalid choice[/red]")
        return
    
    # Инициализация storage
    console.print("[yellow]Initializing storage...[/yellow]")
    
    redis_manager = RedisStorageManager(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379"))
    )
    
    postgres_manager = PostgreSQLStorageManager(
        database_url=os.getenv(
            "DATABASE_URL",
            f"postgresql://{os.getenv('POSTGRES_USER', 'interviewer_user')}:"
            f"{os.getenv('POSTGRES_PASSWORD', 'change_me_in_production')}@"
            f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
            f"{os.getenv('POSTGRES_PORT', '5432')}/"
            f"{os.getenv('POSTGRES_DB', 'voice_interviewer')}"
        )
    )
    
    console.print("[green]✓ Storage initialized[/green]\n")
    
    # Создаём демо-агента
    agent = MockVoiceInterviewerAgent(pattern, redis_manager, postgres_manager)
    
    # Запускаем интервью
    await agent.start_interview()
    
    # CLI
    cli = InterviewCLI(agent)
    
    # Запускаем с мониторингом
    agent_task = asyncio.create_task(agent.run_interview_cycle())
    monitor_task = asyncio.create_task(cli.monitor_interview(update_interval=0.5))
    
    await asyncio.gather(agent_task, monitor_task)
    
    # Финальная сводка
    cli.show_completion_summary()
    
    console.print("\n[bold cyan]📊 Viewing results in database...[/bold cyan]\n")
    
    # Показываем сохранённую анкету
    anketa = await postgres_manager.get_anketa(
        list((await postgres_manager.get_statistics()).pattern_breakdown.keys())[0]
    )
    
    if agent.context:
        from rich.table import Table
        
        table = Table(title="📋 Completed Anketa Preview", show_header=False)
        table.add_column("Field", style="cyan", width=25)
        table.add_column("Value", style="white")
        
        table.add_row("Company Name", "TechSolutions Inc.")
        table.add_row("Industry", "IT / Технологии")
        table.add_row("Language", "Русский")
        table.add_row("Agent Name", "Алекс")
        table.add_row("Tone", "Адаптивный")
        table.add_row("Duration", f"{agent.context.total_duration_seconds:.1f}s")
        table.add_row("Questions Answered", f"{agent.context.answered_questions}/{agent.context.total_questions}")
        
        console.print(table)
    
    console.print("\n[green]✅ Demo completed successfully![/green]")
    console.print("[yellow]Check PostgreSQL database for full results[/yellow]\n")


if __name__ == "__main__":
    asyncio.run(main())
