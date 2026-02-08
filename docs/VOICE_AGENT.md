# Voice Agent

Голосовой агент-консультант на базе LiveKit и Azure OpenAI Realtime API.

## Архитектура

```
┌─────────────────┐     WebRTC      ┌─────────────────┐     WSS      ┌─────────────────┐
│                 │ ◄─────────────► │                 │ ◄──────────► │                 │
│  Browser        │   Audio/Video   │  LiveKit Cloud  │   Realtime   │  Azure OpenAI   │
│  (livekit-js)   │                 │                 │     API      │  GPT-4o         │
│                 │                 │                 │              │                 │
└─────────────────┘                 └─────────────────┘              └─────────────────┘
        │                                   │
        │ HTTP                              │ Job dispatch
        ▼                                   ▼
┌─────────────────┐                 ┌─────────────────┐
│  FastAPI        │                 │  LiveKit Agent  │
│  Web Server     │                 │  (Python)       │
│  :8000          │                 │                 │
└─────────────────┘                 └─────────────────┘
```

## Компоненты

### 1. Web Server (`src/web/server.py`)

FastAPI сервер для:
- Раздача статики (`public/`)
- API для создания сессий (`/api/session/create`)
- Генерация LiveKit токенов
- Управление сессиями

```bash
python scripts/run_server.py
# Запускается на http://localhost:8000
```

### 2. Voice Agent (`src/voice/consultant.py`)

LiveKit Agent, который:
- Подключается к комнате при появлении клиента
- Использует Azure OpenAI Realtime API для STT/TTS/LLM
- Ведёт диалог по заданному промпту
- Извлекает данные в анкету

```bash
python scripts/run_voice_agent.py
# Регистрируется в LiveKit Cloud
```

### 3. Browser Client (`public/app.js`)

JavaScript клиент:
- Подключается к LiveKit комнате
- Публикует аудио с микрофона
- Воспроизводит аудио агента
- Отображает диалог в UI

## Поток данных

```
1. Пользователь открывает http://localhost:8000
2. Нажимает "Начать консультацию"
3. Сервер создаёт сессию и LiveKit комнату
4. Браузер подключается к комнате (WebRTC)
5. LiveKit диспатчит задачу агенту
6. Агент подключается к комнате
7. Агент приветствует пользователя (TTS)
8. Пользователь говорит → LiveKit → Agent → Azure VAD → Azure STT
9. Azure GPT-4o генерирует ответ
10. Azure TTS → Agent → LiveKit → Browser (audio)
```

## Конфигурация

### .env

```bash
# LiveKit Cloud
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# Azure OpenAI Realtime
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-realtime-preview
AZURE_OPENAI_API_VERSION=2024-12-17
```

### LiveKit Cloud Setup

1. Создайте проект на [LiveKit Cloud](https://cloud.livekit.io)
2. Скопируйте URL, API Key, API Secret
3. Добавьте в `.env`

### Azure OpenAI Setup

1. Создайте ресурс Azure OpenAI
2. Деплойте модель `gpt-4o-realtime-preview`
3. Скопируйте endpoint и ключ
4. Добавьте в `.env`

## Запуск

### Development

```bash
# Терминал 1: Web server
python scripts/run_server.py

# Терминал 2: Voice agent
python scripts/run_voice_agent.py

# Открыть http://localhost:8000
```

### Production

```bash
# Voice agent (режим определяется через ENVIRONMENT в .env)
python scripts/run_voice_agent.py
```

## Ключевые классы

### RealtimeModel

```python
from livekit.plugins import openai as lk_openai
from livekit.plugins.openai.realtime.realtime_model import TurnDetection

model = lk_openai.realtime.RealtimeModel.with_azure(
    azure_deployment="gpt-4o-realtime-preview",
    azure_endpoint="wss://...",  # Важно: wss://, не https://
    api_key="...",
    api_version="2024-12-17",
    voice="alloy",
    temperature=0.7,
    turn_detection=TurnDetection(
        type="server_vad",
        threshold=0.6,
        prefix_padding_ms=300,
        silence_duration_ms=1200,
    ),
)
```

> **Миграция (livekit-plugins-openai >= 1.2.18):** Класс `ServerVadOptions` удалён.
> Используйте `TurnDetection(type="server_vad", ...)` из
> `livekit.plugins.openai.realtime.realtime_model`.

### VoiceAgent & AgentSession

```python
from livekit.agents.voice import Agent as VoiceAgent, AgentSession
from livekit.agents.voice.room_io import RoomInputOptions

agent = VoiceAgent(instructions=system_prompt)
session = AgentSession(llm=realtime_model, allow_interruptions=True)

room_input = RoomInputOptions(audio_enabled=True)
await session.start(agent, room=ctx.room, room_input_options=room_input)
```

### Event Handlers

```python
@session.on("user_input_transcribed")
def on_transcribed(event):
    print(f"User said: {event.transcript}")

@session.on("agent_state_changed")
def on_state_changed(event):
    print(f"Agent: {event.old_state} -> {event.new_state}")

@session.on("conversation_item_added")
def on_message(event):
    print(f"{event.item.role}: {event.item.content}")
```

## Browser API

### createLocalAudioTrack

```javascript
const { createLocalAudioTrack } = LivekitClient;

const audioTrack = await createLocalAudioTrack({
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
});

await localParticipant.publishTrack(audioTrack);
```

### Track Subscription

```javascript
room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
    if (track.kind === Track.Kind.Audio) {
        const audioElement = track.attach();
        audioElement.play();
        document.body.appendChild(audioElement);
    }
});
```

## Troubleshooting

### Агент не слышит пользователя

1. Проверьте консоль браузера на ошибки
2. Убедитесь, что микрофон разрешён
3. Проверьте `AUDIO LEVEL` в логах (должен быть > 10)
4. Проверьте `/tmp/agent_entrypoint.log`:
   - `Track subscribed` — агент получил аудио трек
   - `USER STATE: listening -> speaking` — VAD обнаружил речь
   - `USER SPEECH: '...'` — STT транскрибировал

### Пользователь не слышит агента

1. Проверьте `TrackSubscribed` в консоли браузера
2. Убедитесь, что `audioElement.play()` не заблокирован
3. Проверьте громкость в системе

### Агент не подключается

1. Проверьте LIVEKIT_* переменные в `.env`
2. Запустите `python scripts/run_voice_agent.py`
3. Проверьте логи на ошибки подключения

### Azure API ошибки

1. Проверьте AZURE_OPENAI_* переменные
2. Убедитесь, что deployment существует
3. Проверьте квоты и лимиты

## E2E Тестирование

```bash
# Установка зависимостей
npm install puppeteer

# Запуск теста (требует работающий сервер и агент)
node tests/e2e_voice_test.js
```

Тест использует fake audio device Chrome для симуляции микрофона.

## Логи

| Файл | Содержимое |
|------|------------|
| `logs/server.log` | FastAPI HTTP запросы |
| `logs/agent.log` | Lifecycle агента |
| `logs/livekit.log` | LiveKit SDK события |
| `/tmp/agent_entrypoint.log` | Debug лог агента (временный) |

## Версии

- LiveKit Agents SDK: >= 1.2.18
- livekit-plugins-openai: >= 1.2.18 (TurnDetection вместо ServerVadOptions)
- livekit-client (JS): 2.9.3
- Azure OpenAI API: 2024-12-17
