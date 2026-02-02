"""
Redis Storage Manager для хранения текущих сессий интервью
"""

import json
import redis
from typing import Optional
from datetime import timedelta
from src.models import InterviewContext
import structlog

logger = structlog.get_logger()


class RedisStorageManager:
    """
    Управление хранилищем Redis для активных сессий интервью
    """
    
    def __init__(self, host: str = "localhost", port: int = 6379, 
                 password: Optional[str] = None, db: int = 0,
                 session_ttl: int = 7200):
        """
        Args:
            host: Redis host
            port: Redis port
            password: Redis password (optional)
            db: Redis database number
            session_ttl: Time-to-live для сессий в секундах (default: 2 часа)
        """
        self.host = host
        self.port = port
        self.db = db
        self.session_ttl = session_ttl
        
        # Подключение к Redis
        self.client = redis.Redis(
            host=host,
            port=port,
            password=password,
            db=db,
            decode_responses=True  # Автоматически декодировать в строки
        )
        
        logger.info("redis_connected", host=host, port=port, db=db)
    
    def _get_key(self, session_id: str) -> str:
        """Получить ключ для Redis"""
        return f"interview:session:{session_id}"
    
    async def save_context(self, context: InterviewContext) -> bool:
        """
        Сохранить контекст интервью в Redis
        
        Args:
            context: Контекст интервью
            
        Returns:
            True если успешно сохранено
        """
        try:
            key = self._get_key(context.session_id)
            
            # Сериализуем контекст в JSON
            context_json = context.model_dump_json()
            
            # Сохраняем с TTL
            self.client.setex(
                name=key,
                time=timedelta(seconds=self.session_ttl),
                value=context_json
            )
            
            logger.info("context_saved", 
                       session_id=context.session_id,
                       interview_id=context.interview_id,
                       questions_answered=context.answered_questions)
            
            return True
            
        except Exception as e:
            logger.error("context_save_failed", 
                        session_id=context.session_id,
                        error=str(e))
            return False
    
    async def load_context(self, session_id: str) -> Optional[InterviewContext]:
        """
        Загрузить контекст интервью из Redis
        
        Args:
            session_id: ID сессии
            
        Returns:
            Контекст интервью или None если не найден
        """
        try:
            key = self._get_key(session_id)
            context_json = self.client.get(key)
            
            if context_json is None:
                logger.warning("context_not_found", session_id=session_id)
                return None
            
            # Десериализуем из JSON
            context = InterviewContext.model_validate_json(context_json)
            
            logger.info("context_loaded", 
                       session_id=session_id,
                       interview_id=context.interview_id)
            
            return context
            
        except Exception as e:
            logger.error("context_load_failed", 
                        session_id=session_id,
                        error=str(e))
            return None
    
    async def update_context(self, context: InterviewContext) -> bool:
        """
        Обновить существующий контекст
        
        Args:
            context: Обновлённый контекст
            
        Returns:
            True если успешно обновлено
        """
        # Обновление = перезапись с новым TTL
        return await self.save_context(context)
    
    async def delete_context(self, session_id: str) -> bool:
        """
        Удалить контекст интервью
        
        Args:
            session_id: ID сессии
            
        Returns:
            True если успешно удалено
        """
        try:
            key = self._get_key(session_id)
            deleted = self.client.delete(key)
            
            if deleted:
                logger.info("context_deleted", session_id=session_id)
            else:
                logger.warning("context_not_found_for_deletion", 
                             session_id=session_id)
            
            return bool(deleted)
            
        except Exception as e:
            logger.error("context_delete_failed", 
                        session_id=session_id,
                        error=str(e))
            return False
    
    async def extend_ttl(self, session_id: str, additional_seconds: int = 3600) -> bool:
        """
        Продлить TTL сессии
        
        Args:
            session_id: ID сессии
            additional_seconds: Дополнительное время в секундах
            
        Returns:
            True если успешно продлено
        """
        try:
            key = self._get_key(session_id)
            
            # Получаем текущий TTL
            current_ttl = self.client.ttl(key)
            
            if current_ttl == -2:  # Ключ не существует
                logger.warning("cannot_extend_nonexistent_key", 
                             session_id=session_id)
                return False
            
            # Устанавливаем новый TTL
            new_ttl = max(current_ttl, 0) + additional_seconds
            self.client.expire(key, new_ttl)
            
            logger.info("ttl_extended", 
                       session_id=session_id,
                       new_ttl_seconds=new_ttl)
            
            return True
            
        except Exception as e:
            logger.error("ttl_extension_failed", 
                        session_id=session_id,
                        error=str(e))
            return False
    
    async def get_all_active_sessions(self) -> list[str]:
        """
        Получить все активные сессии
        
        Returns:
            Список session_id активных сессий
        """
        try:
            pattern = "interview:session:*"
            keys = self.client.keys(pattern)
            
            # Извлекаем session_id из ключей
            session_ids = [key.split(":")[-1] for key in keys]
            
            logger.info("active_sessions_fetched", count=len(session_ids))
            
            return session_ids
            
        except Exception as e:
            logger.error("fetch_active_sessions_failed", error=str(e))
            return []
    
    async def get_session_info(self, session_id: str) -> Optional[dict]:
        """
        Получить краткую информацию о сессии без загрузки полного контекста
        
        Args:
            session_id: ID сессии
            
        Returns:
            Словарь с базовой информацией
        """
        try:
            key = self._get_key(session_id)
            
            # Проверяем существование
            if not self.client.exists(key):
                return None
            
            # Получаем TTL
            ttl = self.client.ttl(key)
            
            # Загружаем контекст
            context = await self.load_context(session_id)
            
            if context is None:
                return None
            
            return {
                "session_id": session_id,
                "interview_id": context.interview_id,
                "pattern": context.pattern,
                "status": context.status,
                "progress_percentage": context.get_progress_percentage(),
                "answered_questions": context.answered_questions,
                "total_questions": context.total_questions,
                "started_at": context.started_at.isoformat(),
                "ttl_seconds": ttl
            }
            
        except Exception as e:
            logger.error("get_session_info_failed", 
                        session_id=session_id,
                        error=str(e))
            return None
    
    def health_check(self) -> bool:
        """
        Проверить подключение к Redis
        
        Returns:
            True если Redis доступен
        """
        try:
            self.client.ping()
            return True
        except Exception as e:
            logger.error("redis_health_check_failed", error=str(e))
            return False
