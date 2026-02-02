"""
Azure OpenAI Realtime Client.

Speech-to-Text и Text-to-Speech через Azure OpenAI Realtime API.
"""

import os
import json
import asyncio
from typing import Any, AsyncGenerator, Callable, Dict, Optional

import httpx
import websockets


class AzureRealtimeClient:
    """
    Клиент для Azure OpenAI Realtime API.

    Функции:
    - Realtime Speech-to-Text
    - Realtime Text-to-Speech
    - Streaming взаимодействие
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        deployment_name: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        """
        Инициализация клиента.

        Args:
            endpoint: Azure OpenAI endpoint
            api_key: API ключ
            deployment_name: Имя deployment (gpt-4o-realtime-preview)
            api_version: Версия API
        """
        self.endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.deployment_name = deployment_name or os.getenv(
            "AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-realtime-preview"
        )
        self.api_version = api_version or os.getenv(
            "AZURE_OPENAI_API_VERSION", "2024-12-17"
        )

        if not all([self.endpoint, self.api_key]):
            raise ValueError("Azure OpenAI credentials not configured")

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False

    @property
    def realtime_url(self) -> str:
        """URL для Realtime API WebSocket."""
        return (
            f"{self.endpoint.replace('https://', 'wss://')}"
            f"/openai/realtime"
            f"?api-version={self.api_version}"
            f"&deployment={self.deployment_name}"
        )

    async def connect(self) -> None:
        """Установить WebSocket соединение."""
        headers = {
            "api-key": self.api_key,
        }

        self._ws = await websockets.connect(
            self.realtime_url,
            extra_headers=headers,
            ping_interval=30,
            ping_timeout=10,
        )
        self._connected = True

        # Настройка сессии
        await self._configure_session()

    async def disconnect(self) -> None:
        """Закрыть соединение."""
        if self._ws:
            await self._ws.close()
            self._ws = None
            self._connected = False

    async def _configure_session(self) -> None:
        """Настроить сессию Realtime API."""
        config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": "Ты AI-консультант по созданию голосовых агентов.",
                "voice": "alloy",  # alloy, echo, fable, onyx, nova, shimmer
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
                "temperature": 0.7,
                "max_response_output_tokens": 1024,
            }
        }

        await self._send(config)

    async def _send(self, message: Dict[str, Any]) -> None:
        """Отправить сообщение через WebSocket."""
        if not self._ws:
            raise RuntimeError("Not connected to Realtime API")

        await self._ws.send(json.dumps(message))

    async def _receive(self) -> Dict[str, Any]:
        """Получить сообщение из WebSocket."""
        if not self._ws:
            raise RuntimeError("Not connected to Realtime API")

        data = await self._ws.recv()
        return json.loads(data)

    async def send_audio(self, audio_data: bytes) -> None:
        """
        Отправить аудио данные.

        Args:
            audio_data: PCM16 аудио данные
        """
        import base64

        message = {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio_data).decode("utf-8"),
        }
        await self._send(message)

    async def commit_audio(self) -> None:
        """Завершить отправку аудио и получить ответ."""
        await self._send({"type": "input_audio_buffer.commit"})
        await self._send({"type": "response.create"})

    async def send_text(self, text: str, generate_audio: bool = True) -> None:
        """
        Отправить текст и получить аудио ответ.

        Args:
            text: Текст сообщения
            generate_audio: Генерировать аудио ответ
        """
        message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": text,
                    }
                ],
            },
        }
        await self._send(message)

        if generate_audio:
            await self._send({"type": "response.create"})

    async def receive_events(
        self,
        on_transcript: Optional[Callable[[str], None]] = None,
        on_audio: Optional[Callable[[bytes], None]] = None,
        on_response_done: Optional[Callable[[], None]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Получать события от Realtime API.

        Args:
            on_transcript: Callback для транскрипции
            on_audio: Callback для аудио данных
            on_response_done: Callback для завершения ответа

        Yields:
            События от API
        """
        import base64

        while self._connected:
            try:
                event = await self._receive()
                event_type = event.get("type", "")

                # Транскрипция входящего аудио
                if event_type == "conversation.item.input_audio_transcription.completed":
                    transcript = event.get("transcript", "")
                    if on_transcript and transcript:
                        on_transcript(transcript)

                # Аудио ответ
                elif event_type == "response.audio.delta":
                    audio_b64 = event.get("delta", "")
                    if on_audio and audio_b64:
                        audio_data = base64.b64decode(audio_b64)
                        on_audio(audio_data)

                # Завершение ответа
                elif event_type == "response.done":
                    if on_response_done:
                        on_response_done()

                yield event

            except websockets.exceptions.ConnectionClosed:
                self._connected = False
                break
            except Exception as e:
                print(f"Error receiving event: {e}")
                continue

    async def transcribe_audio(self, audio_data: bytes) -> str:
        """
        Транскрибировать аудио в текст.

        Args:
            audio_data: PCM16 аудио данные

        Returns:
            Транскрипция
        """
        if not self._connected:
            await self.connect()

        # Отправляем аудио
        await self.send_audio(audio_data)
        await self.commit_audio()

        # Ждём транскрипцию
        transcript = ""
        async for event in self.receive_events():
            if event.get("type") == "conversation.item.input_audio_transcription.completed":
                transcript = event.get("transcript", "")
                break
            if event.get("type") == "response.done":
                break

        return transcript

    async def synthesize_speech(self, text: str) -> bytes:
        """
        Синтезировать речь из текста.

        Args:
            text: Текст для озвучивания

        Returns:
            PCM16 аудио данные
        """
        if not self._connected:
            await self.connect()

        await self.send_text(text, generate_audio=True)

        # Собираем аудио
        import base64
        audio_chunks = []

        async for event in self.receive_events():
            if event.get("type") == "response.audio.delta":
                audio_b64 = event.get("delta", "")
                if audio_b64:
                    audio_chunks.append(base64.b64decode(audio_b64))

            if event.get("type") == "response.done":
                break

        return b"".join(audio_chunks)
