# Быстрый запуск Voice Interviewer Agent

## Шаг 1: Установка зависимостей

```bash
# Клонируйте репозиторий
git clone <repo-url>
cd voice-interviewer-agent

# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# Установите зависимости
pip install -r requirements.txt
```

## Шаг 2: Создайте .env файл

```bash
cp .env.example .env
```

Заполните минимум:

```env
# DeepSeek (обязательно)
DEEPSEEK_API_KEY=your_key
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_SESSION_TTL=7200

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=voice_interviewer
POSTGRES_USER=interviewer_user
POSTGRES_PASSWORD=secure_password_123

# Общее
ENVIRONMENT=development
LOG_LEVEL=INFO
```

## Шаг 3: Запустите инфраструктуру

```bash
# Запустите Redis и PostgreSQL через Docker
docker-compose -f config/docker-compose.yml up -d

# Проверьте статус
docker-compose -f config/docker-compose.yml ps
```

Вывод должен быть:

```
NAME                         SERVICE     STATUS
voice-interviewer-postgres   postgres    running
voice-interviewer-redis      redis       running
```

## Шаг 4: Запустите агента

```bash
python3 scripts/demo.py
```

## Что произойдёт

1. **Выбор режима:**
   - MAXIMUM — полноценное AI-интервью с DeepSeek
   - MOCK — симуляция без API

2. **Выбор паттерна:**
   - INTERACTION — для агентов, работающих с клиентами
   - MANAGEMENT — для агентов, работающих с сотрудниками

3. **Maximum Interview Mode (три фазы):**
   - **DISCOVERY** — свободный диалог о бизнесе
   - **STRUCTURED** — целенаправленный сбор данных
   - **SYNTHESIS** — генерация полной анкеты

4. **Сохранение анкеты** в JSON, Markdown и PostgreSQL

## Проверка здоровья системы

```bash
python3 scripts/healthcheck.py
```

Проверит подключение к Redis, PostgreSQL и DeepSeek API.

## FAQ

**Q: У меня нет DeepSeek API ключа**

A: Используйте MOCK режим в `scripts/demo.py` или зарегистрируйтесь на [platform.deepseek.com](https://platform.deepseek.com).

**Q: Redis connection failed**

A: Проверьте `docker-compose ps` и перезапустите:

```bash
docker-compose -f config/docker-compose.yml restart redis
```

**Q: Где хранятся анкеты?**

A:
- **Файлы:** `output/anketa_*.json` и `output/anketa_*.md`
- **База данных:** PostgreSQL таблица `anketas`

```bash
docker-compose -f config/docker-compose.yml exec postgres psql -U interviewer_user -d voice_interviewer -c "SELECT * FROM anketas;"
```

**Q: Можно ли использовать без Docker?**

A: Да, установите Redis и PostgreSQL локально и обновите `.env`.

---

## Дальше

- Полная документация: [README.md](../README.md)
- Обзор проекта: [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
- Краткое руководство: [QUICKSTART.md](QUICKSTART.md)
- Пример анкеты: [example_anketa.md](example_anketa.md)

---

**Успехов с Voice Interviewer Agent!**
