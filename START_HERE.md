# ⚡ Быстрый запуск Voice Interviewer Agent

## Шаг 1: Установка зависимостей

```bash
# Клонируйте файлы в вашу директорию
# Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# Установите зависимости
pip install -r requirements.txt
```

## Шаг 2: Создайте .env файл

Создайте файл `.env` в корне проекта:

```env
# Azure OpenAI (обязательно)
AZURE_OPENAI_API_KEY=ваш_ключ
AZURE_OPENAI_ENDPOINT=https://ваш-ресурс.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4-realtime-preview
AZURE_OPENAI_API_VERSION=2024-10-01-preview

# DeepSeek (обязательно)
DEEPSEEK_API_KEY=ваш_ключ
DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-reasoner

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

# LiveKit (опционально, для будущих версий)
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
LIVEKIT_URL=

# Общее
ENVIRONMENT=development
LOG_LEVEL=INFO
MAX_CLARIFICATIONS_PER_QUESTION=3
MIN_ANSWER_LENGTH_WORDS=15
```

## Шаг 3: Запустите инфраструктуру

```bash
# Запустите Redis и PostgreSQL через Docker
docker-compose up -d

# Проверьте статус
docker-compose ps
```

Вывод должен быть:
```
NAME                   SERVICE     STATUS
voice-interviewer-postgres   postgres    running
voice-interviewer-redis      redis       running
```

## Шаг 4: Запустите агента!

```bash
python main.py
```

## Что произойдёт:

1. **Приветственный экран** с выбором паттерна
2. **Подключение к Redis и PostgreSQL**
3. **Выбор паттерна:**
   - 1 = INTERACTION (для агентов, работающих с клиентами)
   - 2 = MANAGEMENT (для агентов, работающих с сотрудниками)
4. **Начало интервью** с визуализацией прогресса
5. **Сохранение анкеты** в базу данных

## Альтернатива: Демо-режим (без голоса)

Если у вас нет Azure OpenAI API, запустите демо:

```bash
python demo.py
```

Демо симулирует работу агента в текстовом режиме.

## Возобновление прерванного интервью

```bash
python main.py resume <session_id>
```

где `<session_id>` - ID сессии, которая была показана при паузе.

## Проверка здоровья системы

```bash
python healthcheck.py
```

Проверит подключение к Redis, PostgreSQL и покажет статистику.

## Что дальше?

1. ✅ Заполните `.env` с вашими ключами API
2. ✅ Запустите `docker-compose up -d`
3. ✅ Запустите `python main.py`
4. ✅ Выберите паттерн (1 или 2)
5. ✅ Отвечайте на вопросы агента
6. ✅ Получите заполненную анкету в PostgreSQL!

---

## FAQ

**Q: У меня нет Azure OpenAI API ключа**
A: Используйте `demo.py` для текстового режима или зарегистрируйтесь в Azure.

**Q: Redis connection failed**
A: Проверьте `docker-compose ps` и перезапустите `docker-compose restart redis`

**Q: Где хранятся анкеты?**
A: В PostgreSQL в таблице `anketas`. Посмотреть можно:
```bash
docker exec -it voice-interviewer-postgres psql -U interviewer_user -d voice_interviewer
SELECT * FROM anketas;
```

**Q: Можно ли использовать без Docker?**
A: Да, установите Redis и PostgreSQL локально и обновите `.env` соответственно.

---

🎉 **Успехов с голосовым агентом!**
