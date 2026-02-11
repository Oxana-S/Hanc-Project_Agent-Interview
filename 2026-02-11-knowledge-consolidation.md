# План: Консолидация контентных данных в единую папку `knowledge/`

## Контекст

Сейчас все контентные данные проекта (база знаний по индустриям, AI-промпты, локализация, синонимы и пр.) разбросаны по 5+ директориям. Это усложняет навигацию и поддержку. Цель — собрать всё в единый "источник истины" `knowledge/` в корне проекта.

**Статус**: ДРАФТ. Реализация начнётся после того, как будут внесены все текущие изменения в проект.

**Решение по БД**: На текущем масштабе (~1000 YAML файлов) база данных не даст выигрыша. YAML + Git + кэширование — правильная архитектура для проекта, где контент редактируется разработчиками. БД имеет смысл рассмотреть, если появится админ-панель для менеджеров или объём вырастет на порядок.

---

## 1. Инвентаризация текущих источников данных

### 1.1 `config/industries/` — Профили индустрий (970 файлов)

| Что | Путь | Кол-во |
|-----|------|--------|
| Мастер-индекс | `config/industries/_index.yaml` | 1 |
| Метаданные стран | `config/industries/_countries.yaml` | 1 |
| Корневые профили | `config/industries/{industry}.yaml` | 8 |
| Базовые шаблоны | `config/industries/_base/*.yaml` | 40 |
| Регион EU | `config/industries/eu/**/*.yaml` | 440 |
| Регион NA | `config/industries/na/**/*.yaml` | 80 |
| Регион LATAM | `config/industries/latam/**/*.yaml` | 120 |
| Регион MENA | `config/industries/mena/**/*.yaml` | 120 |
| Регион SEA | `config/industries/sea/**/*.yaml` | 120 |
| Регион RU | `config/industries/ru/**/*.yaml` | 40 |

**Загрузчик**: `src/knowledge/loader.py` → `IndustryProfileLoader`
**Путь в коде**: `Path(__file__).parent.parent.parent / "config" / "industries"`

### 1.2 `config/synonyms/` — Словари синонимов (3 файла)

| Файл | Назначение |
|------|-----------|
| `base.yaml` | Универсальные технические термины (CRM, PBX и т.д.) |
| `ru.yaml` | Русскоязычные синонимы |
| `en.yaml` | Англоязычные синонимы |

**Загрузчик**: `src/config/synonym_loader.py` → `SynonymLoader`
**Путь в коде**: `Path(__file__).parent.parent.parent / "config" / "synonyms"`

### 1.3 `config/consultant/` — Шаблон KB-контекста (1 файл)

| Файл | Назначение |
|------|-----------|
| `kb_context.yaml` | Определяет какие данные из профиля индустрии подставляются в промпты на каждой фазе |

**Загрузчик**: `src/knowledge/context_builder.py` → `KBContextBuilder`

### 1.4 `config/personas/` — Персоны для симулятора (2 файла)

| Файл | Назначение |
|------|-----------|
| `traits.yaml` | Черты характера персон (brief, verbose, formal, casual и т.д.) |
| `prompts.yaml` | Промпт-шаблоны для генерации персон |

**Загрузчик**: `src/agent_client_simulator/`

### 1.5 `prompts/` — AI-промпты (11 файлов)

```
prompts/
├── anketa/
│   ├── expert.yaml          # Генерация FAQ, возражений, KPI
│   └── extract.yaml         # Извлечение структурированных данных
├── consultant/
│   ├── discovery.yaml       # Фаза знакомства с бизнесом
│   ├── analysis.yaml        # Фаза анализа
│   ├── proposal.yaml        # Фаза предложения
│   └── refinement.yaml      # Фаза уточнения
├── llm/
│   ├── analyze_answer.yaml  # Анализ полноты ответа
│   ├── complete_anketa.yaml # Дозаполнение анкеты
│   └── generation.yaml      # Генерация диалогов
└── voice/
    ├── consultant.yaml      # Системный промпт голосового агента (26KB)
    └── review.yaml          # Ревью анкеты голосом
```

**Загрузчик**: `src/config/prompt_loader.py` → `PromptLoader`
**Путь в коде**: `Path(__file__).parent.parent.parent / "prompts"`

### 1.6 `locales/` — Локализация UI (2 файла)

```
locales/
├── ru/ui.yaml    # Русский
└── en/ui.yaml    # English
```

**Загрузчик**: `src/config/locale_loader.py` → `LocaleLoader`
**Путь в коде**: `Path(__file__).parent.parent.parent / "locales"`

### 1.7 `tests/scenarios/` — Тестовые сценарии (13 файлов)

```
tests/scenarios/
├── _template.yaml
├── auto_service.yaml
├── auto_service_skeptic.yaml
├── beauty_salon_glamour.yaml
├── logistics_company.yaml
├── medical_center.yaml
├── medical_clinic.yaml
├── online_school.yaml
├── real_estate_agency.yaml
├── realestate_domstroy.yaml
├── restaurant_delivery.yaml
├── restaurant_italiano.yaml
└── vitalbox.yaml
```

