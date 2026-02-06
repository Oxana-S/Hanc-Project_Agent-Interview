"""
PostgreSQL Storage Manager для долгосрочного хранения заполненных анкет
"""

from sqlalchemy import create_engine, Column, String, DateTime, JSON, Float, Integer, Text, Enum as SQLEnum, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from typing import Optional, List
import structlog

from src.models import InterviewPattern, InterviewStatistics
from src.anketa.schema import FinalAnketa

logger = structlog.get_logger("storage")

Base = declarative_base()


# ===== МОДЕЛИ БД =====

class AnketaDB(Base):
    """
    Модель анкеты в БД (гибридный подход).

    6 индексированных колонок для быстрого поиска + 1 JSONB для полных данных.
    """
    __tablename__ = "anketas"

    # Индексированные поля для поиска
    anketa_id = Column(String, primary_key=True)
    interview_id = Column(String, unique=True, nullable=False, index=True)
    pattern = Column(String, nullable=False, index=True)  # 'interaction' or 'management'
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    company_name = Column(String, nullable=False, index=True)
    industry = Column(String, nullable=False, index=True)

    # Полные данные анкеты в JSONB
    anketa_json = Column(JSON, nullable=False)


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
    
    async def save_anketa(self, anketa: FinalAnketa) -> bool:
        """
        Сохранить заполненную анкету в БД.

        Args:
            anketa: Заполненная FinalAnketa

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
                company_name=anketa.company_name,
                industry=anketa.industry,
                anketa_json=anketa.model_dump(mode="json")
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
    
    async def get_anketa(self, anketa_id: str) -> Optional[FinalAnketa]:
        """
        Получить анкету по ID.

        Args:
            anketa_id: ID анкеты

        Returns:
            FinalAnketa или None
        """
        session = self._get_session()
        try:
            anketa_db = session.query(AnketaDB).filter(
                AnketaDB.anketa_id == anketa_id
            ).first()

            if anketa_db is None:
                logger.warning("anketa_not_found", anketa_id=anketa_id)
                return None

            # Восстанавливаем FinalAnketa из JSONB
            anketa = FinalAnketa(**anketa_db.anketa_json)

            return anketa

        except SQLAlchemyError as e:
            logger.error("get_anketa_failed",
                         anketa_id=anketa_id,
                         error=str(e))
            return None
        finally:
            session.close()
    
    async def get_anketas_by_company(self, company_name: str) -> List[FinalAnketa]:
        """
        Получить все анкеты компании.

        Args:
            company_name: Название компании

        Returns:
            Список FinalAnketa
        """
        session = self._get_session()
        try:
            anketas_db = session.query(AnketaDB).filter(
                AnketaDB.company_name.ilike(f"%{company_name}%")
            ).all()

            anketas = [FinalAnketa(**a.anketa_json) for a in anketas_db]

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
