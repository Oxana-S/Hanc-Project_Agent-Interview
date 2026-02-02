"""
LiveKit Client.

WebRTC транспорт для голосового взаимодействия.
"""

import os
import time
from typing import Optional
import jwt


class LiveKitClient:
    """
    Клиент для LiveKit.

    Функции:
    - Создание токенов для подключения
    - Управление комнатами
    - Публикация/подписка на аудио треки
    """

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ):
        """
        Инициализация клиента.

        Args:
            url: URL LiveKit сервера (wss://...)
            api_key: API Key
            api_secret: API Secret
        """
        self.url = url or os.getenv("LIVEKIT_URL")
        self.api_key = api_key or os.getenv("LIVEKIT_API_KEY")
        self.api_secret = api_secret or os.getenv("LIVEKIT_API_SECRET")

        if not all([self.url, self.api_key, self.api_secret]):
            raise ValueError("LiveKit credentials not configured")

    def create_token(
        self,
        room_name: str,
        participant_name: str,
        ttl: int = 3600,
        can_publish: bool = True,
        can_subscribe: bool = True,
    ) -> str:
        """
        Создать JWT токен для подключения к комнате.

        Args:
            room_name: Имя комнаты
            participant_name: Имя участника
            ttl: Время жизни токена в секундах
            can_publish: Может публиковать треки
            can_subscribe: Может подписываться на треки

        Returns:
            JWT токен
        """
        now = int(time.time())
        exp = now + ttl

        # Формируем grants
        video_grants = {
            "room": room_name,
            "roomJoin": True,
            "canPublish": can_publish,
            "canSubscribe": can_subscribe,
            "canPublishData": True,
        }

        payload = {
            "iss": self.api_key,
            "sub": participant_name,
            "iat": now,
            "exp": exp,
            "nbf": now,
            "video": video_grants,
            "metadata": "",
            "name": participant_name,
        }

        token = jwt.encode(payload, self.api_secret, algorithm="HS256")
        return token

    def create_agent_token(self, room_name: str, agent_name: str = "ai-consultant") -> str:
        """
        Создать токен для AI агента.

        Args:
            room_name: Имя комнаты
            agent_name: Имя агента

        Returns:
            JWT токен
        """
        return self.create_token(
            room_name=room_name,
            participant_name=agent_name,
            ttl=7200,  # 2 часа
            can_publish=True,
            can_subscribe=True,
        )

    def get_room_url(self, room_name: str) -> str:
        """
        Получить URL для подключения к комнате.

        Args:
            room_name: Имя комнаты

        Returns:
            WebSocket URL
        """
        return f"{self.url}?room={room_name}"

    def generate_room_name(self, session_id: str) -> str:
        """
        Сгенерировать имя комнаты для сессии.

        Args:
            session_id: ID сессии интервью

        Returns:
            Имя комнаты
        """
        return f"interview-{session_id}"
