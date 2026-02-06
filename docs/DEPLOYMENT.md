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

| Вариант | Описание | Рекомендуется для |
|---------|----------|-------------------|
| Docker Compose | Локальная инфраструктура | Разработка, staging |
| Kubernetes | Полноценный оркестратор | Production |
| Managed Services | LiveKit Cloud + Azure + RDS | Минимум ops |

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

## Production Checklist

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

### Agent Health

```bash
# Проверка процесса
pgrep -f "run_voice_agent.py"

# Проверка логов на ошибки
tail -n 100 logs/agent.log | grep -i error
```

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

## Связанная документация

- [QUICKSTART.md](QUICKSTART.md) — быстрый старт
- [VOICE_AGENT.md](VOICE_AGENT.md) — архитектура голосового агента
- [LOGGING.md](LOGGING.md) — настройка логирования
- [ERROR_HANDLING.md](ERROR_HANDLING.md) — обработка ошибок
