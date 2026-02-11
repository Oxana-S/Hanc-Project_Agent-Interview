# Деплой

Инструкции по развёртыванию Hanc.AI Voice Consultant в production-среде.

## Архитектура развёртывания

```
┌─────────────────────────────────────────────────────────────┐
│                        Production                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│   │   Nginx     │───▶│  FastAPI    │───▶│   Redis     │   │
│   │   (proxy)   │    │  (uvicorn)  │    │  (sessions) │   │
│   └─────────────┘    └─────────────┘    └─────────────┘   │
│          │                  │                  │           │
│          │                  │                  ▼           │
│          │                  │           ┌─────────────┐   │
│          │                  └──────────▶│ PostgreSQL  │   │
│          │                              │  (anketas)  │   │
│          │                              └─────────────┘   │
│          ▼                                                 │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│   │  LiveKit    │◀──▶│   Voice     │───▶│   Azure     │   │
│   │   Cloud     │    │   Agent     │    │   OpenAI    │   │
│   └─────────────┘    └─────────────┘    └─────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Варианты развёртывания

| Вариант | Описание | Файл | Рекомендуется для |
|---------|----------|------|-------------------|
| Docker Compose (Dev) | Redis + PostgreSQL + отладка | `config/docker-compose.yml` | Разработка |
| Docker Compose (Prod) | Nginx + Certbot + Web + Agent + Redis + PostgreSQL | `docker-compose.yml` (корень) | Staging, Production |
| Kubernetes | Полноценный оркестратор | — | Большие нагрузки |
| Managed Services | LiveKit Cloud + Azure + RDS | — | Минимум ops |

## Docker Compose (Development/Staging)

### 1. Запуск инфраструктуры

```bash
# Основные сервисы (Redis + PostgreSQL)
docker compose -f config/docker-compose.yml up -d

# С инструментами отладки (pgAdmin, Redis Commander)
docker compose -f config/docker-compose.yml --profile tools up -d
```

### 2. Проверка состояния

```bash
docker compose -f config/docker-compose.yml ps
```

Ожидаемый вывод:

```
NAME                          STATUS           PORTS
voice_interviewer_postgres    Up (healthy)     0.0.0.0:5432->5432/tcp
voice_interviewer_redis       Up (healthy)     0.0.0.0:6379->6379/tcp
```

### 3. Доступ к инструментам

| Инструмент | URL | Логин |
|------------|-----|-------|
| pgAdmin | http://localhost:5050 | admin@example.com / admin |
| Redis Commander | http://localhost:8081 | — |

### 4. Остановка

```bash
docker compose -f config/docker-compose.yml down

# С удалением volumes (очистка данных)
docker compose -f config/docker-compose.yml down -v
```

## Docker Compose (Production)

Корневой `docker-compose.yml` поднимает **всё приложение целиком** — 6 сервисов в единой сети `hanc_network`:

| Сервис | Контейнер | Описание |
|--------|-----------|----------|
| `nginx` | `hanc_nginx` | Reverse proxy, SSL termination (порты 80/443) |
| `certbot` | `hanc_certbot` | Автообновление Let's Encrypt сертификатов (каждые 12ч) |
| `web` | `hanc_web` | FastAPI сервер (внутренний порт 8000) |
| `agent` | `hanc_agent` | Голосовой агент (LiveKit worker) |
| `redis` | `hanc_redis` | Кэш сессий (Redis 7, healthcheck) |
| `postgres` | `hanc_postgres` | Долгосрочное хранение анкет (PostgreSQL 16, healthcheck) |

### 1. Подготовка

```bash
# Заполните .env (обязательно: DOMAIN, POSTGRES_PASSWORD, API ключи)
cp .env.example .env
nano .env
```

Ключевые переменные для production:

```env
DOMAIN=your-domain.com
POSTGRES_PASSWORD=<сгенерированный_пароль_32_символа>
POSTGRES_USER=interviewer_user
POSTGRES_DB=voice_interviewer
```

### 2. Получение SSL-сертификата (первый раз)

```bash
# Инициализация Let's Encrypt
./scripts/init-letsencrypt.sh
```

### 3. Запуск

```bash
# Запуск всех 6 сервисов
docker compose up -d

# Проверка статуса
docker compose ps

# Логи конкретного сервиса
docker compose logs -f web
docker compose logs -f agent
```

Ожидаемый вывод `docker compose ps`:

```
NAME             STATUS           PORTS
hanc_nginx       Up               0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
hanc_certbot     Up
hanc_web         Up
hanc_agent       Up
hanc_redis       Up (healthy)
hanc_postgres    Up (healthy)
```

### 4. Остановка

```bash
# Graceful stop
docker compose down

