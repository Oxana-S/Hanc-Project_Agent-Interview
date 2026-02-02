"""
PostgreSQL Storage Manager для долгосрочного хранения заполненных анкет
"""

from sqlalchemy import create_engine, Column, String, DateTime, JSON, Float, Integer, Text, Enum as SQLEnum, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from typing import Optional, List
import structlog

from models import CompletedAnketa, InterviewPattern, InterviewStatistics

logger = structlog.get_logger()

Base = declarative_base()


# ===== МОДЕЛИ БД =====

class AnketaDB(Base):
    """Модель анкеты в БД"""
    __tablename__ = "anketas"
    
    anketa_id = Column(String, primary_key=True)
    interview_id = Column(String, unique=True, nullable=False, index=True)
    pattern = Column(SQLEnum(InterviewPattern), nullable=False, index=True)
    
    # Временные метки
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    interview_duration_seconds = Column(Float, nullable=False)
    
    # Базовая информация
    company_name = Column(String, nullable=False, index=True)
    industry = Column(String, nullable=False, index=True)
    language = Column(String, nullable=False)
    agent_purpose = Column(Text, nullable=False)
    
    # Конфигурация агента
    agent_name = Column(String, nullable=False)
    tone = Column(String, nullable=False)
    
    # JSON поля для сложных данных
    services = Column(JSON, nullable=True)
    client_types = Column(JSON, nullable=True)
    typical_questions = Column(JSON, nullable=True)
    working_hours = Column(JSON, nullable=True)
    transfer_conditions = Column(JSON, nullable=True)
    integrations = Column(JSON, nullable=True)
    example_dialogues = Column(JSON, nullable=True)
    restrictions = Column(JSON, nullable=True)
    compliance_requirements = Column(JSON, nullable=True)
    
    # Контакты
    contact_person = Column(String, nullable=False)
    contact_email = Column(String, nullable=False)
    contact_phone = Column(String, nullable=False)
    company_website = Column(String, nullable=True)
    
    # Метаданные
    full_responses = Column(JSON, nullable=True)
    quality_metrics = Column(JSON, nullable=True)


class InterviewSessionDB(Base):
    """История всех интервью (включая незавершённые)"""
    __tablename__ = "interview_sessions"
    
    session_id = Column(String, primary_key=True)
    interview_id = Column(String, unique=True, nullable=False, index=True)
    pattern = Column(SQLEnum(InterviewPattern), nullable=False, index=True)
    
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True, index=True)
    status = Column(String, nullable=False, index=True)
    
    duration_seconds = Column(Float, nullable=True)
    questions_asked = Column(Integer, nullable=True)
    questions_answered = Column(Integer, nullable=True)
    clarifications_total = Column(Integer, nullable=True)
    completeness_score = Column(Float, nullable=True)
    
    # Метаданные сессии (переименовано из metadata т.к. это зарезервированное имя в SQLAlchemy)
    session_metadata = Column(JSON, nullable=True)


# ===== STORAGE MANAGER =====

