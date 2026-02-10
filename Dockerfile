FROM python:3.14-slim

WORKDIR /app

# Системные зависимости (для psycopg2-binary, lxml, PyMuPDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Зависимости (кешируется при неизменном requirements.txt)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY src/ src/
COPY config/ config/
COPY prompts/ prompts/
COPY public/ public/
COPY scripts/ scripts/

# Рабочие директории
RUN mkdir -p data logs output

# Не-root пользователь
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# По умолчанию — web server
CMD ["python", "scripts/run_server.py"]
