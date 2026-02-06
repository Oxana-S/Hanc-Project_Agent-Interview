# src/voice/ — Голосовой агент

Модуль голосового AI-консультанта. Принимает голос клиента через LiveKit WebRTC,
обрабатывает через Azure OpenAI Realtime (STT/TTS) и ведёт консультацию.

## Файлы

### consultant.py — Основной модуль агента

Точка входа для LiveKit Agent Worker. Связывает все компоненты.

**Ключевые классы и функции:**

- `VoiceConsultationSession` — состояние голосовой сессии (диалог, таймер, статус)
- `entrypoint(ctx: JobContext)` — вызывается LiveKit при подключении клиента к комнате
- `run_voice_agent()` — запуск worker-процесса через `cli.run_app()`
- `finalize_consultation()` — генерация анкеты и сохранение после завершения

**Пошаговый процесс `entrypoint()`:**

1. Создание `RealtimeModel` (Azure OpenAI WSS-соединение)
2. Создание `VoiceAgent` с системным промптом
3. Подключение к комнате LiveKit (`ctx.connect()`)
4. Создание `AgentSession` и регистрация обработчиков событий
5. Запуск сессии и отправка приветствия

**Интеграция с SessionManager:**

- Извлекает `session_id` из имени комнаты (`consultation-{session_id}`)
- Синхронизирует диалог в SQLite каждое сообщение
- Каждые 6 сообщений извлекает анкету через DeepSeek
- При закрытии сессии — финальная генерация анкеты

**Переменные окружения:**

```text
AZURE_OPENAI_ENDPOINT              — https://<ресурс>.openai.azure.com/
AZURE_OPENAI_API_KEY               — ключ доступа
AZURE_OPENAI_DEPLOYMENT_NAME       — имя deployment (gpt-4o-realtime-preview)
AZURE_OPENAI_REALTIME_API_VERSION  — версия API (2024-10-01-preview)
LIVEKIT_URL                        — wss://<проект>.livekit.cloud
LIVEKIT_API_KEY                    — ключ LiveKit
LIVEKIT_API_SECRET                 — секрет LiveKit
```

### handler.py — Обработчик голосовых сессий

Высокоуровневый менеджер голосовых сессий.

- `VoiceHandler` — создание, запуск и завершение сессий
- `create_session()` — инициализация новой голосовой сессии
- `process_user_audio()` — приём аудио, транскрипция, генерация ответа
- `end_session()` — корректное завершение и возврат результатов

### livekit_client.py — LiveKit утилиты

JWT-токены и управление комнатами.

- `LiveKitClient` — генерация токенов для участников и агентов
- `create_token(room, identity)` — JWT с правами publish/subscribe
- `create_agent_token(room, identity)` — JWT для агента
- `generate_room_name(session_id)` — формирование имени комнаты

### azure_realtime.py — Azure OpenAI Realtime клиент

Низкоуровневый WebSocket-клиент для Azure OpenAI Realtime API.

- `AzureRealtimeClient` — управление WSS-соединением
- `connect()` / `disconnect()` — жизненный цикл соединения
- `send_audio()` — отправка аудио (PCM16)
- `transcribe_audio()` — получение транскрипции (STT)
- `synthesize_speech()` — генерация голоса (TTS)
- Поддержка VAD (Voice Activity Detection) на стороне сервера

### __init__.py — Экспорты

```python
from src.voice.consultant import run_voice_agent
from src.voice.handler import VoiceHandler
from src.voice.livekit_client import LiveKitClient
from src.voice.azure_realtime import AzureRealtimeClient
```

## Запуск

```bash
# Через скрипт (рекомендуется)
./venv/bin/python scripts/run_voice_agent.py dev

# Напрямую
./venv/bin/python -m src.voice.consultant
```

Аргумент `dev` включает режим разработки LiveKit (автоматическая регистрация worker).

## Архитектура соединений

```text
Браузер                 LiveKit Cloud              Голосовой агент
   |                        |                           |
   |-- WebRTC audio ------->|                           |
   |                        |-- dispatch agent -------->|
   |                        |                           |
   |                        |<-- agent joins room ------|
   |                        |                           |
   |                        |                    Azure OpenAI Realtime
   |                        |                           |
   |                        |                           |-- WSS connect -->|
   |                        |                           |<-- STT/TTS ---->|
   |                        |                           |
   |<-- agent audio track --|<-- audio published -------|
   |                        |                           |
   |-- user speaks -------->|-- audio forwarded ------->|-- send to Azure ->
   |                        |                           |<-- response ------|
   |<-- agent responds -----|<-- synthesized audio -----|
```

## Логирование

Логи пишутся в `logs/agent.log` и консоль.

Ключевые маркеры в логах:

| Маркер | Значение |
| ------ | -------- |
| `=== AGENT ENTRYPOINT CALLED ===` | Агент получил задание от LiveKit |
| `AGENT STEP 1/5` — `STEP 5/5` | Этапы инициализации |
| `=== AGENT FULLY READY ===` | Агент готов к диалогу |
| `DIALOGUE_MESSAGE` | Новое сообщение в диалоге |
| `periodic_anketa_extracted` | Промежуточная анкета извлечена |
| `=== FINALIZE START ===` | Начало финализации сессии |
| `STEP X/5 FAILED` | Ошибка на этапе инициализации |

## Troubleshooting

**Агент не получает dispatch (нет `ENTRYPOINT CALLED`):**

- Проверьте что агент запущен с аргументом `dev`
- Проверьте что `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` корректны
- Убедитесь что сервер создаёт комнату с `RoomAgentDispatch`

**Ошибка `WSServerHandshakeError: 404`:**

- Неправильная версия API для Realtime
- Установите `AZURE_OPENAI_REALTIME_API_VERSION=2024-10-01-preview` в `.env`
- GA-версия (`2024-12-17`) не поддерживает `/openai/realtime` на многих эндпоинтах

**Ошибка `APIConnectionError: connection failed after 3 attempts`:**

- Проверьте `AZURE_OPENAI_ENDPOINT` и `AZURE_OPENAI_API_KEY`
- Убедитесь что deployment существует в Azure AI Studio
