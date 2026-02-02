"""
Основной класс голосового агента-интервьюера
Интегрирует LiveKit, Azure OpenAI Realtime API и DeepSeek для reasoning
"""

import asyncio
import time
from typing import Optional, List, Dict, Any
from datetime import datetime
import structlog

# Модели данных
from models import (
    InterviewContext, InterviewPattern, InterviewStatus,
    QuestionResponse, QuestionStatus, AnswerAnalysis, AnalysisStatus,
    Clarification, CompletedAnketa
)

# Storage
from redis_storage import RedisStorageManager
from postgres_storage import PostgreSQLStorageManager

# Вопросы
from interview_questions_interaction import get_all_questions as get_interaction_questions
from interview_questions_management import get_all_questions as get_management_questions

logger = structlog.get_logger()


class VoiceInterviewerAgent:
    """
    Голосовой агент-интервьюер с активным анализом и уточнениями
    """
    
    def __init__(
        self,
        pattern: InterviewPattern,
        redis_manager: RedisStorageManager,
        postgres_manager: PostgreSQLStorageManager,
        azure_openai_config: Dict[str, str],
        deepseek_config: Dict[str, str],
        livekit_config: Dict[str, str],
        max_clarifications: int = 3,
        min_answer_length: int = 15
    ):
        """
        Args:
            pattern: Паттерн интервью (interaction или management)
            redis_manager: Менеджер Redis для сессий
            postgres_manager: Менеджер PostgreSQL для анкет
            azure_openai_config: Конфигурация Azure OpenAI
            deepseek_config: Конфигурация DeepSeek
            livekit_config: Конфигурация LiveKit
            max_clarifications: Максимум уточнений на вопрос
            min_answer_length: Минимальная длина ответа в словах
        """
        self.pattern = pattern
        self.redis_manager = redis_manager
        self.postgres_manager = postgres_manager
        
        # Конфигурации
        self.azure_config = azure_openai_config
        self.deepseek_config = deepseek_config
        self.livekit_config = livekit_config
        
        # Параметры анализа
        self.max_clarifications = max_clarifications
        self.min_answer_length = min_answer_length
        
        # Текущий контекст интервью
        self.context: Optional[InterviewContext] = None
        
        # Загрузка вопросов в зависимости от паттерна
        if pattern == InterviewPattern.INTERACTION:
            self.questions = get_interaction_questions()
        else:
            self.questions = get_management_questions()
        
        logger.info("agent_initialized", 
                   pattern=pattern,
                   total_questions=len(self.questions))
    
    # ===== ИНИЦИАЛИЗАЦИЯ И УПРАВЛЕНИЕ СЕССИЕЙ =====
    
    async def start_interview(self, session_id: Optional[str] = None) -> InterviewContext:
        """
        Начать новое интервью
        
        Args:
            session_id: ID сессии (если нужно восстановить)
            
        Returns:
            Контекст интервью
        """
        # Если session_id передан, пытаемся восстановить
        if session_id:
            context = await self.redis_manager.load_context(session_id)
            if context:
                self.context = context
                logger.info("interview_resumed", 
                           session_id=session_id,
                           progress=context.get_progress_percentage())
                return context
        
        # Создаём новый контекст
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
        
        # Сохраняем в Redis
        await self.redis_manager.save_context(self.context)
        
        # Сохраняем в PostgreSQL историю
        await self.postgres_manager.save_interview_session(
            session_id=self.context.session_id,
            interview_id=self.context.interview_id,
            pattern=self.pattern,
            status=InterviewStatus.IN_PROGRESS.value
        )
        
        logger.info("interview_started", 
                   session_id=self.context.session_id,
                   interview_id=self.context.interview_id,
                   pattern=self.pattern)
        
        return self.context
    
    async def pause_interview(self):
        """Приостановить интервью"""
        if self.context:
            self.context.status = InterviewStatus.PAUSED
            await self.redis_manager.update_context(self.context)
            logger.info("interview_paused", session_id=self.context.session_id)
    
    async def resume_interview(self):
        """Возобновить интервью"""
        if self.context:
            self.context.status = InterviewStatus.IN_PROGRESS
            await self.redis_manager.update_context(self.context)
            logger.info("interview_resumed", session_id=self.context.session_id)
    
    # ===== ОСНОВНОЙ ЦИКЛ ИНТЕРВЬЮ =====
    
    async def run_interview_cycle(self):
        """
        Основной цикл интервью: вопрос -> ответ -> анализ -> уточнения -> следующий вопрос
        """
        if not self.context:
            raise ValueError("Interview not started. Call start_interview() first.")
        
        # Приветствие
        await self._speak_greeting()
        
        # Цикл по вопросам
        while self.context.current_question_index < len(self.context.questions):
            current_question = self.context.get_current_question()
            
            if not current_question:
                break
            
            logger.info("asking_question", 
                       question_id=current_question.question_id,
                       section=current_question.metadata.get("section"),
                       progress=self.context.get_progress_percentage())
            
            # 1. Задаём вопрос
            await self._ask_question(current_question)
            
            # 2. Слушаем ответ
            answer = await self._listen_for_answer()
            
            if not answer:
                logger.warning("no_answer_received", 
                             question_id=current_question.question_id)
                continue
            
            # 3. Сохраняем ответ
            self.context.add_response(
                question_id=current_question.question_id,
                question_text=current_question.question_text,
                answer=answer
            )
            
            # 4. Анализируем через DeepSeek
            analysis = await self._analyze_answer(current_question, answer)
            self.context.update_analysis(current_question.question_id, analysis)
            
            # 5. Уточнения если нужно
            if analysis.status != AnalysisStatus.COMPLETE:
                await self._handle_clarifications(current_question, analysis)
            
            # 6. Помечаем как завершённый
            self.context.mark_question_complete(current_question.question_id)
            
            # 7. Сохраняем прогресс
            await self.redis_manager.update_context(self.context)
            
            # Небольшая пауза между вопросами
            await asyncio.sleep(1.0)
        
        # Завершение интервью
        await self._complete_interview()
    
    # ===== ГОЛОСОВЫЕ ВЗАИМОДЕЙСТВИЯ =====
    
    async def _speak_greeting(self):
        """Произнести приветствие"""
        greeting = f"""
        Здравствуйте! Я голосовой помощник, который поможет вам заполнить анкету для создания 
        голосового агента для вашей компании. 
        
        Я задам вам несколько вопросов о вашем бизнесе, услугах и том, какие задачи должен 
        решать агент. Весь процесс займёт примерно 25-40 минут.
        
        Отвечайте подробно, приводите конкретные примеры - это поможет создать более качественного 
        агента. Если что-то будет непонятно, я обязательно уточню.
        
        Готовы начать?
        """
        
        await self._speak(greeting)
        
        # Ждём подтверждения
        confirmation = await self._listen_for_answer()
        
        logger.info("greeting_completed", confirmed=bool(confirmation))
    
    async def _ask_question(self, question: QuestionResponse):
        """Задать вопрос клиенту"""
        # Обновляем статус
        question.status = QuestionStatus.ASKED
        question.asked_at = datetime.utcnow()
        
        # Произносим вопрос
        await self._speak(question.question_text)
    
    async def _speak(self, text: str):
        """
        Произнести текст через Azure OpenAI TTS
        
        Args:
            text: Текст для произнесения
        """
        try:
            # TODO: Интеграция с Azure OpenAI Realtime API TTS
            # В реальной реализации здесь будет вызов Azure OpenAI
            
            logger.info("speaking", text_length=len(text))
            
            # MOCK: имитация произнесения
            await asyncio.sleep(len(text) / 100)  # ~100 символов в секунду
            
        except Exception as e:
            logger.error("speak_failed", error=str(e))
    
    async def _listen_for_answer(self) -> Optional[str]:
        """
        Слушать ответ клиента через Azure OpenAI STT
        
        Returns:
            Транскрипция ответа или None
        """
        try:
            # TODO: Интеграция с Azure OpenAI Realtime API STT
            # В реальной реализации здесь будет вызов Azure OpenAI
            
            logger.info("listening_for_answer")
            
            # MOCK: имитация прослушивания
            await asyncio.sleep(3.0)
            
            # MOCK: возвращаем фиктивный ответ
            # В реальности здесь будет транскрипция
            return "Это mock ответ для тестирования"
            
        except Exception as e:
            logger.error("listen_failed", error=str(e))
            return None
    
    # ===== АНАЛИЗ ОТВЕТОВ =====
    
    async def _analyze_answer(self, question: QuestionResponse, 
                             answer: str) -> AnswerAnalysis:
        """
        Анализировать ответ через DeepSeek
        
        Args:
            question: Вопрос
            answer: Ответ
            
        Returns:
            Результат анализа
        """
        try:
            # Базовые проверки
            word_count = len(answer.split())
            min_length = question.metadata.get("min_answer_length", self.min_answer_length)
            
            # Формируем промпт для DeepSeek
            analysis_prompt = f"""
            Проанализируй ответ на вопрос анкеты.
            
            ВОПРОС:
            {question.question_text}
            
            ОТВЕТ:
            {answer}
            
            ТРЕБОВАНИЯ К ОТВЕТУ:
            - Минимальная длина: {min_length} слов
            - Тип вопроса: {question.metadata.get('type')}
            - Приоритет: {question.metadata.get('priority')}
            
            ЗАДАЧИ АНАЛИЗА:
            1. Оцени полноту ответа (completeness_score от 0 до 1)
            2. Проверь наличие конкретных примеров
            3. Проверь наличие специфичных деталей
            4. Выяви противоречия если есть
            5. Определи, чего не хватает
            6. Сгенерируй до 3-х уточняющих вопросов если нужно
            
            Верни результат в JSON формате:
            {{
                "status": "complete|incomplete|vague|needs_examples",
                "completeness_score": 0.0-1.0,
                "has_examples": true/false,
                "has_specifics": true/false,
                "contradictions": [],
                "missing_details": [],
                "clarification_questions": [],
                "confidence": 0.0-1.0,
                "reasoning": "твои рассуждения"
            }}
            """
            
            # TODO: Вызов DeepSeek API
            # В реальной реализации здесь будет вызов DeepSeek
            
            logger.info("analyzing_answer", 
                       question_id=question.question_id,
                       answer_length=word_count)
            
            # MOCK: имитация анализа
            await asyncio.sleep(2.0)
            
            # MOCK: возвращаем фиктивный анализ
            # В реальности здесь будет ответ от DeepSeek
            if word_count < min_length:
                return AnswerAnalysis(
                    status=AnalysisStatus.INCOMPLETE,
                    completeness_score=0.4,
                    word_count=word_count,
                    has_examples=False,
                    has_specifics=False,
                    missing_details=["Слишком короткий ответ", "Нет конкретных примеров"],
                    clarification_questions=[
                        "Можете привести конкретный пример?",
                        "Уточните, пожалуйста, детали"
                    ],
                    confidence=0.8,
                    reasoning="Ответ слишком краткий и не содержит примеров"
                )
            else:
                return AnswerAnalysis(
                    status=AnalysisStatus.COMPLETE,
                    completeness_score=0.9,
                    word_count=word_count,
                    has_examples=True,
                    has_specifics=True,
                    clarification_questions=[],
                    confidence=0.95,
                    reasoning="Ответ полный и содержит достаточно деталей"
                )
                
        except Exception as e:
            logger.error("analyze_answer_failed", 
                        question_id=question.question_id,
                        error=str(e))
            
            # Возвращаем базовый анализ при ошибке
            return AnswerAnalysis(
                status=AnalysisStatus.COMPLETE,
                completeness_score=0.5,
                word_count=len(answer.split()),
                has_examples=False,
                has_specifics=False,
                confidence=0.5,
                reasoning="Анализ не удался, принимаем ответ как есть"
            )
    
    # ===== УТОЧНЯЮЩИЕ ВОПРОСЫ =====
    
    async def _handle_clarifications(self, question: QuestionResponse,
                                     analysis: AnswerAnalysis):
        """
        Обработать уточняющие вопросы
        
        Args:
            question: Вопрос
            analysis: Результат анализа
        """
        if not analysis.clarification_questions:
            return
        
        # Ограничиваем количество уточнений
        max_clarifications = min(
            len(analysis.clarification_questions),
            self.max_clarifications
        )
        
        for i in range(max_clarifications):
            clarification_text = analysis.clarification_questions[i]
            
            logger.info("asking_clarification", 
                       question_id=question.question_id,
                       clarification_num=i+1,
                       total=max_clarifications)
            
            # Задаём уточняющий вопрос
            await self._speak(clarification_text)
            
            # Слушаем ответ
            clarification_answer = await self._listen_for_answer()
            
            if clarification_answer:
                # Сохраняем уточнение
                self.context.add_clarification(
                    question_id=question.question_id,
                    clarification_text=clarification_text,
                    answer=clarification_answer
                )
                
                # Небольшая пауза
                await asyncio.sleep(0.5)
    
    # ===== ЗАВЕРШЕНИЕ ИНТЕРВЬЮ =====
    
    async def _complete_interview(self):
        """Завершить интервью и сгенерировать анкету"""
        if not self.context:
            return
        
        # Обновляем статус
        self.context.status = InterviewStatus.COMPLETED
        self.context.completed_at = datetime.utcnow()
        self.context.total_duration_seconds = (
            self.context.completed_at - self.context.started_at
        ).total_seconds()
        
        # Сохраняем финальный контекст
        await self.redis_manager.update_context(self.context)
        
        # Генерируем заполненную анкету
        anketa = await self._generate_anketa()
        
        # Сохраняем в PostgreSQL
        await self.postgres_manager.save_anketa(anketa)
        
        # Обновляем историю сессии
        await self.postgres_manager.update_interview_session(
            session_id=self.context.session_id,
            completed_at=self.context.completed_at,
            duration=self.context.total_duration_seconds,
            questions_asked=self.context.total_questions,
            questions_answered=self.context.answered_questions,
            clarifications=self.context.total_clarifications_asked,
            completeness_score=self.context.completeness_score,
            status=InterviewStatus.COMPLETED.value
        )
        
        # Произносим благодарность
        await self._speak_goodbye(anketa)
        
        logger.info("interview_completed", 
                   interview_id=self.context.interview_id,
                   anketa_id=anketa.anketa_id,
                   duration_minutes=self.context.total_duration_seconds / 60)
    
    async def _generate_anketa(self) -> CompletedAnketa:
        """
        Генерировать заполненную анкету из контекста интервью
        
        Returns:
            Заполненная анкета
        """
        if not self.context:
            raise ValueError("No context available")
        
        # Извлекаем ответы
        responses = {q.question_id: q.answer for q in self.context.questions if q.answer}
        
        # Создаём анкету (базовая версия - в реальности нужен более сложный парсинг)
        anketa = CompletedAnketa(
            interview_id=self.context.interview_id,
            pattern=self.pattern,
            interview_duration_seconds=self.context.total_duration_seconds,
            
            # Базовая информация (из вопросов 1.x)
            company_name=responses.get("1.1", "Не указано"),
            industry=responses.get("1.2", "Не указано"),
            language=responses.get("1.3", "Русский"),
            agent_purpose=responses.get("1.4", "Не указано"),
            
            # Конфигурация агента
            agent_name=responses.get("2.5", "Ассистент"),
            tone=responses.get("2.6", "Адаптивный"),
            
            # Контакты
            contact_person=responses.get("4.4.1", "Не указано"),
            contact_email=responses.get("4.4.2", "email@example.com"),
            contact_phone=responses.get("4.4.3", "+00000000000"),
            company_website=responses.get("4.4.4"),
            
            # Полные ответы
            full_responses=responses,
            
            # Метрики качества
            quality_metrics={
                "completeness_score": self.context.completeness_score,
                "total_clarifications": self.context.total_clarifications_asked,
                "average_answer_length": self.context.average_answer_length
            }
        )
        
        return anketa
    
    async def _speak_goodbye(self, anketa: CompletedAnketa):
        """Произнести благодарность и резюме"""
        goodbye = f"""
        Спасибо большое! Мы завершили интервью.
        
        Я собрал всю необходимую информацию для создания голосового агента для компании 
        {anketa.company_name}.
        
        Агент будет называться {anketa.agent_name} и поможет вашему бизнесу {anketa.agent_purpose}.
        
        Сейчас я отправлю вам на email {anketa.contact_email} полную анкету с вашими ответами.
        
        Если у вас возникнут вопросы, вы всегда можете связаться с нами.
        
        Хорошего дня!
        """
        
        await self._speak(goodbye)
