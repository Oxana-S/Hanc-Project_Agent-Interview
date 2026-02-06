# Дизайн: Голосовой агент-консультант

**Дата:** 2026-02-04
**Статус:** В разработке

## Цель

Голосовой интерфейс для ConsultantInterviewer — клиент говорит голосом, агент отвечает голосом, анкета заполняется автоматически.

## Архитектура

```
Клиент (браузер/телефон)
         │
         │ WebRTC (аудио)
         ▼
   LiveKit Cloud (wss://hancai-demo-jv845uy1.livekit.cloud)
         │
         │ livekit-agents SDK
         ▼
┌─────────────────────────────────────────────┐
│           VoiceConsultant (Python)          │
│                                             │
│  ┌─────────┐   ┌──────────────┐   ┌─────┐  │
│  │ Azure   │──▶│ Consultant   │──▶│Azure│  │
│  │ STT     │   │ Interviewer  │   │ TTS │  │
│  │(Whisper)│   │ (DeepSeek)   │   │     │  │
│  └─────────┘   └──────────────┘   └─────┘  │
│                      │                      │
│              ┌───────┴───────┐              │
│              │ KB + Anketa   │              │
│              └───────────────┘              │
└─────────────────────────────────────────────┘
```

## Компоненты

### 1. VoiceConsultant (новый класс)

Файл: `src/voice/consultant.py`

Связывает:
- LiveKit (получение/отправка аудио)
- Azure Realtime (STT/TTS)
- ConsultantInterviewer (логика диалога)

### 2. Поток данных

```
1. Клиент говорит → LiveKit получает аудио
2. Аудио → Azure STT → текст
3. Текст → ConsultantInterviewer._handle_user_input()
4. Ответ консультанта → Azure TTS → аудио
5. Аудио → LiveKit → клиент слышит
```

### 3. Управление фазами

ConsultantInterviewer уже имеет фазы:
- Discovery → Analysis → Proposal → Refinement

VoiceConsultant адаптирует:
- Длинные тексты разбиваются на части
- Подтверждения ("Я правильно понял?") работают голосом
- Финализация анкеты по завершении

## Файлы

```
src/voice/
├── __init__.py          # Обновить экспорты
├── consultant.py        # НОВЫЙ: VoiceConsultant
├── handler.py           # Существующий (упростить)
├── livekit_client.py    # Существующий
└── azure_realtime.py    # Существующий

scripts/
└── run_voice_agent.py   # НОВЫЙ: точка входа
```

## Зависимости

```
livekit-agents>=0.8.0
livekit>=0.11.0
```

## Конфигурация

Используем существующий `.env`:
- LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
- AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT_NAME
- DEEPSEEK_API_KEY (для ConsultantInterviewer)

## Запуск

```bash
# Запуск голосового агента
python scripts/run_voice_agent.py

# Агент подключится к LiveKit Cloud и будет ждать клиентов
# Клиент подключается через веб-интерфейс или тестовый скрипт
```

## Тестирование

1. Юнит-тесты для VoiceConsultant
2. Интеграционный тест: симуляция голосового диалога
3. E2E: подключение через браузер
