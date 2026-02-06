# Тестирование

Система тестирования Hanc.AI Voice Consultant: юнит-тесты и LLM-симуляция.

## Обзор

| Тип | Количество | Инструмент |
| --- | --- | --- |
| Юнит-тесты | 252 | pytest |
| Сценарии симуляции | 12 | agent_client_simulator |
| Pipeline Test → Review | 1 | run_pipeline.py |

## Юнит-тесты (pytest)

### Запуск

```bash
# Все тесты
pytest

# С подробным выводом
pytest -v

# Конкретный модуль
pytest tests/unit/test_api_server.py

# По маркеру
pytest -m "not slow"
```

### Структура

```text
tests/
├── __init__.py
├── conftest.py
├── fixtures/
│   └── __init__.py
├── unit/
│   ├── __init__.py
│   ├── test_api_server.py       # FastAPI server tests (35 tests: sessions, anketa, confirm, end, pages, lifecycle flows)
│   ├── test_cli_interface.py    # CLI interface tests (InterviewCLI)
│   ├── test_interview_context.py # InterviewContext model tests
│   ├── test_models.py           # Core models (InterviewPattern, CompletedAnketa, QuestionResponse, etc.)
│   ├── test_notifications.py    # NotificationManager tests
│   ├── test_postgres_storage.py # PostgreSQL storage (AnketaDB, InterviewSessionDB, statistics)
│   ├── test_redis_storage.py    # Redis storage (save/load context, TTL)
│   ├── test_session_manager.py  # SessionManager (SQLite CRUD, links, statistics)
│   └── test_session_models.py   # ConsultationSession model tests
└── scenarios/                   # YAML-сценарии для симуляции (12 файлов)
```

## LLM-симуляция консультаций

### Принцип работы

SimulatedClient — это LLM (DeepSeek), который играет роль клиента по YAML-сценарию. ConsultationTester запускает полный цикл консультации (4 фазы), затем TestValidator проверяет результаты.

### Доступные сценарии (12)

| Сценарий | Отрасль | Описание |
| --- | --- | --- |
| auto_service | Автосервис | Базовый B2B-клиент |
| auto_service_skeptic | Автосервис | Скептически настроенный клиент |
| beauty_salon_glamour | Салон красоты | B2C, wellness |
| logistics_company | Логистика | Грузоперевозки |
| medical_center | Медицинский центр | Запись на приём |
| medical_clinic | Клиника | Здравоохранение |
| online_school | Онлайн-школа | Образование |
| real_estate_agency | Недвижимость | Агентство |
| realestate_domstroy | Недвижимость | Застройщик |
| restaurant_delivery | Ресторан + доставка | HoReCa |
| restaurant_italiano | Ресторан | Итальянская кухня |
| vitalbox | Франшиза wellness | Квалификация партнёров |

### Запуск симуляции

```bash
# Список сценариев
python scripts/run_test.py --list

# Запуск одного сценария
python scripts/run_test.py auto_service

# Тихий режим
python scripts/run_test.py auto_service --quiet

# Без сохранения отчётов
python scripts/run_test.py auto_service --no-save

# С документами клиента
python scripts/run_test.py logistics_company --input-dir input/test_logistics/
```

### Pipeline: Test → Review

```bash
# Полный pipeline (тест + ревью анкеты в редакторе)
python scripts/run_pipeline.py auto_service

# Автоматическое одобрение
python scripts/run_pipeline.py auto_service --auto-approve

# Без этапа ревью
python scripts/run_pipeline.py auto_service --skip-review

# С указанием выходной папки
python scripts/run_pipeline.py auto_service --output-dir output/final
```

### Валидация результатов (TestValidator)

6 проверок после каждой симуляции:

| Проверка | Описание |
| --- | --- |
| completeness | Обязательные поля анкеты заполнены |
| data_quality | Валидность значений (не мусор, не диалоговые маркеры) |
| scenario_match | Данные соответствуют YAML-сценарию |
| phases | Все 4 фазы пройдены |
| no_loops | Нет зацикливания в диалоге |
| metrics | Количество ходов и время в допустимых пределах |

### Результаты

TestResult содержит:

- `status` — completed / failed / interrupted
- `duration_seconds` — длительность
- `turn_count` — количество ходов диалога
- `phases_completed` — пройденные фазы
- `anketa` — собранные данные
- `final_anketa` — извлечённая FinalAnketa v2.0
- `validation` — результаты 6 проверок
- `errors` — ошибки

### Отчёты

TestReporter генерирует:

- **Console** — Rich-вывод с таблицами и прогрессом
- **JSON** — `output/tests/{scenario}_{timestamp}.json`
- **Markdown** — `output/tests/{scenario}_{timestamp}.md`