# С удалением volumes (ВНИМАНИЕ: удалит данные БД!)
docker compose down -v
```

### 5. Volumes

| Volume | Содержимое |
|--------|-----------|
| `app_data` | SQLite база (`data/sessions.db`) |
| `app_logs` | Логи приложения (`logs/`) |
| `app_output` | Результаты консультаций (`output/`) |
| `redis_data` | Redis AOF persistence |
| `postgres_data` | Данные PostgreSQL |

### Отличие от dev-compose

| | `config/docker-compose.yml` (Dev) | `docker-compose.yml` (Prod) |
|---|---|---|
| **Назначение** | Только инфраструктура | Всё приложение |
| **Сервисы** | Redis, PostgreSQL, pgAdmin, Redis Commander | Nginx, Certbot, Web, Agent, Redis, PostgreSQL |
| **Порты наружу** | 6379, 5432, 5050, 8081 | 80, 443 |
| **SSL** | Нет | Let's Encrypt (Nginx + Certbot) |
| **Web/Agent** | Запускаются вручную | Запускаются в контейнерах |
| **Отладка** | pgAdmin, Redis Commander (--profile tools) | Нет |

## Управление процессами (Development)

Для разработки используйте `scripts/hanc.sh`:

```bash
# Запуск
./venv/bin/python scripts/run_server.py          # Терминал 1: Web server
./scripts/hanc.sh start                          # Терминал 2: Voice agent (фоном)

# Мониторинг
./scripts/hanc.sh status                         # Статус всех процессов
./scripts/hanc.sh logs                           # Логи агента (tail -f)

# Перезапуск / остановка
./scripts/hanc.sh restart                        # Перезапуск агента
./scripts/hanc.sh stop                           # Graceful stop
./scripts/hanc.sh kill-all                       # Аварийное завершение
```

Агент защищён от дублирования через PID-файл (`.agent.pid`).

## Production Checklist

### Проверка подключений перед деплоем

**КРИТИЧЕСКИ ВАЖНО:** Перед развёртыванием в production выполните проверку реальных подключений ко всем сервисам.

```bash
# Полная проверка всех сервисов (см. docs/TESTING.md → Этап 5)
# DeepSeek API
python -c "import asyncio; from src.llm.deepseek import DeepSeekClient; asyncio.run(DeepSeekClient().chat([{'role':'user','content':'ping'}])); print('✅ DeepSeek')"

# Redis (требует запущенный контейнер)
python -c "import redis; r=redis.from_url('redis://localhost:6379'); r.ping(); print('✅ Redis')"

# PostgreSQL (требует запущенный контейнер)
python -c "from sqlalchemy import create_engine, text; e=create_engine('postgresql://interviewer_user:change_me_in_production@localhost:5432/voice_interviewer'); e.connect().execute(text('SELECT 1')); print('✅ PostgreSQL')"

# LiveKit
python -c "import asyncio,os; from dotenv import load_dotenv; from livekit import api; load_dotenv(); lk=api.LiveKitAPI(os.getenv('LIVEKIT_URL'),os.getenv('LIVEKIT_API_KEY'),os.getenv('LIVEKIT_API_SECRET')); asyncio.run(lk.room.list_rooms(api.ListRoomsRequest())); print('✅ LiveKit')"
```

📖 **Подробные скрипты и troubleshooting:** [TESTING.md#этап-5-проверка-подключений-к-сервисам](TESTING.md#этап-5-проверка-подключений-к-сервисам)

### Безопасность

- [ ] Изменить пароли в `.env` (POSTGRES_PASSWORD, PGADMIN_PASSWORD)
- [ ] Отключить pgAdmin и Redis Commander в production
- [ ] Настроить HTTPS (сертификаты Let's Encrypt или корпоративные)
- [ ] Ограничить доступ к портам 5432, 6379 через firewall
- [ ] Использовать secrets manager (Vault, AWS Secrets Manager) вместо `.env`

### Переменные окружения

```env
# === Продакшен значения ===
POSTGRES_PASSWORD=<сгенерированный_пароль_32_символа>
POSTGRES_USER=interviewer_prod
POSTGRES_DB=voice_interviewer_prod

# === API ключи ===
DEEPSEEK_API_KEY=sk-...
LIVEKIT_API_KEY=API...
LIVEKIT_API_SECRET=...
AZURE_OPENAI_API_KEY=...

# === URLs ===
LIVEKIT_URL=wss://your-project.livekit.cloud
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
```

### Бэкапы

```bash
# PostgreSQL backup
docker exec voice_interviewer_postgres pg_dump -U interviewer_user voice_interviewer > backup_$(date +%Y%m%d).sql

# Redis backup (RDB snapshot)
docker exec voice_interviewer_redis redis-cli BGSAVE
docker cp voice_interviewer_redis:/data/dump.rdb ./redis_backup_$(date +%Y%m%d).rdb
```

### Мониторинг

Рекомендуемые метрики:

| Метрика | Источник | Алерт порог |
|---------|----------|-------------|
| API latency | FastAPI middleware | > 2s |
| Active sessions | Redis KEYS count | > 1000 |
| PostgreSQL connections | pg_stat_activity | > 80% max |
| Voice agent errors | logs/agent.log | > 5/min |
| LiveKit room failures | LiveKit Cloud dashboard | > 1% |

## Nginx Конфигурация

```nginx
upstream fastapi {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    location / {
        proxy_pass http://fastapi;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    location /static/ {
        alias /app/public/;
        expires 1d;
    }
}
```

## Systemd Service

### FastAPI Server

```ini
# /etc/systemd/system/hanc-api.service
[Unit]
Description=Hanc.AI Voice Consultant API
After=network.target postgresql.service redis.service

