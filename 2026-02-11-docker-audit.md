# Docker Deployment Audit — HANC.AI Voice Consultant
**Дата:** 2026-02-11

---

## CRITICAL (3)

### 1. Python 3.14-slim — нестабильный базовый образ
- **Файл:** `Dockerfile:1`
- Python 3.14 в pre-release. В `requirements.txt` прямо указано: *"Python 3.14+ может иметь проблемы совместимости"*
- C-расширения (livekit, psycopg2, PyMuPDF, lxml) могут не собраться
- **Рекомендация:** сменить на `python:3.12-slim`

### 2. Нет WebSocket headers в nginx — LiveKit не будет работать
- **Файл:** `config/nginx/nginx.conf.template:74-85`
- Отсутствуют заголовки `Upgrade` и `Connection` для WebSocket upgrade
- Фронтенд не сможет установить WS-соединение через nginx
- **Рекомендация:** добавить в `location /`:
  ```nginx
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  ```

### 3. API-ключи в `.env` закоммичены в репозиторий
- **Файл:** `.env`
- Все ключи (DeepSeek, Azure, LiveKit, Anthropic) доступны любому с доступом к репо
- `.env` есть в `.gitignore`, но файл уже в рабочей директории
- **Рекомендация:** ротировать все ключи, проверить что `.env` не попал в git-историю

---

## WARNING (7)

### 1. Dev-зависимости в production-образе
- **Файл:** `requirements.txt:94-107`
- pytest, black, flake8, mypy, pre-commit — добавляют ~50-100MB к образу
- **Рекомендация:** разделить на `requirements.txt` (prod) и `requirements-dev.txt`

### 2. Нет healthcheck у web и agent сервисов
- **Файл:** `docker-compose.yml:41-88`
- Redis и PostgreSQL имеют healthcheck, web и agent — нет
- nginx зависит от web с `condition: service_started`, а не `service_healthy`
- При старте nginx может получить 502, пока uvicorn не готов
- **Рекомендация:** добавить healthcheck:
  ```yaml
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
    interval: 10s
    timeout: 5s
    retries: 5
  ```

### 3. Uvicorn auto-reload в production
- **Файлы:** `scripts/run_server.py:20` + `.env:100`
- `ENVIRONMENT=development` в `.env` включает `reload=True` в uvicorn
- Это создаёт лишнюю нагрузку CPU и неожиданные перезапуски
- **Рекомендация:** установить `ENVIRONMENT=production` в compose `environment:`

### 4. DATABASE_URL дублируется с разными паролями
- **Файлы:** `docker-compose.yml` + `.env`
- В compose default: `change_me`, в `.env`: `change_me_in_production`
- Работает за счёт подстановки из `.env`, но хрупко
- **Рекомендация:** убрать DATABASE_URL из `.env`, оставить только в compose

### 5. Нет EXPOSE в Dockerfile
- **Файл:** `Dockerfile`
- Отсутствует `EXPOSE 8000`
- **Рекомендация:** добавить `EXPOSE 8000` перед CMD

### 6. Agent сервис всегда в dev-режиме
- **Файл:** `docker-compose.yml:70`
- `command: python scripts/run_voice_agent.py dev` — жёстко задан dev
- В production LiveKit agents должен использовать `start`
- **Рекомендация:** использовать переменную `AGENT_MODE` для конфигурации

### 7. PID-файл бесполезен в контейнере
- **Файл:** `scripts/run_voice_agent.py:33-78`
- Логика singleton через PID-файл не нужна в Docker (один процесс на контейнер)
- **Рекомендация:** пропускать PID-логику при обнаружении `/.dockerenv`

---

## MINOR (5)

### 1. Alembic в зависимостях, но не настроен
- **Файл:** `requirements.txt:28`
- `alembic>=1.13.0` указан, но нет `alembic.ini` и папки `alembic/`
- Миграции делаются вручную через ALTER TABLE в `src/session/manager.py`

### 2. Неоптимальный порядок COPY слоёв
- **Файл:** `Dockerfile:15-19`
- Все COPY инвалидируют кеш вместе
- Стабильные файлы (prompts/, config/) стоит копировать перед часто меняющимися (src/)

### 3. Deprecated version key
- **Файл:** `config/docker-compose.yml:1`
- `version: '3.8'` — deprecated в Docker Compose v2+
- Корневой compose файл уже без version (корректно)

### 4. Security headers теряются на static assets
- **Файл:** `config/nginx/nginx.conf.template:88-96`
- `add_header Cache-Control` в static блоке убирает HSTS, X-Frame-Options из parent блока
- Nginx `add_header` заменяет, а не дополняет при вложенных location

### 5. Возможно нехватка системных библиотек
- **Файл:** `Dockerfile:6-8`
- Установлены только `gcc`, `libpq-dev`
- Для lxml может потребоваться `libxml2-dev`, `libxslt1-dev`
- На python:3.14 без pre-built wheels сборка провалится