**Загрузчик**: `scripts/run_test.py` → `SCENARIOS_DIR`
**Путь в коде**: `Path(__file__).parent.parent / "tests" / "scenarios"`

### 1.8 Что НЕ переносим (системные конфиги)

| Файл | Причина |
|------|---------|
| `config/docker-compose.yml` | Инфраструктура Docker |
| `config/init_db.sql` | Инициализация БД |
| `config/nginx/` | Конфигурация nginx |
| `config/notifications.yaml` | Настройки уведомлений (email/webhook) |

---

## 2. Целевая структура `knowledge/`

```
knowledge/
├── industries/                    # Из config/industries/
│   ├── _index.yaml
│   ├── _countries.yaml
│   ├── _base/                     # 40 базовых шаблонов
│   │   ├── automotive.yaml
│   │   ├── medical.yaml
│   │   └── ...
│   ├── automotive.yaml            # 8 корневых профилей
│   ├── medical.yaml
│   ├── ...
│   ├── eu/                        # Региональные профили
│   ├── na/
│   ├── latam/
│   ├── mena/
│   ├── sea/
│   └── ru/
│
├── synonyms/                      # Из config/synonyms/
│   ├── base.yaml
│   ├── ru.yaml
│   └── en.yaml
│
├── prompts/                       # Из prompts/
│   ├── anketa/
│   │   ├── expert.yaml
│   │   └── extract.yaml
│   ├── consultant/
│   │   ├── discovery.yaml
│   │   ├── analysis.yaml
│   │   ├── proposal.yaml
│   │   └── refinement.yaml
│   ├── llm/
│   │   ├── analyze_answer.yaml
│   │   ├── complete_anketa.yaml
│   │   └── generation.yaml
│   └── voice/
│       ├── consultant.yaml
│       └── review.yaml
│
├── locales/                       # Из locales/
│   ├── ru/
│   │   └── ui.yaml
│   └── en/
│       └── ui.yaml
│
├── consultant/                    # Из config/consultant/
│   └── kb_context.yaml
│
├── personas/                      # Из config/personas/
│   ├── traits.yaml
│   └── prompts.yaml
│
└── scenarios/                     # Из tests/scenarios/
    ├── _template.yaml
    ├── auto_service.yaml
    ├── auto_service_skeptic.yaml
    ├── beauty_salon_glamour.yaml
    ├── logistics_company.yaml
    ├── medical_center.yaml
    ├── medical_clinic.yaml
    ├── online_school.yaml
    ├── real_estate_agency.yaml
    ├── realestate_domstroy.yaml
    ├── restaurant_delivery.yaml
    ├── restaurant_italiano.yaml
    └── vitalbox.yaml
```

**Итого**: ~1000 YAML файлов в единой структуре.

---

## 3. Драфт плана миграции (для будущей реализации)

### Этап 1: Перенос файлов
1. Создать директорию `knowledge/` со всеми поддиректориями
2. Скопировать файлы (НЕ перемещать — чтобы старый код продолжал работать):
   - `config/industries/` → `knowledge/industries/`
   - `config/synonyms/` → `knowledge/synonyms/`
   - `config/consultant/` → `knowledge/consultant/`
   - `config/personas/` → `knowledge/personas/`
   - `prompts/` → `knowledge/prompts/`
   - `locales/` → `knowledge/locales/`
   - `tests/scenarios/` → `knowledge/scenarios/`

### Этап 2: Обновление загрузчиков (Python-код)
Файлы, которые потребуют изменений:

| Файл | Что менять |
|------|-----------|
| `src/config/prompt_loader.py` | `"prompts"` → `"knowledge" / "prompts"` |
| `src/config/locale_loader.py` | `"locales"` → `"knowledge" / "locales"` |
| `src/config/synonym_loader.py` | `"config" / "synonyms"` → `"knowledge" / "synonyms"` |
| `src/knowledge/loader.py` | `"config" / "industries"` → `"knowledge" / "industries"` |
| `src/knowledge/context_builder.py` | Путь к `kb_context.yaml` → `"knowledge" / "consultant"` |
| `scripts/run_test.py` | `"tests" / "scenarios"` → `"knowledge" / "scenarios"` |
| `src/agent_client_simulator/` | Ссылки на сценарии и персоны |

### Этап 3: Проверка
1. Запустить юнит-тесты: `pytest tests/unit/`
2. Проверить загрузку промптов, локалей, синонимов, индустрий
3. Проверить что голосовой агент и консультант стартуют
4. Запустить тестовый сценарий: `python scripts/run_test.py auto_service`

### Этап 4: Удаление старых директорий
После подтверждения работоспособности:
- Удалить `prompts/` (перенесена в `knowledge/prompts/`)
- Удалить `locales/` (перенесена в `knowledge/locales/`)
- Из `config/` удалить `industries/`, `synonyms/`, `consultant/`, `personas/`
- Из `tests/scenarios/` удалить перенесённые файлы
- Обновить `.gitignore`, `Dockerfile`, `docker-compose.yml` если они ссылаются на старые пути

### Этап 5: Обновить документацию
- `README.md` — описание новой структуры
- `CLAUDE.md` — если есть, указать `knowledge/` как источник истины
- `docs/ARCHITECTURE.md` — обновить схему проекта
