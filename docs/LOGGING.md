# Система логирования

Логи разделены на 10 файлов по направлениям + общий файл ошибок.

## Структура `logs/`

```text
logs/
├── server.log          # HTTP API запросы (создание сессий, polling анкеты)
├── agent.log           # Жизненный цикл агента (запуск, шаги 1-5, готовность)
├── livekit.log         # LiveKit события (создание комнат, токены, подключения)
├── dialogue.log        # Сообщения диалога (кто что сказал, когда)
├── anketa.log          # Извлечение анкеты, обновления, генерация файлов
├── azure.log           # Azure OpenAI Realtime (WSS-соединение, модель)
├── session.log         # Жизненный цикл сессий (создание, статусы, финализация)
├── deepseek.log        # DeepSeek LLM API вызовы, ретраи, ошибки
├── notifications.log   # Email, webhooks
├── output.log          # Сохранение файлов (OutputManager)
└── errors.log          # ВСЕ ошибки из всех компонентов (ERROR+)
```

## Категории и процессы

Каждый процесс активирует только свои категории:

| Категория | Файл | Server | Agent | Модули |
| --- | --- | --- | --- | --- |
| server | server.log | + | | `src/web/server.py` |
| agent | agent.log | | + | `src/voice/consultant.py` (lifecycle) |
| livekit | livekit.log | + | + | `server.py` (room), `consultant.py` (connect) |
| dialogue | dialogue.log | | + | `consultant.py` (сообщения) |
| anketa | anketa.log | | + | `src/anketa/*.py` |
| azure | azure.log | | + | `consultant.py` (RealtimeModel, WSS) |
| session | session.log | + | + | `src/session/manager.py` |
| deepseek | deepseek.log | | + | `src/llm/deepseek.py` |
| notifications | notifications.log | + | | `src/notifications/manager.py` |
| output | output.log | | + | `src/output/manager.py` |
| (root ERROR) | errors.log | + | + | все модули, только ERROR+ |

### PROCESS_CATEGORIES

```python
PROCESS_CATEGORIES = {
    "server": ["server", "livekit", "session", "notifications"],
    "agent":  ["agent", "livekit", "dialogue", "anketa",
               "azure", "session", "deepseek", "output"],
}
```

## Конфигурация

Файл: `src/logging_config.py`

### Инициализация

```python
from src.logging_config import setup_logging

# В web сервере (src/web/server.py)
setup_logging("server")   # создаёт: server.log, livekit.log, session.log, notifications.log

# В голосовом агенте (src/voice/consultant.py)
setup_logging("agent")    # создаёт: agent.log, livekit.log, dialogue.log, anketa.log,
                           #          azure.log, session.log, deepseek.log, output.log
```

`setup_logging()` вызывается один раз при старте процесса. Повторные вызовы игнорируются (`_initialized` guard).

### Именованные логгеры

```python
# structlog (большинство модулей)
import structlog
logger = structlog.get_logger("anketa")      # → logs/anketa.log

# stdlib logging (deepseek.py)
import logging
logger = logging.getLogger("deepseek")       # → logs/deepseek.log
```

## Формат записей

```text
2026-02-05 14:30:15 [INFO] [anketa] periodic_anketa_extracted session_id=abc12345 company=АвтоПрофи
2026-02-05 14:30:16 [INFO] [dialogue] DIALOGUE_MESSAGE role=user preview=Мы занимаемся ремонтом авт... total_messages=8
2026-02-05 14:30:17 [ERROR] [deepseek] DeepSeek API error status=429 retry=2/3
```

Формат: `%(asctime)s [%(levelname)s] [%(name)s] %(message)s`

## Иерархия обработчиков

```text
Root Logger
├── Console Handler (stdout) ── все уровни
├── errors.log Handler ──────── только ERROR+
│
├── Logger "server" ─── server.log
├── Logger "agent" ──── agent.log
├── Logger "livekit" ── livekit.log
├── Logger "dialogue" ─ dialogue.log
├── Logger "anketa" ─── anketa.log
├── Logger "azure" ──── azure.log
├── Logger "session" ── session.log
├── Logger "deepseek" ─ deepseek.log
├── Logger "notifications" ─ notifications.log
└── Logger "output" ─── output.log
```

Все именованные логгеры propagate=True → их записи также попадают:
- В консоль (через Root → Console Handler)
- В errors.log (через Root → errors.log Handler, если ERROR+)

## Маппинг модуль → логгер

| Модуль | Логгеры |
| --- | --- |
| `src/voice/consultant.py` | agent, azure, dialogue, livekit, anketa, session |
| `src/web/server.py` | server, livekit, session |
| `src/session/manager.py` | session |
| `src/anketa/extractor.py` | anketa |
| `src/anketa/generator.py` | anketa |
| `src/anketa/data_cleaner.py` | anketa |
| `src/anketa/markdown_parser.py` | anketa |
| `src/anketa/review_service.py` | anketa |
| `src/llm/deepseek.py` | deepseek |
| `src/output/manager.py` | output |
| `src/notifications/manager.py` | notifications |

### Логгеры без выделенного файла

| Логгер | Модули | Куда пишется |
| --- | --- | --- |
| `documents` | `src/documents/parser.py`, `src/documents/analyzer.py` | Только консоль + errors.log (если ERROR+) |
| (default) | `src/storage/redis.py`, `src/storage/postgres.py`, `src/config/synonym_loader.py`, `src/knowledge/manager.py` | Только консоль + errors.log (если ERROR+) |

Эти логгеры не включены в `LOG_CATEGORIES`, поэтому для них не создаётся отдельный файл. Записи попадают через root logger в консоль и, при уровне ERROR+, в `errors.log`.

## Использование

### Просмотр конкретного направления

```bash
# Только диалог
tail -f logs/dialogue.log

# Только ошибки
tail -f logs/errors.log

# Сессии из обоих процессов
tail -f logs/session.log

# LiveKit события
tail -f logs/livekit.log
```

### Фильтрация

```bash
# Все записи конкретной сессии
grep "session_id=abc12345" logs/*.log

# Ошибки DeepSeek
grep "ERROR" logs/deepseek.log

# Все извлечения анкеты
grep "periodic_anketa_extracted" logs/anketa.log
```

### Проверка изоляции

```bash
# Каждый файл должен содержать только свою категорию:
grep -c "\[server\]" logs/server.log      # > 0
grep -c "\[anketa\]" logs/server.log      # = 0

grep -c "\[dialogue\]" logs/dialogue.log  # > 0
grep -c "\[server\]" logs/dialogue.log    # = 0
```