## Создание нового сценария

### 1. Скопируйте шаблон

```bash
cp tests/scenarios/_template.yaml tests/scenarios/my_company.yaml
```

### 2. Заполните данные

```yaml
persona:
  name: "Иван Иванов"
  role: "Директор"
  company: "ООО Ромашка"
  industry: "Розничная торговля"
  communication_style: "professional"   # professional / casual / brief / detailed
  knowledge_level: "medium"             # low / medium / high

  pain_points:
    - "Операторы не справляются с потоком звонков"
    - "Теряем клиентов из-за долгого ожидания"

  goals:
    - "Автоматизировать ответы на типовые вопросы"

  constraints:
    - "Бюджет до 300 000 рублей"

  target_functions:
    - "Ответы на FAQ"
    - "Приём заказов"

  integrations:
    - "1С - синхронизация заказов"

  background: |
    Компания занимается продажей стройматериалов.
    Ежедневно поступает 200-300 звонков.

expected_results:
  required_fields:
    - company_name
    - industry
  expected_functions:
    - "FAQ"
  expected_integrations:
    - "1С"
```

### 3. Запустите

```bash
python scripts/run_test.py my_company
```

## Стоимость и производительность

Один тест использует ~50-100 вызовов DeepSeek API:

- SimulatedClient: ~20-30 ответов
- ConsultantInterviewer: ~30-50 ответов
- Анализ и извлечение: ~10-20 вызовов

Примерная стоимость: $0.05-0.15 за тест.

## Отладка

### Verbose режим

По умолчанию включён. Показывает промпты, ответы клиента, смену фаз.

### Логи

При запуске тестов логи пишутся в `logs/`:

- `logs/anketa.log` — извлечение анкеты
- `logs/deepseek.log` — вызовы LLM API
- `logs/errors.log` — все ошибки

Подробнее: [LOGGING.md](LOGGING.md)

### Частые проблемы

| Проблема | Решение |
| --- | --- |
| `DeepSeek API error status=400` | Проверьте DEEPSEEK_API_KEY и баланс |
| Тест зависает | Используйте `max_turns_per_phase` для ограничения |
| Пустая анкета | Проверьте что dialogue_history не пуст |
| Validation failed | Посмотрите `result.validation["errors"]` |

## E2E тесты голосового агента

E2E тесты для Voice Agent используют Puppeteer с fake audio device Chrome.

### Установка Puppeteer

```bash
npm install puppeteer
```

### Запуск E2E теста

```bash
# Требуется работающий сервер и агент
python scripts/run_server.py &
python scripts/run_voice_agent.py dev &

# Запуск теста
node tests/e2e_voice_test.js
```

### Что тестируется

| Этап | Проверка |
| --- | --- |
| Browser launch | Запуск Chrome с fake audio |
| Page load | Загрузка UI |
| LiveKit connection | Подключение к комнате |
| Audio track published | Публикация микрофона |
| Agent greeting | Приветствие агента |
| Track subscribed by agent | Подписка агента на аудио |
| Agent received audio | VAD обнаружил речь |
| STT transcription | Транскрипция речи |
| Agent response to user | Ответ агента |
| Conversation in UI | Сообщения в интерфейсе |

### Fake Audio

Тест использует WAV-файл вместо микрофона:

```javascript
browser = await puppeteer.launch({
    args: [
        '--use-fake-device-for-media-stream',
        '--use-fake-ui-for-media-stream',
        `--use-file-for-fake-audio-capture=${TEST_AUDIO_FILE}`,
        '--autoplay-policy=no-user-gesture-required',
    ],
});
```

### Проверка логов агента

Тест читает `/tmp/agent_entrypoint.log` для проверки:

```javascript
const agentLog = execSync('cat /tmp/agent_entrypoint.log').toString();

// Проверка подписки на трек
const trackSubscribed = agentLog.includes('Track subscribed');

// Проверка VAD
const userSpeaking = agentLog.includes('USER STATE: listening -> speaking');

// Проверка транскрипции
const userSpeechMatch = agentLog.match(/USER SPEECH: '([^']+)'/);
```

### Создание тестового аудио

```bash
# Генерация речи через macOS
say -v Yuri "Привет, меня зовут Иван" -o test.aiff
ffmpeg -i test.aiff -ar 48000 -ac 1 tests/fixtures/test_speech_ru.wav -y
```

### Отладка E2E тестов

Для визуальной отладки запустите headful режим:

```javascript
browser = await puppeteer.launch({
    headless: false,  // Видимый браузер
    // ...
});
```
