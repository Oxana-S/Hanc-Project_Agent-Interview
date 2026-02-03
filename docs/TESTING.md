# Тестирование ConsultantInterviewer

Фреймворк для автоматического тестирования AI-консультанта через симуляцию клиентов.

## Обзор

Система позволяет:
- Симулировать реального клиента с помощью LLM
- Прогонять полный цикл консультации (4 фазы)
- Проверять заполнение анкеты
- Генерировать отчёты в JSON и Markdown

## Быстрый старт

```bash
# Посмотреть доступные сценарии
python scripts/run_test.py --list

# Запустить тест
python scripts/run_test.py vitalbox

# Запустить без подробного вывода
python scripts/run_test.py vitalbox --quiet

# Не сохранять отчёты в файлы
python scripts/run_test.py vitalbox --no-save
```

## Структура файлов

```
src/
├── agent_client_simulator/          # Фреймворк симуляции
│   ├── __init__.py
│   ├── client.py               # SimulatedClient - AI-клиент
│   ├── runner.py               # ConsultationTester - запуск тестов
│   ├── reporter.py             # TestReporter - генерация отчётов
│   └── validator.py            # TestValidator - валидация результатов

tests/
└── scenarios/                  # Сценарии тестирования
    ├── _template.yaml          # Шаблон для новых сценариев
    └── vitalbox.yaml           # Пример: франшиза Vitalbox

scripts/
├── run_test.py                 # CLI для запуска тестов
└── run_pipeline.py             # Интегрированный pipeline (Test → Review)

output/
└── tests/                      # Сохранённые отчёты
    ├── vitalbox_20260203_001234.json
    └── vitalbox_20260203_001234.md
```

## Создание сценария

### 1. Скопируйте шаблон

```bash
cp tests/scenarios/_template.yaml tests/scenarios/my_company.yaml
```

### 2. Заполните данные клиента

```yaml
# tests/scenarios/my_company.yaml

persona:
  # === ОСНОВНАЯ ИНФОРМАЦИЯ ===
  name: "Иван Иванов"              # Имя контактного лица
  role: "Директор"                  # Должность
  company: "ООО Ромашка"           # Название компании
  industry: "Розничная торговля"    # Отрасль
  website: "https://romashka.ru"   # Сайт (опционально)

  # === СТИЛЬ ОБЩЕНИЯ ===
  # professional - деловой, вежливый
  # casual - дружелюбный, неформальный
  # brief - короткие ответы
  # detailed - развёрнутые ответы
  communication_style: "professional"

  # === УРОВЕНЬ ТЕХНИЧЕСКИХ ЗНАНИЙ ===
  # low - не разбирается в AI/IT
  # medium - общее понимание
  # high - хорошо понимает технологии
  knowledge_level: "medium"

  # === КОНТЕКСТ БИЗНЕСА ===
  pain_points:
    - "Операторы не справляются с потоком звонков"
    - "Теряем клиентов из-за долгого ожидания"
    - "Много рутинных вопросов отнимают время"

  goals:
    - "Автоматизировать ответы на типовые вопросы"
    - "Сократить время ожидания клиентов"
    - "Разгрузить операторов для сложных задач"

  constraints:
    - "Бюджет до 300 000 рублей"
    - "Нужна интеграция с 1С"

  # === ТРЕБОВАНИЯ К АГЕНТУ ===
  target_functions:
    - "Ответы на FAQ"
    - "Приём заказов"
    - "Проверка статуса заказа"

  integrations:
    - "1С - синхронизация заказов"
    - "Телефония - входящие звонки"

  # === ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ ===
  background: |
    Компания занимается продажей строительных материалов.
    Ежедневно поступает 200-300 звонков.
    Основные вопросы: наличие товара, цены, доставка.

  special_instructions: |
    При ответах учитывай:
    - Клиент консервативен, не любит новые технологии
    - Важна стоимость, а не "модность" решения

# === КРИТЕРИИ УСПЕХА ТЕСТА ===
expected_results:
  required_fields:
    - company_name
    - industry
    - agent_goal

  expected_functions:
    - "FAQ"
    - "заказ"

  expected_integrations:
    - "1С"
```

### 3. Запустите тест

```bash
python scripts/run_test.py my_company
```

## Компоненты фреймворка

### SimulatedClient

AI-клиент, который генерирует реалистичные ответы на основе персоны.

```python
from src.agent_client_simulator.client import SimulatedClient

# Загрузка из YAML
client = SimulatedClient.from_yaml("tests/scenarios/vitalbox.yaml")

# Генерация ответа
response = await client.respond(
    consultant_message="Расскажите о вашей компании",
    phase="discovery"
)
```

**Параметры персоны:**

| Параметр | Описание |
|----------|----------|
| `name` | Имя контактного лица |
| `role` | Должность |
| `company` | Название компании |
| `industry` | Отрасль бизнеса |
| `website` | URL сайта (для Research Engine) |
| `communication_style` | Стиль общения: professional, casual, brief, detailed |
| `knowledge_level` | Техническая грамотность: low, medium, high |
| `pain_points` | Список болевых точек бизнеса |
| `goals` | Цели автоматизации |
| `constraints` | Ограничения (бюджет, сроки, технические) |
| `target_functions` | Желаемые функции агента |
| `integrations` | Нужные интеграции |
| `background` | Дополнительный контекст о бизнесе |
| `special_instructions` | Особые инструкции для симуляции |

