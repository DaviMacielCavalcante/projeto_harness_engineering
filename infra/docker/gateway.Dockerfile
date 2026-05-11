# Dockerfile do gateway FastAPI.
# Stack: python:3.12-slim + uv (sem multi-stage por simplicidade no B1).

FROM python:3.12-slim

WORKDIR /app

RUN ["pip", "install", "--no-cache-dir", "uv==0.4.27"]

COPY pyproject.toml .

COPY uv.lock* .

RUN ["uv", "sync", "--frozen", "--no-dev", "--no-install-project"]

COPY src/ ./src/

COPY prompts/ ./prompts/

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]