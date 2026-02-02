"""
Модели данных для хранения контекста интервью
Используем Redis для текущих сессий и PostgreSQL для долгосрочного хранения
"""

from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


# ===== ENUMS =====

class InterviewPattern(str, Enum):
    """Паттерн интервью"""
    INTERACTION = "interaction"  # Для клиентов компании
    MANAGEMENT = "management"    # Для сотрудников компании


class InterviewStatus(str, Enum):
    """Статус интервью"""
    INITIATED = "initiated"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class QuestionStatus(str, Enum):
    """Статус вопроса"""
    PENDING = "pending"
    ASKED = "asked"
    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    COMPLETE = "complete"
    SKIPPED = "skipped"


class AnalysisStatus(str, Enum):
    """Статус анализа ответа"""
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    VAGUE = "vague"
    CONTRADICTORY = "contradictory"
    NEEDS_EXAMPLES = "needs_examples"


# ===== БАЗОВЫЕ МОДЕЛИ =====

class AnswerAnalysis(BaseModel):
    """Результат анализа ответа через DeepSeek"""
    status: AnalysisStatus
    completeness_score: float = Field(ge=0.0, le=1.0)
    word_count: int
    has_examples: bool
    has_specifics: bool
    contradictions: List[str] = []
    missing_details: List[str] = []
    clarification_questions: List[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Clarification(BaseModel):
    """Уточняющий вопрос и ответ"""
    clarification_id: str = Field(default_factory=lambda: str(uuid4()))
    question: str
    answer: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    analysis: Optional[AnswerAnalysis] = None


class QuestionResponse(BaseModel):
    """Ответ на вопрос"""
    question_id: str
    question_text: str
    answer: Optional[str] = None
    status: QuestionStatus = QuestionStatus.PENDING
    asked_at: Optional[datetime] = None
    answered_at: Optional[datetime] = None
    audio_duration_seconds: Optional[float] = None
    analysis: Optional[AnswerAnalysis] = None
    clarifications: List[Clarification] = []
    metadata: Dict[str, Any] = {}


# ===== КОНТЕКСТ ИНТЕРВЬЮ =====

class InterviewContext(BaseModel):
    """
    Полный контекст интервью (хранится в Redis)
    Это основная структура данных, которая постоянно обновляется
    """
    # Идентификация
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    interview_id: str = Field(default_factory=lambda: str(uuid4()))
    pattern: InterviewPattern
    
    # Временные метки
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # Статус
    status: InterviewStatus = InterviewStatus.INITIATED
    current_section: str = "Базовая информация"
    current_question_index: int = 0
    
    # Вопросы и ответы
    questions: List[QuestionResponse] = []
    total_questions: int = 0
    answered_questions: int = 0
    
    # Метрики
    total_duration_seconds: float = 0.0
    total_clarifications_asked: int = 0
    average_answer_length: float = 0.0
    completeness_score: float = 0.0
    
    # Дополнительные данные
    user_metadata: Dict[str, Any] = {}
    conversation_history: List[Dict[str, str]] = []  # {role, content, timestamp}
    
    # Технические детали
    livekit_room_name: Optional[str] = None
    client_ip: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
    
    def add_response(self, question_id: str, question_text: str, answer: str, 
                     audio_duration: Optional[float] = None) -> QuestionResponse:
        """Добавить ответ на вопрос"""
        # Находим вопрос или создаём новый
        question_response = next(
            (q for q in self.questions if q.question_id == question_id),
            None
        )
        
        if question_response is None:
            question_response = QuestionResponse(
                question_id=question_id,
                question_text=question_text
            )
            self.questions.append(question_response)
        
        # Обновляем ответ
        question_response.answer = answer
        question_response.answered_at = datetime.utcnow()
        question_response.audio_duration_seconds = audio_duration
        question_response.status = QuestionStatus.ANSWERED
        
        # Обновляем метрики
        self.answered_questions = sum(1 for q in self.questions if q.answer)
        self.updated_at = datetime.utcnow()
        
        return question_response
    
    def add_clarification(self, question_id: str, clarification_text: str, 
                         answer: Optional[str] = None) -> Clarification:
        """Добавить уточняющий вопрос"""
        question_response = next(
            (q for q in self.questions if q.question_id == question_id),
            None
        )
        
        if question_response is None:
            raise ValueError(f"Question {question_id} not found")
        
        clarification = Clarification(
            question=clarification_text,
            answer=answer
        )
        
        question_response.clarifications.append(clarification)
        self.total_clarifications_asked += 1
        self.updated_at = datetime.utcnow()
        
        return clarification
    
    def update_analysis(self, question_id: str, analysis: AnswerAnalysis):
        """Обновить анализ ответа"""
        question_response = next(
            (q for q in self.questions if q.question_id == question_id),
            None
        )
        
        if question_response is None:
            raise ValueError(f"Question {question_id} not found")
        
        question_response.analysis = analysis
        
        # Обновляем статус в зависимости от анализа
        if analysis.status == AnalysisStatus.COMPLETE:
            question_response.status = QuestionStatus.COMPLETE
        elif analysis.status in [AnalysisStatus.INCOMPLETE, AnalysisStatus.VAGUE, 
                                 AnalysisStatus.NEEDS_EXAMPLES]:
            question_response.status = QuestionStatus.NEEDS_CLARIFICATION
        
        self.updated_at = datetime.utcnow()
    
    def get_progress_percentage(self) -> float:
        """Получить процент заполнения"""
        if self.total_questions == 0:
            return 0.0
        return (self.answered_questions / self.total_questions) * 100
    
    def get_current_question(self) -> Optional[QuestionResponse]:
        """Получить текущий вопрос"""
        if 0 <= self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None
    
    def mark_question_complete(self, question_id: str):
        """Пометить вопрос как полностью обработанный"""
        question_response = next(
            (q for q in self.questions if q.question_id == question_id),
            None
        )
        
        if question_response:
            question_response.status = QuestionStatus.COMPLETE
            self.current_question_index += 1
            self.updated_at = datetime.utcnow()
    
    def all_required_fields_filled(self) -> bool:
        """Проверить, все ли обязательные поля заполнены"""
        required_questions = [q for q in self.questions 
                            if q.metadata.get("priority") == "required"]
        return all(q.status == QuestionStatus.COMPLETE for q in required_questions)


# ===== ФИНАЛЬНАЯ АНКЕТА =====

class CompletedAnketa(BaseModel):
    """
    Заполненная анкета (хранится в PostgreSQL)
    Финальный результат интервью
    """
    anketa_id: str = Field(default_factory=lambda: str(uuid4()))
    interview_id: str
    pattern: InterviewPattern
    
    # Временные метки
    created_at: datetime = Field(default_factory=datetime.utcnow)
    interview_duration_seconds: float
    
    # Базовая информация
    company_name: str
    industry: str
    language: str
    agent_purpose: str
    
    # Клиенты/Сотрудники и услуги
    business_type: Optional[str] = None
    services: List[Dict[str, Any]] = []
    client_types: List[str] = []
    typical_questions: List[str] = []
    
    # Конфигурация агента
    agent_name: str
    tone: str  # formal, friendly, adaptive
    working_hours: Dict[str, str] = {}
    transfer_conditions: List[str] = []
    
    # Интеграции
    integrations: Dict[str, Any] = {
        "email": {"enabled": False},
        "calendar": {"enabled": False},
        "call_forward": {"enabled": False},
        "sms": {"enabled": False},
        "whatsapp": {"enabled": False}
    }
    
    # Примеры диалогов
    example_dialogues: List[Dict[str, str]] = []
    
    # Ограничения и compliance
    restrictions: List[str] = []
    compliance_requirements: List[str] = []
    
    # Контакты
    contact_person: str
    contact_email: str
    contact_phone: str
    company_website: Optional[str] = None
    
    # Метаданные
    full_responses: Dict[str, Any] = {}  # Все ответы в структурированном виде
    quality_metrics: Dict[str, float] = {}
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


# ===== СТАТИСТИКА =====

class InterviewStatistics(BaseModel):
    """Статистика по интервью"""
    total_interviews: int = 0
    completed_interviews: int = 0
    average_duration_minutes: float = 0.0
    average_questions_asked: float = 0.0
    average_clarifications: float = 0.0
    average_completeness_score: float = 0.0
    completion_rate: float = 0.0
    
    pattern_breakdown: Dict[str, int] = {}
    industry_breakdown: Dict[str, int] = {}
