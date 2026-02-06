# Аудит проекта и план улучшений

**Дата:** 2026-02-05
**Версия:** 1.0

---

## Результаты аудита

Проведён полный аудит кодовой базы: проверены все модули в `src/`, конфигурация, тесты, документация. Найдены расхождения между документацией и реальным кодом, дублирования, устаревшие файлы.

### Исправлено ранее (16 расхождений)

1. **CRITICAL**: Система имеет 3 режима, а не 2 (Maximum Interview отсутствовал в документации)
2. **CRITICAL**: `src/storage/` был помечен как "legacy", хотя активно используется Maximum режимом
3. **CRITICAL**: Модуль `src/interview/` полностью отсутствовал в документации
4. **CRITICAL**: В TESTING.md были перечислены 15 несуществующих тестовых файлов (реально 9 файлов в `tests/unit/`)
5. **CRITICAL**: `DEEPSEEK_MODEL=deepseek-chat` вместо правильного `deepseek-reasoner`
6. Модуль `src/cli/` отсутствовал в ARCHITECTURE.md
7. Модуль `src/research/` отсутствовал в ARCHITECTURE.md
8. `phases.py` описан неправильно (нет `COMPLETED` фазы)
9. Запись "4 этапа" без указания MaximumInterviewer (3 фазы)
10. Зависимости Redis/PostgreSQL не указаны
11. `docker-compose.yml` не документирован
12. Пути скриптов в PYTHON_3.14_SETUP.md указаны неправильно
13. Логгеры `documents` и дефолтный не задокументированы
14. TOC в AGENT_WORKFLOWS.md неполный
15. Нумерация секций в QUICKSTART.md сбита
16. Независимость Maximum режима не отражена

---

## Категория A: Архитектура и код

### A1: Унификация 3 моделей анкет [БОЛЬШАЯ ЗАДАЧА]

**Проблема:** В проекте 3 разные модели анкеты с разными форматами:

| Модель | Файл | Тип | Назначение |
|--------|------|-----|------------|
| `CompletedAnketa` | `src/models.py` | Pydantic BaseModel | PostgreSQL (Maximum) |
| `FinalAnketa` | `src/anketa/schema.py` | Pydantic v2, 18 блоков | Consultant/Voice режимы |
| `FullAnketa` | `src/llm/anketa_generator.py` | dataclass, 78 полей | LLM-генерация |

**Рекомендация:** Выбрать `FinalAnketa` (самая полная, 18 блоков, Pydantic v2) как единую модель. Адаптировать `CompletedAnketa` и `FullAnketa` через конвертеры или наследование.

**Статус:** Документировано для будущей реализации. Требует тщательного рефакторинга с проверкой всех мест использования.

### A2: Переименование AnketaGenerator -> AnketaFormatter [СРЕДНЯЯ]

**Проблема:** Два "генератора" с путаницей имён:
- `AnketaGenerator` (`src/anketa/generator.py`) — форматирует FinalAnketa в MD/JSON
- `LLMAnketaGenerator` (`src/llm/anketa_generator.py`) — генерирует анкету из диалога через LLM

**Рекомендация:** Переименовать `AnketaGenerator` -> `AnketaFormatter` для ясности.

**Статус:** Документировано для будущей реализации. Требует обновления всех импортов.

### A3: Добавить deprecation notice в src/voice/handler.py [DONE]

**Проблема:** `handler.py` содержит TODO-заглушки, в то время как `consultant.py` имеет полную реализацию.

**Решение:** Добавить deprecated notice в начало файла.

### A4: Аудит azure_realtime.py и livekit_client.py

**Результат:** Оба файла — самостоятельные утилитарные модули:
- `azure_realtime.py` (286 строк): Полный WebSocket клиент для Azure OpenAI Realtime API
- `livekit_client.py` (133 строки): JWT-токены и утилиты для LiveKit

Оба файла импортируются в `handler.py` и потенциально в `consultant.py`. Модули рабочие, не нуждаются в изменениях.

### A5: Удаление неиспользуемых RAG-зависимостей [DONE]

**Проблема:** `requirements.txt` содержит `azure-search-documents==11.4.0` и `sentence-transformers==2.3.1` дважды (как закомментированные и незакомментированные), RAG не реализован.

**Решение:** Удалить незакомментированные, оставить закомментированные с пометкой "для будущего использования".

### A6: Добавить именованные логгеры [DONE]

**Проблема:** Модули `src/storage/redis.py`, `src/storage/postgres.py`, `src/config/synonym_loader.py` используют `structlog.get_logger()` без имени.

**Решение:** Заменить на именованные: `structlog.get_logger("storage")`, `structlog.get_logger("config")`.

### A7: Разделение src/models.py [НИЗКИЙ ПРИОРИТЕТ]

**Текущее состояние:** 315 строк, содержит enums + InterviewContext + CompletedAnketa + InterviewStatistics.

**Рекомендация:** Оставить как есть — файл не слишком большой, логически связанные модели.

### A8: Перемещение docker-compose.yml [ОТЛОЖЕНО]

**Текущее расположение:** `config/docker-compose.yml`

**Рекомендация:** Оставить в `config/` — это часть конфигурации, не корневой файл проекта. Документация уже корректно указывает путь.

