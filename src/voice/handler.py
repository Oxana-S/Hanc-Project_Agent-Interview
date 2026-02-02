"""
Voice Handler.

Объединяет LiveKit и Azure Realtime для голосового взаимодействия.
"""

import asyncio
import os
from typing import Any, Callable, Dict, Optional

from src.voice.livekit_client import LiveKitClient
from src.voice.azure_realtime import AzureRealtimeClient
from src.consultant.interviewer import ConsultantInterviewer
from src.models import InterviewPattern


class VoiceHandler:
    """
    Обработчик голосового взаимодействия.

    Связывает:
    - LiveKit (WebRTC транспорт)
    - Azure Realtime (STT/TTS)
    - ConsultantInterviewer (логика)
    """

    def __init__(
        self,
        livekit_client: Optional[LiveKitClient] = None,
        azure_client: Optional[AzureRealtimeClient] = None,
    ):
        """
        Инициализация обработчика.

        Args:
            livekit_client: Клиент LiveKit
            azure_client: Клиент Azure Realtime
        """
        self.livekit = livekit_client or LiveKitClient()
        self.azure = azure_client or AzureRealtimeClient()

        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    async def create_session(
        self,
        session_id: str,
        pattern: InterviewPattern = InterviewPattern.INTERACTION,
    ) -> Dict[str, str]:
        """
        Создать новую голосовую сессию.

        Args:
            session_id: ID сессии
            pattern: Паттерн интервью

        Returns:
            {room_name, user_token, livekit_url}
        """
        room_name = self.livekit.generate_room_name(session_id)
        user_token = self.livekit.create_token(room_name, f"user-{session_id[:8]}")

        # Создаём консультанта для сессии
        interviewer = ConsultantInterviewer(pattern=pattern)

        self._active_sessions[session_id] = {
            "room_name": room_name,
            "interviewer": interviewer,
            "status": "created",
        }

        return {
            "session_id": session_id,
            "room_name": room_name,
            "user_token": user_token,
            "livekit_url": self.livekit.url,
        }

    async def start_session(self, session_id: str) -> None:
        """
        Запустить голосовую сессию.

        Args:
            session_id: ID сессии
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Session {session_id} not found")

        session = self._active_sessions[session_id]
        session["status"] = "active"

        # Подключаемся к Azure Realtime
        await self.azure.connect()

        # Подключаем агента к комнате LiveKit
        agent_token = self.livekit.create_agent_token(session["room_name"])

        # TODO: Реализовать полную интеграцию с LiveKit Agent SDK
        # Это требует установки livekit-agents и более сложной логики

    async def process_user_audio(
        self,
        session_id: str,
        audio_data: bytes,
    ) -> Optional[str]:
        """
        Обработать аудио от пользователя.

        Args:
            session_id: ID сессии
            audio_data: PCM16 аудио данные

        Returns:
            Транскрипция
        """
        if session_id not in self._active_sessions:
            return None

        # Транскрибируем через Azure
        transcript = await self.azure.transcribe_audio(audio_data)
        return transcript

    async def generate_response(
        self,
        session_id: str,
        user_message: str,
    ) -> tuple[str, bytes]:
        """
        Сгенерировать ответ на сообщение пользователя.

        Args:
            session_id: ID сессии
            user_message: Текст сообщения пользователя

        Returns:
            (текст ответа, аудио ответа)
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Session {session_id} not found")

        session = self._active_sessions[session_id]
        interviewer = session["interviewer"]

        # Получаем текстовый ответ от консультанта
        # TODO: Интегрировать с фазами консультанта
        response_text = f"Получил: {user_message}"

        # Синтезируем аудио
        audio_data = await self.azure.synthesize_speech(response_text)

        return response_text, audio_data

    async def end_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Завершить сессию.

        Args:
            session_id: ID сессии

        Returns:
            Результаты сессии
        """
        if session_id not in self._active_sessions:
            return None

        session = self._active_sessions[session_id]
        session["status"] = "completed"

        # Отключаемся от Azure
        await self.azure.disconnect()

        # Получаем результаты
        interviewer = session["interviewer"]
        result = {
            "session_id": session_id,
            "collected": interviewer.collected.to_anketa_dict(),
            "stats": interviewer._get_session_stats(),
        }

        # Удаляем сессию
        del self._active_sessions[session_id]

        return result

    def get_session_status(self, session_id: str) -> Optional[str]:
        """Получить статус сессии."""
        if session_id in self._active_sessions:
            return self._active_sessions[session_id]["status"]
        return None

    @property
    def active_session_count(self) -> int:
        """Количество активных сессий."""
        return len(self._active_sessions)
