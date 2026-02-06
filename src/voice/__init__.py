"""
Voice Interface Module.

Голосовое взаимодействие через:
- LiveKit (WebRTC)
- Azure OpenAI Realtime API (STT/TTS)

Использование:
    # Запуск голосового агента
    python scripts/run_voice_agent.py

    # Или программно
    from src.voice import VoiceConsultantAssistant, run_voice_agent
    run_voice_agent()
"""

from src.voice.handler import VoiceHandler
from src.voice.livekit_client import LiveKitClient
from src.voice.azure_realtime import AzureRealtimeClient
from src.voice.consultant import run_voice_agent

__all__ = [
    # Основной голосовой консультант
    "run_voice_agent",

    # Низкоуровневые компоненты
    "VoiceHandler",
    "LiveKitClient",
    "AzureRealtimeClient",
]
