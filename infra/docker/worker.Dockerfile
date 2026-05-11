# Dockerfile compartilhado dos workers (ingest e query).
# Um único Dockerfile, dois containers — o WORKER_KIND escolhe qual main rodar.

FROM python:3.12-slim

WORKDIR /app

RUN ["pip", "install", "--no-cache-dir", "uv==0.4.27"]

COPY pyproject.toml .

COPY uv.lock* .

RUN ["uv", "sync", "--frozen", "--no-dev", "--no-install-project"]

COPY src/ ./src/

COPY prompts/ ./prompts/

ENV PYTHONPATH=/app

CMD ["sh", "-c", "uv run python -m src.workers.${WORKER_KIND}.main"]