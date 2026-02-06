# Обработка ошибок

Система обработки ошибок Hanc.AI Voice Consultant.

## Иерархия ошибок

```
Exception
├── ValueError
│   ├── DEEPSEEK_API_KEY not set
│   └── Invalid configuration
├── httpx.HTTPStatusError
│   ├── 429 Rate Limit
│   ├── 400 Bad Request
│   └── 500 Server Error
├── httpx.TimeoutException
├── httpx.ConnectError
├── EditorError
│   └── EditorTimeoutError
└── ValidationError (anketa)
```

## API Errors (DeepSeek)

### Rate Limiting (429)

DeepSeekClient автоматически обрабатывает rate limits с exponential backoff:

```python
# src/llm/deepseek.py
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # секунды

# Попытка 1: сразу
# Попытка 2: через 2s
# Попытка 3: через 4s
# Попытка 4: через 8s
```

### Timeout

Увеличенные таймауты для deepseek-reasoner:

| Операция | Таймаут | Причина |
|----------|---------|---------|
| chat() | 180s | Reasoning требует времени |
| analyze_answer() | 120s | Анализ + генерация |
| extract_anketa() | 180s | Большой контекст |

### Логирование ошибок

```python
logger.error(f"DeepSeek API error: status={status_code}, detail={response.text}")
```

Файл: `logs/deepseek.log`

## Voice Agent Errors

### Azure OpenAI Realtime

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `Connection failed` | Неверный endpoint | Проверьте AZURE_OPENAI_ENDPOINT |
| `Authentication failed` | Неверный ключ | Проверьте AZURE_OPENAI_API_KEY |
| `Model not found` | Неверный deployment | Проверьте AZURE_OPENAI_DEPLOYMENT_NAME |
| `Rate limit exceeded` | Превышен лимит | Уменьшите частоту вызовов |

### LiveKit

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `Room not found` | Комната не существует | Проверьте session_id |
| `Connection timeout` | Сетевые проблемы | Проверьте LIVEKIT_URL |
| `Track publish failed` | WebRTC проблемы | Проверьте firewall/NAT |
| `Agent dispatch failed` | Агент не запущен | Запустите run_voice_agent.py |

### Обработка в агенте

```python
# src/voice/consultant.py
try:
    response = await self.session.process_user_input(text)
except Exception as e:
    logger.error(f"Error processing input: {e}")
    await self.session.say("Произошла ошибка. Попробуем ещё раз.")
```

## Web Server Errors

### FastAPI Exception Handlers

```python
# src/web/server.py
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"error": str(exc)}
    )
```

### HTTP Status Codes

| Код | Описание | Когда |
|-----|----------|-------|
| 200 | OK | Успешный запрос |
| 201 | Created | Создана новая сессия |
| 400 | Bad Request | Неверные параметры |
| 404 | Not Found | Сессия не найдена |
| 500 | Server Error | Внутренняя ошибка |

## Storage Errors

### PostgreSQL

```python
# src/storage/postgres.py
from sqlalchemy.exc import SQLAlchemyError

try:
    session.commit()
except SQLAlchemyError as e:
    session.rollback()
    logger.error(f"Database error: {e}")
    raise
```

### Redis

```python
# src/storage/redis.py
try:
    await self.redis.set(key, value, ex=ttl)
except redis.RedisError as e:
    logger.error(f"Redis error: {e}")
    # Fallback to memory storage or re-raise
```

## Validation Errors

### Anketa Validation

```python
# src/agent_document_reviewer/models.py
class ValidationError:
    field: str
    message: str
    severity: str  # "error" | "warning"
```

### Pydantic Validation

```python
try:
    anketa = FinalAnketa(**data)
except ValidationError as e:
    logger.error(f"Anketa validation failed: {e}")
    # Return partial data or re-prompt
```

## Retry Strategies

### Exponential Backoff

```python
async def with_retry(func, max_retries=3, base_delay=1.0):
    for attempt in range(max_retries):
        try:
            return await func()
        except (TimeoutError, ConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)
```

### Circuit Breaker

Для продакшена рекомендуется добавить circuit breaker:

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=30)
async def call_external_api():
    ...
```

## Error Logging

### Структура логов

```
2026-02-06 12:30:45 ERROR [deepseek] DeepSeek API error: status=429, detail={"error":"rate_limit_exceeded"}
2026-02-06 12:30:47 WARNING [deepseek] Rate limit hit, retrying (attempt 1, wait 2.0s)
2026-02-06 12:30:49 INFO [deepseek] Request successful after retry
```

### Файлы логов

| Файл | Содержимое |
|------|------------|
| `logs/server.log` | HTTP запросы, сессии |
| `logs/agent.log` | Voice agent события |
| `logs/deepseek.log` | API вызовы DeepSeek |
| `logs/anketa.log` | Извлечение анкеты |
| `logs/errors.log` | Все ошибки (агрегированно) |

## Graceful Degradation

### Fallback стратегии

| Сервис недоступен | Fallback |
|-------------------|----------|
| DeepSeek | Retry 3x, затем ошибка |
| Azure OpenAI | Переключение на текстовый режим |
| PostgreSQL | Использовать SQLite |
| Redis | Использовать in-memory dict |

### Пример

```python
try:
    await postgres_storage.save_anketa(anketa)
except SQLAlchemyError:
    logger.warning("PostgreSQL unavailable, using SQLite fallback")
    await sqlite_storage.save_anketa(anketa)
```

## Мониторинг ошибок

### Рекомендуемые метрики

| Метрика | Алерт порог | Действие |
|---------|-------------|----------|
| API errors/min | > 10 | Проверить DeepSeek status |
| Voice errors/min | > 5 | Проверить Azure/LiveKit |
| DB errors/min | > 3 | Проверить PostgreSQL |
| Response time p99 | > 5s | Масштабирование |

### Sentry интеграция

```python
import sentry_sdk

sentry_sdk.init(
    dsn="https://...",
    traces_sample_rate=0.1,
    environment="production"
)
```

## Связанная документация

- [LOGGING.md](LOGGING.md) — настройка логирования
- [DEPLOYMENT.md](DEPLOYMENT.md) — production конфигурация
- [VOICE_AGENT.md](VOICE_AGENT.md) — голосовой агент
