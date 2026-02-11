# Docker — команды и управление

Справочник по Docker-командам для проекта Hanc.AI Voice Agent.

> Этот документ описывает **корневой `docker-compose.yml`** (production — все 6 сервисов).
> Для dev-инфраструктуры (только Redis + PostgreSQL + pgAdmin) см. `config/docker-compose.yml` и [DEPLOYMENT.md](DEPLOYMENT.md#docker-compose-developmentstaging).

## Архитектура

```
Browser (https://demo.hanc.ai)
    │
    │ :443 (TLS)
    ▼
┌─────────┐     ┌──────────┐
│  nginx   │────▶│   web    │ :8000 (internal)
│  :80/443 │     │ FastAPI  │
└─────────┘     └──────────┘
                ┌──────────┐  ┌───────┐  ┌──────────┐
                │  agent   │  │ redis │  │ postgres │
                │ LiveKit  │  │ :6379 │  │ :5432    │
                └──────────┘  └───────┘  └──────────┘
```

| Сервис | Контейнер | Образ | Назначение |
|--------|-----------|-------|-----------|
| nginx | hanc_nginx | nginx:1.27-alpine | SSL termination, reverse proxy |
| certbot | hanc_certbot | certbot/certbot | Авто-обновление SSL-сертификатов |
| web | hanc_web | hanc-ai (свой) | FastAPI — API + фронтенд |
| agent | hanc_agent | hanc-ai (свой) | LiveKit голосовой агент |
| redis | hanc_redis | redis:7-alpine | Кэш сессий (опционально) |
| postgres | hanc_postgres | postgres:16-alpine | Долгосрочное хранение (опционально) |

---

## Первый деплой

```bash
# 1. Настроить окружение
cp .env.example .env
nano .env                        # DOMAIN, API-ключи, CERTBOT_EMAIL

# 2. Собрать образ приложения
docker compose build

# 3. Получить SSL-сертификат (один раз)
./scripts/init-letsencrypt.sh

# 4. Запустить все 6 сервисов
docker compose up -d
```

---

## Повседневные команды

### Запуск и остановка

```bash
# Запустить все сервисы (фон)
docker compose up -d

# Запустить + пересобрать образ (после git pull)
docker compose up --build -d

# Остановить все сервисы (контейнеры сохраняются)
docker compose stop

# Остановить и удалить контейнеры (данные в volumes сохраняются)
docker compose down

# Остановить и удалить ВСЁ включая volumes (ОСТОРОЖНО — удалит БД!)
docker compose down -v
```

### Статус и мониторинг

```bash
# Список контейнеров и их статус
docker compose ps

# Логи всех сервисов (последние 50 строк)
docker compose logs --tail=50

# Логи конкретного сервиса (в реальном времени)
docker compose logs -f web
docker compose logs -f agent
docker compose logs -f nginx

# Логи за последний час
docker compose logs --since 1h
```

### Перезапуск

```bash
# Перезапустить один сервис (без пересборки)
docker compose restart web
docker compose restart agent
docker compose restart nginx

# Пересобрать и перезапустить только web (после изменения кода)
docker compose up --build -d web

# Пересобрать и перезапустить только agent
docker compose up --build -d agent
```

---

## Сборка образа

```bash
# Собрать образ (с кэшем — быстро, если requirements.txt не менялся)
docker compose build

# Собрать без кэша (после изменения requirements.txt или Dockerfile)
docker compose build --no-cache

# Собрать только один сервис
docker compose build web
```

**Кэш слоёв Docker:** если `requirements.txt` не изменился, `pip install` берётся из кэша и сборка занимает секунды. Если `requirements.txt` изменился — пересобирается с нуля (~2-5 минут).

---

## Диагностика

### Проверка здоровья сервисов

```bash
# Web (FastAPI)
docker compose exec web curl -s http://localhost:8000/api/sessions

# Agent — проверить что запустился
docker compose logs agent --tail=10

# Redis
docker compose exec redis redis-cli ping
# Ожидание: PONG

# PostgreSQL
docker compose exec postgres pg_isready -U interviewer_user
# Ожидание: accepting connections

# Nginx — HTTPS работает
curl -I https://$DOMAIN

# SSL-сертификат — дата истечения
openssl s_client -connect $DOMAIN:443 -servername $DOMAIN < /dev/null 2>/dev/null | \
    openssl x509 -noout -dates
```

### Вход внутрь контейнера

```bash
# Shell в контейнере web
docker compose exec web /bin/sh

# Shell в контейнере agent
docker compose exec agent /bin/sh

# Проверить файлы внутри контейнера
docker compose exec web ls -la /app/src/
docker compose exec web ls -la /app/data/

# Проверить переменные окружения
docker compose exec web env | grep AZURE
docker compose exec agent env | grep LIVEKIT
```

### Просмотр файлов и БД

```bash
# Посмотреть SQLite базу внутри контейнера
docker compose exec web python -c "
import sqlite3, json
conn = sqlite3.connect('/app/data/sessions.db')
rows = conn.execute('SELECT session_id, status, company_name FROM sessions ORDER BY created_at DESC LIMIT 5').fetchall()
for r in rows: print(r)
"

# Проверить что nginx конфиг применился корректно
docker compose exec nginx cat /etc/nginx/nginx.conf
```

---

## SSL-сертификат

```bash
# Первичное получение (только один раз)
./scripts/init-letsencrypt.sh

# Принудительное обновление (если сертификат скоро истечёт)
docker compose exec certbot certbot renew --force-renewal
docker compose exec nginx nginx -s reload

# Проверить статус сертификата
docker compose exec certbot certbot certificates
```

**Авто-обновление:** certbot проверяет сертификат каждые 12 часов, nginx перезагружается каждые 6 часов. Обновление происходит автоматически за 30 дней до истечения.

---

## Управление данными

### Volumes (постоянные данные)

```bash
# Список Docker volumes
docker volume ls | grep hanc

# Размер volumes
docker system df -v | grep hanc
```

| Volume | Путь в контейнере | Содержимое |
|--------|-------------------|-----------|
| app_data | /app/data/ | sessions.db (SQLite) |
| app_logs | /app/logs/ | Логи приложения |
| app_output | /app/output/ | Результаты консультаций |
| redis_data | /data/ | Redis дамп |
| postgres_data | /var/lib/postgresql/data/ | PostgreSQL данные |

Bind-mount (не Docker volume):
| Путь на хосте | Путь в контейнере | Содержимое |
|---------------|-------------------|-----------|
| ./data/certbot/conf | /etc/letsencrypt | SSL-сертификаты |
| ./data/certbot/www | /var/www/certbot | ACME challenge файлы |

### Бэкап

```bash
# Бэкап SQLite (основная БД)
docker compose exec web cp /app/data/sessions.db /app/data/sessions.db.bak
docker cp hanc_web:/app/data/sessions.db ./backup_sessions.db

# Бэкап PostgreSQL (если используется)
docker compose exec postgres pg_dump -U interviewer_user voice_interviewer > backup_postgres.sql
```

---

## Обновление кода на сервере

```bash
# Стандартный процесс обновления
git pull
docker compose up --build -d

# Проверить что всё работает
docker compose ps
docker compose logs --tail=10
curl -I https://$DOMAIN
```

Если изменился только код Python (не requirements.txt) — сборка занимает ~10 секунд благодаря кэшу Docker-слоёв.

---

## Очистка

```bash
# Удалить неиспользуемые образы (освободить место)
docker image prune -f

# Удалить все неиспользуемые ресурсы Docker (образы, сети, кэш)
docker system prune -f

# Полная очистка проекта (ОСТОРОЖНО — удалит данные!)
docker compose down -v
docker image prune -a -f
```

---

## Частые проблемы

| Проблема | Команда диагностики | Решение |
|----------|---------------------|---------|
| Контейнер перезапускается в цикле | `docker compose logs agent --tail=50` | Смотреть traceback в логах |
| 502 Bad Gateway | `docker compose logs web --tail=20` | web не запустился — ошибка Python |
| Нет доступа к микрофону | Открыть по `https://`, не `http://` | Нужен SSL (nginx + certbot) |
| Старый код после деплоя | `docker compose build --no-cache` | Пересобрать без кэша |
| Нет места на диске | `docker system df` | `docker system prune -f` |
| Порт 80/443 занят | `ss -tlnp \| grep -E ':80\|:443'` | Остановить другой nginx/apache |
| Redis/Postgres не стартует | `docker compose logs redis` | Проверить healthcheck |
| SSL-сертификат не получается | `docker compose logs certbot` | DNS A-запись → IP сервера |
