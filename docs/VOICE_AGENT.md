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
- Управление сессиями и комнатами
- Health check голосового агента (`/api/agent/health`)
- Автоочистка старых LiveKit-комнат при старте

```bash
./venv/bin/python scripts/run_server.py
# Запускается на http://localhost:8000
```

### 2. Voice Agent (`src/voice/consultant.py`)

LiveKit Agent, который:
- Подключается к комнате при появлении клиента
- Использует Azure OpenAI Realtime API для STT/TTS/LLM
- Ведёт диалог по заданному промпту
- Извлекает данные в анкету (каждые 6 сообщений через DeepSeek)
- Защищён от дублирования через PID-файл (`.agent.pid`)

```bash
# Рекомендуется: через hanc.sh
./scripts/hanc.sh start

# Или напрямую
./venv/bin/python scripts/run_voice_agent.py
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
./venv/bin/python scripts/run_server.py

# Терминал 2: Voice agent (через hanc.sh — рекомендуется)
./scripts/hanc.sh start

# Открыть http://localhost:8000
```

### Управление процессами (`scripts/hanc.sh`)

```bash
./scripts/hanc.sh start      # Запустить агент в фоне
./scripts/hanc.sh stop       # Остановить (SIGTERM, затем SIGKILL через 10 сек)
./scripts/hanc.sh restart    # Перезапустить
./scripts/hanc.sh status     # Показать статус всех процессов
./scripts/hanc.sh logs       # tail -f логов агента
./scripts/hanc.sh kill-all   # Аварийное завершение (SIGKILL)
```

Агент защищён от дублирования: PID записывается в `.agent.pid`, при попытке запуска второй копии скрипт предупредит. PID-файл автоматически удаляется при корректном завершении (`SIGTERM`, `atexit`).

### Health Check

```bash
# Проверка через API
curl http://localhost:8000/api/agent/health
# {"worker_alive": true, "worker_pid": 12345}
```

Фронтенд автоматически проверяет доступность агента перед созданием сессии. Если агент не запущен — показывает сообщение с инструкцией.

### Production

```bash
# Voice agent (режим определяется через ENVIRONMENT в .env)
./venv/bin/python scripts/run_voice_agent.py prod
```

Для systemd-сервисов см. [DEPLOYMENT.md](DEPLOYMENT.md).

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
        threshold=0.85,        # Строгий фильтр шума (0.5=default, выше=менее чувствительный)
        prefix_padding_ms=500,  # Буфер аудио перед началом речи
        silence_duration_ms=2000,  # 2с тишины до окончания реплики
        eagerness="low",        # Терпеливый: ждёт дольше перед ответом ("high"=немедленно)
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
session = AgentSession(
    llm=realtime_model,
    allow_interruptions=True,
    min_interruption_duration=1.5,   # Минимум 1.5с речи для прерывания
    min_interruption_words=3,        # Минимум 3 слова
    min_endpointing_delay=1.5,       # Ждать 1.5с после тишины перед ответом
    false_interruption_timeout=2.5,  # Время на определение ложного прерывания
    resume_false_interruption=True,  # Возобновлять речь после ложного прерывания
)

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

## Восстановление сессий

При перезагрузке страницы сессия восстанавливается автоматически:

1. URL обновляется через `pushState` после создания сессии (`/session/{uniqueLink}`)
2. При загрузке страницы фронтенд проверяет URL и вызывает `GET /api/session/{id}/reconnect`
3. Сервер проверяет LiveKit-комнату, при необходимости пересоздаёт и диспатчит агента
4. Клиент получает новый токен и переподключается к комнате

## Управление LiveKit-комнатами

```bash
# Список активных комнат
curl http://localhost:8000/api/rooms

# Удаление всех комнат (очистка)
curl -X DELETE http://localhost:8000/api/rooms

# CLI-скрипт для очистки
./venv/bin/python scripts/cleanup_rooms.py
./venv/bin/python scripts/cleanup_rooms.py --force  # без подтверждения
```

При старте сервера все старые комнаты автоматически удаляются.

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

### Агент обрезает фразы / "заикается" (v2.0 fix)

**Проблема:** Агент начинает отвечать, но обрывается на полуслове. Пользователь слышит
"Расскажите, пожалуйста, о вашей компании: чем" — и тишина.

**Причина (диагностировано из логов):** Призрачные VAD-триггеры. Azure server_vad
детектирует шум/эхо/дыхание как "речь", STT возвращает пустую строку, агент начинает
отвечать на ничего, реальная речь пользователя прерывает этот призрачный ответ.
За 71 секунд сессии — 4 призрачных триггера.

**Решение (v2.0):**

Серверная сторона (TurnDetection — Azure VAD):
- `threshold`: 0.65 → **0.85** (строже фильтрует шум)
- `silence_duration_ms`: 1500 → **2000** (ждёт 2с тишины)
- `prefix_padding_ms`: 300 → **500** (больше контекста)
- `eagerness`: не задан → **"low"** (терпеливый, не торопится отвечать)

Клиентская сторона (AgentSession — LiveKit SDK):
- `min_interruption_duration`: 0.8 → **1.5** (1.5с речи для прерывания)
- `min_interruption_words`: 2 → **3** (минимум 3 слова)
- `min_endpointing_delay`: 0.5 → **1.5** (ждать 1.5с перед ответом)
- `false_interruption_timeout`: 1.5 → **2.5** (было ниже дефолта 2.0 — ошибка v1.5!)
- `resume_false_interruption`: True (возобновлять после ложных прерываний)

Также Azure OpenAI Realtime API может:

- Переключиться на text-only стрим (без TTS) при быстрой отмене+создании ответа
- Приостановить отправку событий на 20-40 секунд ([Community report](https://community.openai.com/t/1368051))

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