### ConsultationTester

Запускает полную симуляцию консультации.

```python
from src.agent_client_simulator.runner import ConsultationTester, run_test_scenario

# Простой запуск
result = await run_test_scenario("tests/scenarios/vitalbox.yaml")

# Расширенная настройка
from src.agent_client_simulator.client import SimulatedClient
from src.models import InterviewPattern

client = SimulatedClient.from_yaml("tests/scenarios/vitalbox.yaml")
tester = ConsultationTester(
    client=client,
    pattern=InterviewPattern.INTERACTION,
    max_turns_per_phase=20,
    verbose=True
)
result = await tester.run(scenario_name="vitalbox")
```

### TestReporter

Генерирует отчёты о результатах теста.

```python
from src.agent_client_simulator.reporter import TestReporter

reporter = TestReporter(output_dir="output/tests")

# Вывод в консоль
reporter.report_to_console(result)

# Сохранение в файлы
reporter.save_json(result)      # -> output/tests/vitalbox_20260203.json
reporter.save_markdown(result)  # -> output/tests/vitalbox_20260203.md

# Всё сразу
reporter.full_report(result, save_files=True)
```

## Результаты теста

### TestResult

```python
@dataclass
class TestResult:
    scenario_name: str           # Имя сценария
    status: str                  # "completed", "failed", "interrupted"
    duration_seconds: float      # Длительность в секундах
    phases_completed: List[str]  # Пройденные фазы
    current_phase: str           # Текущая фаза
    anketa: Dict[str, Any]       # Заполненная анкета
    business_analysis: Dict      # Результат анализа бизнеса
    proposed_solution: Dict      # Предложенное решение
    dialogue_history: List       # История диалога
    turn_count: int              # Количество ходов
    errors: List[str]            # Ошибки
```

### Пример вывода

```
══════════════════════════════════════════════════
РЕЗУЛЬТАТЫ ТЕСТА
══════════════════════════════════════════════════
Статус: completed
Длительность: 482.0 сек
Ходов: 18
Фазы: discovery, analysis, proposal, refinement

Заполненные поля анкеты:
  • company_name: Vitalbox
  • industry: Wellness / Массажные услуги
  • specialization: Сеть массажных боксов...
  • agent_purpose: Квалификация франчайзи...
  ...

Заполнено: 15 из 15 (100%)
```

## Фазы консультации

Тест проходит через все 4 фазы:

| Фаза | Описание | Что проверяется |
|------|----------|-----------------|
| **DISCOVERY** | Знакомство с бизнесом | Сбор базовой информации |
| **ANALYSIS** | Анализ и исследование | Формирование анализа, валидация |
| **PROPOSAL** | Предложение решения | Структура предложения |
| **REFINEMENT** | Заполнение анкеты | Полнота данных |

## Отладка

### Verbose режим

По умолчанию включён. Показывает:
- Какие промпты получает mock
- Какой тип ответа генерируется
- Ответы симулированного клиента

### Логи DeepSeek

Если возникают ошибки API:
```
DeepSeek API error status=400
```

Проверьте:
1. Наличие `DEEPSEEK_API_KEY` в `.env`
2. Баланс аккаунта DeepSeek
3. Корректность формата сообщений

### Таймауты

Если тест зависает, возможно:
- LLM долго отвечает (сеть, нагрузка)
- Бесконечный цикл в логике фаз

Используйте `max_turns_per_phase` для ограничения.

## Примеры сценариев

### B2B: IT-услуги

```yaml
persona:
  name: "Сергей Козлов"
  role: "CTO"
  company: "TechCorp"
  industry: "IT-услуги"
  communication_style: "detailed"
  knowledge_level: "high"
  pain_points:
    - "Много рутинных запросов в техподдержку"
  target_functions:
    - "Первая линия поддержки"
    - "Создание тикетов в Jira"
```

### B2C: Медицина

```yaml
persona:
  name: "Елена Смирнова"
  role: "Главный врач"
  company: "Клиника Здоровье"
  industry: "Медицина"
  communication_style: "professional"
  knowledge_level: "low"
  pain_points:
    - "Пациенты не дозваниваются"
    - "Администраторы перегружены"
  target_functions:
    - "Запись на приём"
    - "Напоминания о визитах"
```

### Франшиза

```yaml
persona:
  name: "Алексей Петров"
  role: "Руководитель отдела развития"
  company: "Vitalbox"
  industry: "Wellness"
  pain_points:
    - "Теряем лидов из-за долгого ответа"
  target_functions:
    - "Квалификация партнёров"
    - "Ответы на FAQ по франшизе"
```

## FAQ

### Сколько стоит один тест?

Один полный тест использует ~50-100 вызовов DeepSeek API:
- SimulatedClient: ~20-30 ответов клиента
- ConsultantInterviewer: ~30-50 ответов консультанта
- Анализ и предложение: ~10-20 вызовов

Примерная стоимость: $0.05-0.15 за тест.

### Как ускорить тесты?

1. Уменьшите `discovery_max_turns` в ConsultantInterviewer
2. Используйте `--quiet` для минимального вывода
3. Упростите `background` в сценарии

### Как добавить свои проверки?

Расширьте `expected_results` в YAML:

```yaml
expected_results:
  required_fields:
    - company_name
    - agent_goal

  expected_functions:
    - "квалификация"

  expected_integrations:
    - "CRM"
```

И добавьте валидацию в `TestReporter.report_to_console()`.