### A9: Создание Makefile [DONE]

**Решение:** Создать `Makefile` с командами для всех трёх режимов, тестов, инфраструктуры.

---

## Категория B: Тестирование [БОЛЬШИЕ ЗАДАЧИ]

### B1: Тесты для бизнес-логики

**Текущее состояние:** 252 теста в 9 файлах покрывают только инфраструктуру:
- `test_models.py`, `test_redis_storage.py`, `test_postgres_storage.py`
- `test_anketa_schema.py`, `test_synonym_loader.py`, `test_knowledge.py`
- `test_interview_phases.py`, `test_cli_interface.py`, `test_review_service.py`

**Отсутствуют тесты для:**
- `AnketaExtractor` (основная бизнес-логика)
- `ConsultantInterviewer` (4-фазная консультация)
- `DeepSeekClient` (LLM-вызовы, ретраи)
- `OutputManager` (сохранение файлов)
- `DocumentAnalyzer` (анализ документов)
- `logging_config` (настройка логирования)

**Статус:** Документировано для будущей реализации.

### B2: Интеграционные тесты

**Отсутствуют тесты для:**
- Full pipeline: диалог -> анкета -> файлы
- Голосовой режим: LiveKit -> Azure -> DeepSeek
- Maximum режим: Redis -> PostgreSQL -> Output

**Статус:** Документировано для будущей реализации.

### B3: Тесты Redis/PostgreSQL

**Текущие тесты** используют mock-объекты. Для полной проверки нужны тесты с реальными Redis и PostgreSQL (через docker-compose в CI).

**Статус:** Документировано для будущей реализации.

---

## Категория C: Конфигурация

### C1: Реструктуризация .env [DONE]

**Проблема:** `.env` не имеет группировки по режимам. `.env.example` устарел (другие переменные, другой deployment name).

**Решение:**
- Реструктурировать `.env` с группировкой по режимам
- Скопировать `.env` в `.env.example` (как указал пользователь)

### C2: Очистка requirements.txt [DONE]

**Проблемы:**
1. Секция `DEVELOPMENT` дублируется (закомментированная и незакомментированная)
2. RAG-зависимости дублируются
3. `sentence-transformers` тянет тяжёлые зависимости (PyTorch)

**Решение:** Убрать дубликаты, оставить одну секцию для dev, закомментировать RAG.

### C3: Проверка config/init_db.sql

**Результат:** SQL-схема соответствует моделям в `src/storage/postgres.py`. Таблицы `anketas` и `interview_sessions` совпадают по полям. Дополнительно есть таблица `statistics`, представления и триггеры, которые не используются в Python-коде (но полезны для прямых SQL-запросов).

---

## Категория D: Документация

### D1: Обновление docs/example_anketa.md [DONE]

**Проблема:** Пример анкеты в формате CompletedAnketa (старая структура: 4 секции), а не FinalAnketa v2.0 (18 блоков).

**Решение:** Обновить формат с сохранением содержания.

### D2: Перемещение рабочих заметок [DONE]

**Проблема:** В `docs/` находятся рабочие заметки на русском с датами:
- `2026-02-02 23-55_Что сделано.txt`
- `2026-02-03_16-32_DocumentReviewer_ План-Описание.txt`
- `2026-02-05 13-35_Описание для системы Логирования.txt`

**Решение:** Переместить в `docs/archive/`.

### D3: Ссылка на PYTHON_3.14_SETUP.md в README [DONE]

**Решение:** Добавить в секцию "Документация" README.

### D4: Документирование /docs endpoint [DONE]

**Решение:** Добавить в секцию API README пометку о Swagger UI на `/docs`.

### D5: Перемещение #_prompt.md [DONE]

**Проблема:** Философский документ проекта лежит в корне с нестандартным именем.

**Решение:** Переместить в `docs/` как `docs/PHILOSOPHY.md`.

---

## Категория E: Качество кода

### E1: Deprecated SQLAlchemy import [DONE]

**Проблема:** `src/storage/postgres.py:6` использует:
```python
from sqlalchemy.ext.declarative import declarative_base
```
Это deprecated с SQLAlchemy 2.0. Правильный импорт:
```python
from sqlalchemy.orm import declarative_base
```

### E2: Перемещение #_prompt.md [DONE]

См. D5 выше.

### E3: Перемещение Старт.txt [DONE]

**Решение:** Переместить в `docs/archive/`.

### E4: Удаление synonyms.yaml.bak [DONE]

**Решение:** Удалить backup-файл, т.к. есть git history.

### E5: Добавление output/ в .gitignore [DONE]

**Проблема:** `output/` не указан в `.gitignore`, хотя содержит генерируемые файлы.

---

## Приоритеты

| Приоритет | Задачи | Статус |
|-----------|--------|--------|
| **HIGH** | E1-E5, C1-C2, D2-D5, A3, A6, A9 | DONE |
| **MEDIUM** | D1, A5 | DONE |
| **LOW (документировано)** | A1, A2, A7, A8, B1-B3 | Для будущей реализации |

---

## Выполненные изменения

Все задачи с приоритетами HIGH и MEDIUM выполнены в рамках этой сессии.
Задачи LOW документированы в этом файле для будущей реализации.