[Service]
Type=exec
User=hanc
Group=hanc
WorkingDirectory=/opt/hanc-voice-consultant
Environment="PATH=/opt/hanc-voice-consultant/venv/bin"
EnvironmentFile=/opt/hanc-voice-consultant/.env
ExecStart=/opt/hanc-voice-consultant/venv/bin/uvicorn src.web.server:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Voice Agent

```ini
# /etc/systemd/system/hanc-agent.service
[Unit]
Description=Hanc.AI Voice Agent
After=network.target hanc-api.service

[Service]
Type=exec
User=hanc
Group=hanc
WorkingDirectory=/opt/hanc-voice-consultant
Environment="PATH=/opt/hanc-voice-consultant/venv/bin"
EnvironmentFile=/opt/hanc-voice-consultant/.env
ExecStart=/opt/hanc-voice-consultant/venv/bin/python scripts/run_voice_agent.py prod
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Управление

```bash
# Запуск
sudo systemctl start hanc-api hanc-agent

# Статус
sudo systemctl status hanc-api hanc-agent

# Логи
sudo journalctl -u hanc-api -f
sudo journalctl -u hanc-agent -f

# Автозапуск
sudo systemctl enable hanc-api hanc-agent
```

## Health Checks

### API Health Endpoint

```bash
curl http://localhost:8000/health
# Expected: {"status": "ok", "redis": "connected", "postgres": "connected"}
```

### Agent Health (встроенный endpoint)

```bash
# Проверка через API (PID-файл + pgrep fallback)
curl http://localhost:8000/api/agent/health
# Expected: {"worker_alive": true, "worker_pid": 12345}
```

Фронтенд автоматически проверяет доступность агента перед созданием сессии.

### Agent Health (CLI)

```bash
# Через hanc.sh (рекомендуется для dev)
./scripts/hanc.sh status

# Ручная проверка процесса
pgrep -f "run_voice_agent.py"

# Проверка логов на ошибки
tail -n 100 logs/agent.log | grep -i error
```

### LiveKit-комнаты

```bash
# Список активных комнат
curl http://localhost:8000/api/rooms

# Очистка всех комнат
curl -X DELETE http://localhost:8000/api/rooms

# CLI-скрипт
./venv/bin/python scripts/cleanup_rooms.py --force
```

При старте сервера все старые комнаты автоматически удаляются.

## Масштабирование

### Горизонтальное масштабирование API

```bash
# Увеличить количество workers
uvicorn src.web.server:app --workers 8
```

### Несколько Voice Agents

LiveKit поддерживает автоматический dispatch агентов. Запустите несколько экземпляров:

```bash
# Агент 1 (на сервере A)
python scripts/run_voice_agent.py prod

# Агент 2 (на сервере B)
python scripts/run_voice_agent.py prod
```

LiveKit автоматически распределит комнаты между доступными агентами.

## Troubleshooting

| Проблема | Диагностика | Решение |
|----------|-------------|---------|
| PostgreSQL connection refused | `docker logs voice_interviewer_postgres` | Проверьте POSTGRES_PASSWORD в .env |
| Redis timeout | `redis-cli -h localhost ping` | Увеличьте timeout или проверьте сеть |
| Agent не подключается | `tail -f logs/agent.log` | Проверьте LIVEKIT_* переменные |
| 502 Bad Gateway | `sudo systemctl status hanc-api` | Убедитесь что uvicorn запущен |

## Документы клиентов (input/)

При развёртывании убедитесь, что папка `input/` доступна для записи и чтения:

```bash
# Создание папки для документов
mkdir -p /opt/hanc-voice-consultant/input
chown hanc:hanc /opt/hanc-voice-consultant/input
chmod 750 /opt/hanc-voice-consultant/input
```

Рекомендации:

- Ограничьте размер загружаемых файлов (рекомендуется max 50 MB на файл)
- Поддерживаемые форматы: PDF, DOCX, XLSX, MD, TXT
- Периодически очищайте старые документы (рекомендуется retention 30 дней)
- Документы обрабатываются локально (PyMuPDF, python-docx, openpyxl) — внешние сервисы не требуются

## Связанная документация

- [DOCKER.md](DOCKER.md) — справочник Docker-команд (production docker-compose)
- [QUICKSTART.md](QUICKSTART.md) — быстрый старт
- [VOICE_AGENT.md](VOICE_AGENT.md) — архитектура голосового агента
- [LOGGING.md](LOGGING.md) — настройка логирования
- [ERROR_HANDLING.md](ERROR_HANDLING.md) — обработка ошибок
