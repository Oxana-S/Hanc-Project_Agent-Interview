"""
Voice Interface Module.

Голосовое взаимодействие через:
- LiveKit (WebRTC)
- Azure OpenAI Realtime API (STT/TTS)
"""

from src.voice.handler import VoiceHandler
from src.voice.livekit_client import LiveKitClient
from src.voice.azure_realtime import AzureRealtimeClient

__all__ = [
    "VoiceHandler",
    "LiveKitClient",
    "AzureRealtimeClient",
]