class PostgreSQLStorageManager:
    """
    Управление хранилищем PostgreSQL для заполненных анкет
    """
    
    def __init__(self, database_url: str):
        """
        Args:
            database_url: URL подключения к PostgreSQL
                         Формат: postgresql://user:password@host:port/database
        """
        self.database_url = database_url
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Создаём таблицы если их нет
        Base.metadata.create_all(self.engine)
        
        logger.info("postgresql_connected", database_url=database_url)
    
    def _get_session(self) -> Session:
        """Получить сессию БД"""
        return self.SessionLocal()
    
    async def save_anketa(self, anketa: CompletedAnketa) -> bool:
        """
        Сохранить заполненную анкету в БД
        
        Args:
            anketa: Заполненная анкета
            
        Returns:
            True если успешно сохранено
        """
        session = self._get_session()
        try:
            anketa_db = AnketaDB(
                anketa_id=anketa.anketa_id,
                interview_id=anketa.interview_id,
                pattern=anketa.pattern,
                created_at=anketa.created_at,
                interview_duration_seconds=anketa.interview_duration_seconds,
                company_name=anketa.company_name,
                industry=anketa.industry,
                language=anketa.language,
                agent_purpose=anketa.agent_purpose,
                agent_name=anketa.agent_name,
                tone=anketa.tone,
                services=anketa.services,
                client_types=anketa.client_types,
                typical_questions=anketa.typical_questions,
                working_hours=anketa.working_hours,
                transfer_conditions=anketa.transfer_conditions,
                integrations=anketa.integrations,
                example_dialogues=anketa.example_dialogues,
                restrictions=anketa.restrictions,
                compliance_requirements=anketa.compliance_requirements,
                contact_person=anketa.contact_person,
                contact_email=anketa.contact_email,
                contact_phone=anketa.contact_phone,
                company_website=anketa.company_website,
                full_responses=anketa.full_responses,
                quality_metrics=anketa.quality_metrics
            )
            
            session.add(anketa_db)
            session.commit()
            
            logger.info("anketa_saved", 
                       anketa_id=anketa.anketa_id,
                       company=anketa.company_name,
                       pattern=anketa.pattern)
            
            return True
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error("anketa_save_failed", 
                        anketa_id=anketa.anketa_id,
                        error=str(e))
            return False
        finally:
            session.close()
    
    async def get_anketa(self, anketa_id: str) -> Optional[CompletedAnketa]:
        """
        Получить анкету по ID
        
        Args:
            anketa_id: ID анкеты
            
        Returns:
            Анкета или None
        """
        session = self._get_session()
        try:
            anketa_db = session.query(AnketaDB).filter(
                AnketaDB.anketa_id == anketa_id
            ).first()
            
            if anketa_db is None:
                logger.warning("anketa_not_found", anketa_id=anketa_id)
                return None
            
            # Конвертируем в Pydantic модель
            anketa = CompletedAnketa(
                anketa_id=anketa_db.anketa_id,
                interview_id=anketa_db.interview_id,
                pattern=anketa_db.pattern,
                created_at=anketa_db.created_at,
                interview_duration_seconds=anketa_db.interview_duration_seconds,
                company_name=anketa_db.company_name,
                industry=anketa_db.industry,
                language=anketa_db.language,
                agent_purpose=anketa_db.agent_purpose,
                agent_name=anketa_db.agent_name,
                tone=anketa_db.tone,
                services=anketa_db.services or [],
                client_types=anketa_db.client_types or [],
                typical_questions=anketa_db.typical_questions or [],
                working_hours=anketa_db.working_hours or {},
                transfer_conditions=anketa_db.transfer_conditions or [],
                integrations=anketa_db.integrations or {},
                example_dialogues=anketa_db.example_dialogues or [],
                restrictions=anketa_db.restrictions or [],
                compliance_requirements=anketa_db.compliance_requirements or [],
                contact_person=anketa_db.contact_person,
                contact_email=anketa_db.contact_email,
                contact_phone=anketa_db.contact_phone,
                company_website=anketa_db.company_website,
                full_responses=anketa_db.full_responses or {},
                quality_metrics=anketa_db.quality_metrics or {}
            )
            
            return anketa
            
        except SQLAlchemyError as e:
            logger.error("get_anketa_failed", 
                        anketa_id=anketa_id,
                        error=str(e))
            return None
        finally:
            session.close()
    
    async def get_anketas_by_company(self, company_name: str) -> List[CompletedAnketa]:
        """
        Получить все анкеты компании
        
        Args:
            company_name: Название компании
            
        Returns:
            Список анкет
        """
        session = self._get_session()
        try:
            anketas_db = session.query(AnketaDB).filter(
                AnketaDB.company_name.ilike(f"%{company_name}%")
            ).all()
            
            anketas = []
            for anketa_db in anketas_db:
                anketa = await self.get_anketa(anketa_db.anketa_id)
                if anketa:
                    anketas.append(anketa)
            
            logger.info("anketas_fetched_by_company", 
                       company=company_name,
                       count=len(anketas))
            
            return anketas
            
        except SQLAlchemyError as e:
            logger.error("get_anketas_by_company_failed", 
                        company=company_name,
                        error=str(e))
            return []
        finally:
            session.close()
    
    async def save_interview_session(self, session_id: str, interview_id: str,
                                     pattern: InterviewPattern, status: str,
                                     metadata: Optional[dict] = None) -> bool:
        """
        Сохранить информацию о сессии интервью
        
        Args:
            session_id: ID сессии
            interview_id: ID интервью
            pattern: Паттерн интервью
            status: Статус
            metadata: Дополнительные метаданные
            
        Returns:
            True если успешно
        """
        db_session = self._get_session()
        try:
            session_db = InterviewSessionDB(
                session_id=session_id,
                interview_id=interview_id,
                pattern=pattern,
                status=status,
                session_metadata=metadata or {}
            )
            
            db_session.add(session_db)
            db_session.commit()
            
            logger.info("interview_session_saved", 
                       session_id=session_id,
                       interview_id=interview_id)
            
            return True
            
        except SQLAlchemyError as e:
            db_session.rollback()
            logger.error("save_interview_session_failed", 
                        session_id=session_id,
                        error=str(e))
            return False
        finally:
            db_session.close()
    
    async def update_interview_session(self, session_id: str, 
                                       completed_at: Optional[datetime] = None,
                                       duration: Optional[float] = None,
                                       questions_asked: Optional[int] = None,
                                       questions_answered: Optional[int] = None,
                                       clarifications: Optional[int] = None,
                                       completeness_score: Optional[float] = None,
                                       status: Optional[str] = None) -> bool:
        """Обновить информацию о сессии"""
        db_session = self._get_session()
        try:
            session_db = db_session.query(InterviewSessionDB).filter(
                InterviewSessionDB.session_id == session_id
            ).first()
            
            if session_db is None:
                logger.warning("session_not_found_for_update", session_id=session_id)
                return False
            
            if completed_at:
                session_db.completed_at = completed_at
            if duration is not None:
                session_db.duration_seconds = duration
            if questions_asked is not None:
                session_db.questions_asked = questions_asked
            if questions_answered is not None:
                session_db.questions_answered = questions_answered
            if clarifications is not None:
                session_db.clarifications_total = clarifications
            if completeness_score is not None:
                session_db.completeness_score = completeness_score
            if status:
                session_db.status = status
            
            db_session.commit()
            
            logger.info("interview_session_updated", session_id=session_id)
            
            return True
            
        except SQLAlchemyError as e:
            db_session.rollback()
            logger.error("update_interview_session_failed", 
                        session_id=session_id,
                        error=str(e))
            return False
        finally:
            db_session.close()
    
    async def get_statistics(self) -> InterviewStatistics:
        """Получить статистику по всем интервью"""
        session = self._get_session()
        try:
            # Общее количество интервью
            total = session.query(InterviewSessionDB).count()
            
            # Завершённые интервью
            completed = session.query(InterviewSessionDB).filter(
                InterviewSessionDB.status == "completed"
            ).count()
            
            # Средняя длительность
            avg_duration = session.query(
                InterviewSessionDB.duration_seconds
            ).filter(
                InterviewSessionDB.duration_seconds.isnot(None)
            ).all()
            
            avg_duration_minutes = (
                sum(d[0] for d in avg_duration) / len(avg_duration) / 60
                if avg_duration else 0.0
            )
            
            # Breakdown по паттернам
            pattern_counts = {}
            for pattern in InterviewPattern:
                count = session.query(InterviewSessionDB).filter(
                    InterviewSessionDB.pattern == pattern
                ).count()
                pattern_counts[pattern.value] = count
            
            # Breakdown по отраслям (из завершённых анкет)
            industry_counts = {}
            industries = session.query(
                AnketaDB.industry
            ).all()
            
            for industry in industries:
                industry_name = industry[0]
                industry_counts[industry_name] = industry_counts.get(industry_name, 0) + 1
            
            stats = InterviewStatistics(
                total_interviews=total,
                completed_interviews=completed,
                average_duration_minutes=avg_duration_minutes,
                completion_rate=(completed / total * 100) if total > 0 else 0.0,
                pattern_breakdown=pattern_counts,
                industry_breakdown=industry_counts
            )
            
            return stats
            
        except SQLAlchemyError as e:
            logger.error("get_statistics_failed", error=str(e))
            return InterviewStatistics()
        finally:
            session.close()
    
    def health_check(self) -> bool:
        """Проверить подключение к БД"""
        try:
            session = self._get_session()
            session.execute(text("SELECT 1"))
            session.close()
            return True
        except Exception as e:
            logger.error("postgresql_health_check_failed", error=str(e))
            return False
