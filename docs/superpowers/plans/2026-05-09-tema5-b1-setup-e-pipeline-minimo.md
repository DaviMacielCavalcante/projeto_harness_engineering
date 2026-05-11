# Tema 5 — B1: Setup e Pipeline Mínimo

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subir a infraestrutura base (Docker Compose Modo 1) e ter o pipeline RAG ponta-a-ponta funcionando minimamente: ingerir 1 PDF e responder 1 query com citação.

**Architecture:** Python 3.12 com `uv`. FastAPI gateway publica em RabbitMQ. Workers (ingest e query) consomem das filas, falam com Ollama (embeddings + generate) e Qdrant (vector store) via Tailscale (ou DNS interno do compose no Modo 1). Schemas Pydantic compartilhados em `src/shared/`. TDD onde fizer sentido (chunking, schemas, gateway, parsing); testes de integração via compose para o pipeline end-to-end.

**Tech Stack:** Python 3.12, uv, FastAPI, Uvicorn, aio-pika (RabbitMQ), httpx, qdrant-client, redis-py, pypdf, langdetect, structlog, pydantic, pydantic-settings, tenacity, pytest, pytest-asyncio, ruff. Containers: rabbitmq:3-management, qdrant/qdrant, redis:7-alpine, ollama/ollama.

**Bloco do cronograma:** B1 (10–12/05/2026, 3 dias).

**Marco luz-verde do bloco:** `make smoke` ingere um PDF do `samples/` e roda uma query que devolve resposta JSON com citação válida.

---

## Estrutura de arquivos a criar

```
projeto_harness_engineering/
├── .env.example                          # template de env vars
├── .env.local                            # cópia para dev local (Modo 1)
├── .gitignore                            # ignora .venv, __pycache__, .env, data/
├── docker-compose.yml                    # serviços + profile "all"
├── Makefile                              # targets: dev, smoke, logs, down
├── pyproject.toml                        # uv + dependências
├── README.md                             # como rodar
├── infra/
│   └── docker/
│       ├── gateway.Dockerfile
│       └── worker.Dockerfile
├── prompts/
│   ├── system_qa_pt.md                   # system prompt PT (versão B1)
│   └── user_qa_template.md               # Jinja2 template
├── samples/
│   └── exemplo.pdf                       # 1 PDF de teste (qualquer doc curto)
├── scripts/
│   └── smoke_test.py                     # script de aceitação do bloco
├── src/
│   ├── __init__.py
│   ├── gateway/
│   │   ├── __init__.py
│   │   ├── main.py                       # FastAPI app + lifespan
│   │   └── routes.py                     # POST /ingest, POST /query, GET /health
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── config.py                     # Settings (pydantic-settings)
│   │   ├── logging.py                    # structlog setup
│   │   ├── messaging.py                  # aio-pika helpers
│   │   ├── ollama_client.py              # httpx wrapper para Ollama
│   │   └── schemas.py                    # Pydantic schemas compartilhados
│   └── workers/
│       ├── __init__.py
│       ├── ingest/
│       │   ├── __init__.py
│       │   ├── chunking.py               # chunking recursivo
│       │   ├── main.py                   # consumer loop
│       │   └── parsing.py                # parse_pdf
│       └── query/
│           ├── __init__.py
│           ├── main.py                   # consumer loop
│           └── prompt_builder.py         # monta prompt a partir de chunks
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_chunking.py
    │   ├── test_prompt_builder.py
    │   └── test_schemas.py
    └── integration/
        ├── __init__.py
        └── test_gateway_smoke.py
```

---

## Task 1: Inicializar repo Python com uv

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `src/__init__.py`, `src/shared/__init__.py`, `src/gateway/__init__.py`, `src/workers/__init__.py`, `src/workers/ingest/__init__.py`, `src/workers/query/__init__.py`
- Create: `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/conftest.py`

- [x] **Step 1: Verificar uv instalado**

Run: `uv --version`
Expected: versão `0.4.x` ou superior. Se não tiver: `winget install astral-sh.uv` (Windows) ou `curl -LsSf https://astral.sh/uv/install.sh | sh`.

- [x] **Step 2: Criar `pyproject.toml`**

Conteúdo:

```toml
[project]
name = "rag-distribuido"
version = "0.1.0"
description = "Tema 5 — RAG distribuído (Engenharia de Contexto e Harness aplicada à PDP)"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "structlog>=24.4",
    "aio-pika>=9.5",
    "httpx>=0.28",
    "qdrant-client>=1.12",
    "redis>=5.2",
    "pypdf>=5.1",
    "langdetect>=1.0.9",
    "tenacity>=9.0",
    "jinja2>=3.1",
    "prometheus-client>=0.21",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.14",
    "respx>=0.21",
    "ruff>=0.8",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "ASYNC"]
ignore = ["E501"]

[tool.uv]
package = false
```

- [x] **Step 3: Criar `.gitignore`**

```
# Python
__pycache__/
*.py[cod]
.venv/
*.egg-info/
.pytest_cache/
.ruff_cache/
.mypy_cache/

# Env
.env
.env.local
.env.distributed

# Data and artifacts
data/
*.log
samples/*.pdf
!samples/.gitkeep

# IDE
.vscode/
.idea/

# Docker volumes
qdrant_storage/
ollama_models/
rabbitmq_data/
redis_data/
```

- [x] **Step 4: Criar `README.md` esqueleto**

```markdown
# Tema 5 — RAG Distribuído

Sistema RAG (Retrieval-Augmented Generation) distribuído entre 3 PCs via Tailscale, sem custos de cloud.

Disciplina: Programação Distribuída e Paralela (CESUPA).

## Pré-requisitos

- Docker e Docker Compose
- Python 3.12 com `uv` instalado
- (Opcional) GPU NVIDIA com `nvidia-container-toolkit` para Ollama acelerado

## Modo 1 — Dev local (single-host)

Sobe tudo no mesmo PC. Use para desenvolvimento e testes rápidos.

```bash
make dev          # sobe compose com profile "all"
make smoke        # roda smoke test ponta-a-ponta
make logs         # acompanha logs
make down         # derruba tudo
```

## Modo 2 — Distribuído (3 PCs via Tailscale)

Configurado em B3. Para B1, use só Modo 1.

## Estrutura

Veja `docs/superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md` para o design completo.
```

- [x] **Step 5: Criar diretórios + arquivos `__init__.py` vazios**

Run (PowerShell):
```powershell
New-Item -ItemType Directory -Force -Path src, src/shared, src/gateway, src/workers, src/workers/ingest, src/workers/query, tests, tests/unit, tests/integration, samples, prompts, scripts, infra/docker | Out-Null
"" | Set-Content src/__init__.py, src/shared/__init__.py, src/gateway/__init__.py, src/workers/__init__.py, src/workers/ingest/__init__.py, src/workers/query/__init__.py, tests/__init__.py, tests/unit/__init__.py, tests/integration/__init__.py
"# placeholder for sample PDFs" | Set-Content samples/.gitkeep
```

- [x] **Step 6: Criar `tests/conftest.py` mínimo**

```python
import sys
from pathlib import Path

# Permite importar src.* sem instalar como pacote
sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [x] **Step 7: Sincronizar dependências**

Run: `uv sync`
Expected: cria `.venv/`, instala todas as dependências, gera `uv.lock`.

- [x] **Step 8: Validar pytest roda**

Run: `uv run pytest`
Expected: `0 passed` (não há testes ainda, mas pytest deve rodar sem erro de collection).

---

## Task 2: Configuração compartilhada (`shared/config.py`)

**Files:**
- Create: `src/shared/config.py`
- Create: `.env.example`
- Create: `.env.local`
- Create: `tests/unit/test_config.py`

- [x] **Step 1: Escrever teste falhando**

`tests/unit/test_config.py`:

```python
import os
import pytest
from src.shared.config import Settings


def test_settings_loads_defaults(monkeypatch):
    monkeypatch.delenv("RABBITMQ_URL", raising=False)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    s = Settings(_env_file=None)
    assert s.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert s.ollama_url == "http://ollama:11434"
    assert s.qdrant_url == "http://qdrant:6333"
    assert s.redis_url == "redis://redis:6379/0"
    assert s.qdrant_collection == "se_corpus"
    assert s.embedding_model == "nomic-embed-text"
    assert s.generation_model == "qwen2.5:7b-instruct"


def test_settings_overrides_via_env(monkeypatch):
    monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@1.2.3.4:5672/")
    monkeypatch.setenv("OLLAMA_URL", "http://1.2.3.4:11434")
    s = Settings(_env_file=None)
    assert s.rabbitmq_url == "amqp://user:pass@1.2.3.4:5672/"
    assert s.ollama_url == "http://1.2.3.4:11434"
```

- [x] **Step 2: Rodar teste — deve falhar**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'src.shared.config'`.

- [x] **Step 3: Implementar `src/shared/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Mensageria
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    queue_ingest_documents: str = "ingest.documents"
    queue_ingest_chunks: str = "ingest.chunks"
    queue_query_requests: str = "query.requests"

    # Inferência
    ollama_url: str = "http://ollama:11434"
    embedding_model: str = "nomic-embed-text"
    generation_model: str = "qwen2.5:7b-instruct"
    generation_num_ctx: int = 8192
    generation_temperature: float = 0.2

    # Vector DB
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "se_corpus"
    embedding_dim: int = 768

    # Cache
    redis_url: str = "redis://redis:6379/0"

    # Chunking
    chunk_target_tokens: int = 800
    chunk_overlap_tokens: int = 120

    # Observabilidade
    log_level: str = "INFO"
    service_name: str = "unset"

    # Retrieval
    retrieval_top_k_initial: int = 20
    retrieval_top_k_final: int = 5


settings = Settings()
```

- [x] **Step 4: Rodar teste — deve passar**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: 2 passed.

- [x] **Step 5: Criar `.env.example`**

```dotenv
# Modo 1 (single-host) — defaults do compose já funcionam, deixe vazio.
# Modo 2 (distribuído) — preencher com IPs Tailscale do PC1.

# RABBITMQ_URL=amqp://guest:guest@100.x.y.z:5672/
# OLLAMA_URL=http://100.x.y.z:11434
# QDRANT_URL=http://100.x.y.z:6333
# REDIS_URL=redis://100.x.y.z:6379/0

LOG_LEVEL=INFO
```

- [x] **Step 6: Copiar para `.env.local`**

Run (PowerShell): `Copy-Item .env.example .env.local`

---

## Task 3: Logging estruturado (`shared/logging.py`)

**Files:**
- Create: `src/shared/logging.py`

- [x] **Step 1: Implementar setup de logging (não há teste — wrapper trivial)**

`src/shared/logging.py`:

```python
import logging
import sys
import structlog
from src.shared.config import settings


def configure_logging(service_name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Configura structlog para emitir JSON no stdout. Idempotente."""
    name = service_name or settings.service_name

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    log = structlog.get_logger().bind(service=name)
    return log


def bind_correlation_id(correlation_id: str) -> None:
    """Adiciona correlation_id ao contexto do logger atual."""
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)


def clear_correlation_id() -> None:
    structlog.contextvars.clear_contextvars()
```

- [x] **Step 2: Validar que módulo carrega**

Run: `uv run python -c "from src.shared.logging import configure_logging; log = configure_logging('test'); log.info('hello', foo='bar')"`
Expected: 1 linha JSON em stdout com campos `event=hello`, `foo=bar`, `service=test`, `level=info`, `timestamp=...`.

---

## Task 4: Schemas Pydantic compartilhados (`shared/schemas.py`)

**Files:**
- Create: `src/shared/schemas.py`
- Create: `tests/unit/test_schemas.py`

- [x] **Step 1: Escrever teste falhando**

`tests/unit/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError
from src.shared.schemas import (
    IngestRequest,
    QueryRequest,
    QueryResponse,
    Citation,
    ChunkMessage,
    DocumentMessage,
)


def test_ingest_request_valid():
    req = IngestRequest(filename="paper.pdf", content_b64="aGVsbG8=", source_type="pdf")
    assert req.filename == "paper.pdf"
    assert req.source_type == "pdf"


def test_ingest_request_rejects_unknown_source_type():
    with pytest.raises(ValidationError):
        IngestRequest(filename="x", content_b64="aGk=", source_type="docx")


def test_query_request_defaults():
    req = QueryRequest(question="O que é arquitetura hexagonal?")
    assert req.top_k == 5
    assert req.session_id is None


def test_citation_roundtrip():
    c = Citation(doc_id="abc", chunk_id="abc:0", page=1, snippet="texto", source="paper.pdf")
    d = c.model_dump()
    c2 = Citation.model_validate(d)
    assert c == c2


def test_query_response_serialization():
    resp = QueryResponse(
        answer="Resposta",
        citations=[Citation(doc_id="a", chunk_id="a:0", page=None, snippet="s", source="x.pdf")],
        usage={"tokens_in": 100, "tokens_out": 30},
        latency_ms=1234,
    )
    payload = resp.model_dump_json()
    assert "Resposta" in payload
    assert "tokens_in" in payload


def test_chunk_message_required_fields():
    msg = ChunkMessage(
        doc_id="a",
        chunk_id="a:0",
        text="conteúdo",
        source="paper.pdf",
        page=2,
        lang="pt",
        chunk_index=0,
    )
    assert msg.chunk_id == "a:0"
```

- [x] **Step 2: Rodar teste — deve falhar**

Run: `uv run pytest tests/unit/test_schemas.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [x] **Step 3: Implementar `src/shared/schemas.py`**

```python
from typing import Literal
from pydantic import BaseModel, Field


SourceType = Literal["pdf", "md", "html"]


class IngestRequest(BaseModel):
    filename: str
    content_b64: str = Field(description="Conteúdo do documento codificado em base64")
    source_type: SourceType


class IngestResponse(BaseModel):
    correlation_id: str
    doc_id: str
    status: Literal["accepted"] = "accepted"


class DocumentMessage(BaseModel):
    """Mensagem publicada na fila ingest.documents."""
    correlation_id: str
    doc_id: str
    filename: str
    content_b64: str
    source_type: SourceType


class ChunkMessage(BaseModel):
    """Mensagem publicada na fila ingest.chunks."""
    doc_id: str
    chunk_id: str
    text: str
    source: str
    page: int | None = None
    lang: str = "unk"
    chunk_index: int


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    session_id: str | None = None


class Citation(BaseModel):
    doc_id: str
    chunk_id: str
    page: int | None
    snippet: str
    source: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    usage: dict[str, int]
    latency_ms: int


class QueryRequestMessage(BaseModel):
    """Mensagem publicada na fila query.requests."""
    correlation_id: str
    reply_to: str
    question: str
    top_k: int
    session_id: str | None = None
```

- [x] **Step 4: Rodar teste — deve passar**

Run: `uv run pytest tests/unit/test_schemas.py -v`
Expected: 5 passed.

---

## Task 5: Cliente Ollama (`shared/ollama_client.py`)

**Files:**
- Create: `src/shared/ollama_client.py`
- Create: `tests/unit/test_ollama_client.py`

- [x] **Step 1: Escrever teste falhando com `respx` (mock HTTP)**

`tests/unit/test_ollama_client.py`:

```python
import pytest
import respx
import httpx
from src.shared.ollama_client import OllamaClient


@pytest.mark.asyncio
@respx.mock
async def test_embed_returns_vector():
    route = respx.post("http://ollama:11434/api/embeddings").mock(
        return_value=httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})
    )
    client = OllamaClient(base_url="http://ollama:11434")
    vec = await client.embed("hello", model="nomic-embed-text")
    assert vec == [0.1, 0.2, 0.3]
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_generate_returns_text():
    respx.post("http://ollama:11434/api/generate").mock(
        return_value=httpx.Response(200, json={
            "response": "Resposta gerada",
            "prompt_eval_count": 50,
            "eval_count": 12,
        })
    )
    client = OllamaClient(base_url="http://ollama:11434")
    out = await client.generate(
        prompt="Pergunta?",
        model="qwen2.5:7b-instruct",
        options={"temperature": 0.2, "num_ctx": 8192},
    )
    assert out["text"] == "Resposta gerada"
    assert out["tokens_in"] == 50
    assert out["tokens_out"] == 12


@pytest.mark.asyncio
@respx.mock
async def test_embed_retries_on_500_then_succeeds():
    respx.post("http://ollama:11434/api/embeddings").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"embedding": [0.4]}),
        ]
    )
    client = OllamaClient(base_url="http://ollama:11434")
    vec = await client.embed("x", model="nomic-embed-text")
    assert vec == [0.4]
```

- [x] **Step 2: Rodar teste — deve falhar**

Run: `uv run pytest tests/unit/test_ollama_client.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [x] **Step 3: Implementar `src/shared/ollama_client.py`**

```python
import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)


class OllamaClient:
    def __init__(self, base_url: str, timeout: float = 60.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def _post_with_retry(self, path: str, json: dict) -> dict:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1, max=8),
            retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=self._timeout) as http:
                    resp = await http.post(f"{self._base_url}{path}", json=json)
                    resp.raise_for_status()
                    return resp.json()
        raise RuntimeError("unreachable")

    async def embed(self, text: str, model: str) -> list[float]:
        data = await self._post_with_retry(
            "/api/embeddings",
            {"model": model, "prompt": text},
        )
        return data["embedding"]

    async def generate(
        self,
        prompt: str,
        model: str,
        options: dict | None = None,
    ) -> dict:
        payload = {"model": model, "prompt": prompt, "stream": False}
        if options:
            payload["options"] = options
        data = await self._post_with_retry("/api/generate", payload)
        return {
            "text": data.get("response", ""),
            "tokens_in": data.get("prompt_eval_count", 0),
            "tokens_out": data.get("eval_count", 0),
        }
```

- [x] **Step 4: Rodar teste — deve passar**

Run: `uv run pytest tests/unit/test_ollama_client.py -v`
Expected: 3 passed.

---

## Task 6: Helpers de mensageria (`shared/messaging.py`)

**Files:**
- Create: `src/shared/messaging.py`

Não há teste unitário direto — `aio-pika` exige broker real; será exercitado pelo smoke test e tasks subsequentes.

- [x] **Step 1: Implementar `src/shared/messaging.py`**

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection


@asynccontextmanager
async def connect(url: str) -> AsyncIterator[AbstractRobustConnection]:
    conn = await aio_pika.connect_robust(url)
    try:
        yield conn
    finally:
        await conn.close()


async def declare_queues(conn: AbstractRobustConnection, *names: str) -> None:
    """Declara filas com DLX padrão. DLX e bind explícito vêm em B3."""
    channel = await conn.channel()
    for name in names:
        await channel.declare_queue(name, durable=True)
    await channel.close()


async def publish_json(
    conn: AbstractRobustConnection,
    queue: str,
    payload: dict,
    correlation_id: str | None = None,
    reply_to: str | None = None,
) -> None:
    channel = await conn.channel()
    try:
        body = aio_pika.Message(
            body=__import__("json").dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            correlation_id=correlation_id,
            reply_to=reply_to,
        )
        await channel.default_exchange.publish(body, routing_key=queue)
    finally:
        await channel.close()


Handler = Callable[[AbstractIncomingMessage, dict], Awaitable[None]]


async def consume_forever(
    conn: AbstractRobustConnection,
    queue_name: str,
    handler: Handler,
    prefetch: int = 1,
) -> None:
    """Consome até o cancelamento do task. handler recebe (msg, payload_dict)."""
    import json
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=prefetch)
    queue = await channel.declare_queue(queue_name, durable=True)
    async with queue.iterator() as it:
        async for msg in it:
            async with msg.process(requeue=False):
                payload = json.loads(msg.body)
                await handler(msg, payload)
```

- [x] **Step 2: Validar que importa**

Run: `uv run python -c "from src.shared.messaging import connect, publish_json, consume_forever; print('ok')"`
Expected: `ok`.

---

## Task 7: Docker Compose Modo 1 + Dockerfiles

**Files:**
- Create: `docker-compose.yml`
- Create: `infra/docker/gateway.Dockerfile`
- Create: `infra/docker/worker.Dockerfile`

- [x] **Step 1: Criar `infra/docker/gateway.Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir uv==0.4.27

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY prompts/ ./prompts/

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [x] **Step 2: Criar `infra/docker/worker.Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir uv==0.4.27

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY prompts/ ./prompts/

ENV PYTHONPATH=/app

# WORKER_KIND ∈ {ingest, query} controla qual main rodar
CMD ["sh", "-c", "uv run python -m src.workers.${WORKER_KIND}.main"]
```

- [ ] **Step 3: Criar `docker-compose.yml`**

```yaml
name: rag-distribuido

x-worker-base: &worker-base
  build:
    context: .
    dockerfile: infra/docker/worker.Dockerfile
  env_file:
    - .env.local
  depends_on:
    rabbitmq:
      condition: service_healthy
    qdrant:
      condition: service_started
    ollama:
      condition: service_started
  restart: unless-stopped

services:
  rabbitmq:
    image: rabbitmq:3-management
    container_name: rag-rabbitmq
    profiles: ["all", "server"]
    ports:
      - "5672:5672"
      - "15672:15672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 10s
      timeout: 5s
      retries: 10
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq

  qdrant:
    image: qdrant/qdrant:v1.12.4
    container_name: rag-qdrant
    profiles: ["all", "server"]
    ports:
      - "6333:6333"
    volumes:
      - qdrant_storage:/qdrant/storage

  redis:
    image: redis:7-alpine
    container_name: rag-redis
    profiles: ["all", "server"]
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  ollama:
    image: ollama/ollama:latest
    container_name: rag-ollama
    profiles: ["all", "server"]
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    # Para usar GPU: descomente o bloco abaixo E garanta nvidia-container-toolkit instalado.
    # Sem GPU, deixe comentado — o Ollama cai para CPU automaticamente (use llama3.2:1b).
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]

  gateway:
    build:
      context: .
      dockerfile: infra/docker/gateway.Dockerfile
    container_name: rag-gateway
    profiles: ["all", "server"]
    env_file:
      - .env.local
    environment:
      SERVICE_NAME: gateway
    ports:
      - "8000:8000"
    depends_on:
      rabbitmq:
        condition: service_healthy
    restart: unless-stopped

  ingest-worker:
    <<: *worker-base
    container_name: rag-ingest-worker
    profiles: ["all", "worker"]
    environment:
      WORKER_KIND: ingest
      SERVICE_NAME: ingest-worker

  query-worker:
    <<: *worker-base
    container_name: rag-query-worker
    profiles: ["all", "worker"]
    environment:
      WORKER_KIND: query
      SERVICE_NAME: query-worker

volumes:
  rabbitmq_data:
  qdrant_storage:
  redis_data:
  ollama_models:
```

> Nota: a seção `deploy.resources` para GPU é ignorada se você rodar sem `nvidia-container-toolkit`. Para B1 sem GPU, tudo bem — Ollama cai pra CPU. Para puxar um modelo pequeno em CPU, você usará `llama3.2:1b` em Task 11.

- [ ] **Step 4: Validar sintaxe do compose**

Run: `docker compose --profile all config > /dev/null`
Expected: sem erro.

---

## Task 8: Gateway FastAPI (`src/gateway/`)

**Files:**
- Create: `src/gateway/main.py`
- Create: `src/gateway/routes.py`
- Create: `tests/integration/test_gateway_smoke.py`

- [ ] **Step 1: Implementar `src/gateway/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.gateway.routes import router
from src.shared.config import settings
from src.shared.logging import configure_logging
from src.shared.messaging import connect, declare_queues


log = configure_logging("gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("gateway.starting", rabbitmq=settings.rabbitmq_url)
    async with connect(settings.rabbitmq_url) as conn:
        await declare_queues(
            conn,
            settings.queue_ingest_documents,
            settings.queue_ingest_chunks,
            settings.queue_query_requests,
        )
        app.state.rabbitmq = conn
        log.info("gateway.ready")
        yield
    log.info("gateway.stopping")


app = FastAPI(title="RAG Distribuído — Gateway", lifespan=lifespan)
app.include_router(router)
```

- [ ] **Step 2: Implementar `src/gateway/routes.py`**

```python
import hashlib
import uuid
import asyncio
import json

import aio_pika
from fastapi import APIRouter, HTTPException, Request

from src.shared.config import settings
from src.shared.logging import bind_correlation_id, clear_correlation_id, configure_logging
from src.shared.messaging import publish_json
from src.shared.schemas import (
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)


log = configure_logging("gateway")
router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/ingest", response_model=IngestResponse, status_code=202)
async def ingest(req: IngestRequest, request: Request) -> IngestResponse:
    correlation_id = f"i-{uuid.uuid4().hex[:8]}"
    bind_correlation_id(correlation_id)
    try:
        doc_id = hashlib.sha256(
            (req.filename + req.content_b64[:1024]).encode()
        ).hexdigest()[:16]

        await publish_json(
            request.app.state.rabbitmq,
            settings.queue_ingest_documents,
            {
                "correlation_id": correlation_id,
                "doc_id": doc_id,
                "filename": req.filename,
                "content_b64": req.content_b64,
                "source_type": req.source_type,
            },
            correlation_id=correlation_id,
        )
        log.info("ingest.accepted", doc_id=doc_id, filename=req.filename)
        return IngestResponse(correlation_id=correlation_id, doc_id=doc_id)
    finally:
        clear_correlation_id()


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, request: Request) -> QueryResponse:
    correlation_id = f"q-{uuid.uuid4().hex[:8]}"
    bind_correlation_id(correlation_id)
    try:
        conn = request.app.state.rabbitmq
        channel = await conn.channel()
        try:
            reply_queue = await channel.declare_queue(
                f"query.responses.{correlation_id}",
                exclusive=True,
                auto_delete=True,
            )
            await publish_json(
                conn,
                settings.queue_query_requests,
                {
                    "correlation_id": correlation_id,
                    "reply_to": reply_queue.name,
                    "question": req.question,
                    "top_k": req.top_k,
                    "session_id": req.session_id,
                },
                correlation_id=correlation_id,
                reply_to=reply_queue.name,
            )
            log.info("query.published", question_len=len(req.question))

            async with reply_queue.iterator(timeout=120) as it:
                async for msg in it:
                    async with msg.process():
                        payload = json.loads(msg.body)
                        log.info("query.responded", latency_ms=payload.get("latency_ms"))
                        return QueryResponse(**payload)
            raise HTTPException(status_code=504, detail="timeout aguardando resposta")
        finally:
            await channel.close()
    finally:
        clear_correlation_id()
```

- [ ] **Step 3: Validar que o gateway sobe num teste de smoke (sem worker)**

`tests/integration/test_gateway_smoke.py`:

```python
"""Smoke test do gateway. Requer RabbitMQ rodando.

Rode com: docker compose --profile server up -d rabbitmq
e depois: uv run pytest tests/integration/test_gateway_smoke.py -v
"""
import os
import pytest
from httpx import AsyncClient, ASGITransport
from src.gateway.main import app


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="define RUN_INTEGRATION=1 e suba o RabbitMQ para rodar",
)


@pytest.mark.asyncio
async def test_health_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

> Esse teste é skipado por padrão; será exercitado de fato pelo smoke da Task 14.

---

## Task 9: Chunking recursivo (`workers/ingest/chunking.py`)

**Files:**
- Create: `src/workers/ingest/chunking.py`
- Create: `tests/unit/test_chunking.py`

- [ ] **Step 1: Escrever testes falhando**

`tests/unit/test_chunking.py`:

```python
import pytest
from src.workers.ingest.chunking import chunk_text, count_tokens_approx


def test_count_tokens_approx_uses_4chars_per_token():
    assert count_tokens_approx("a" * 400) == 100


def test_chunk_text_short_returns_single_chunk():
    chunks = chunk_text("texto curto", target_tokens=800, overlap_tokens=120)
    assert len(chunks) == 1
    assert chunks[0] == "texto curto"


def test_chunk_text_breaks_on_paragraph_boundary():
    text = ("a" * 1000) + "\n\n" + ("b" * 1000) + "\n\n" + ("c" * 1000)
    chunks = chunk_text(text, target_tokens=300, overlap_tokens=20)
    assert len(chunks) >= 3
    # cada chunk começa com letra esperada (sem partir parágrafo no meio)
    starts = [c.lstrip()[0] for c in chunks if c.strip()]
    assert "a" in starts and "b" in starts and "c" in starts


def test_chunk_text_overlap_is_applied():
    text = "a" * 4000  # ~1000 tokens
    chunks = chunk_text(text, target_tokens=200, overlap_tokens=40)
    assert len(chunks) >= 4
    # overlap entre adjacentes (chunks compartilham caracteres em sequência)
    for i in range(len(chunks) - 1):
        tail = chunks[i][-50:]
        head = chunks[i + 1][:200]
        # algum sufixo do anterior aparece no início do próximo
        overlap_chars = sum(1 for ch in tail if ch in head)
        assert overlap_chars > 0


def test_chunk_text_no_chunk_exceeds_target_significantly():
    text = "frase. " * 1000
    chunks = chunk_text(text, target_tokens=200, overlap_tokens=20)
    for c in chunks:
        # Tolerância de 25% acima do alvo
        assert count_tokens_approx(c) <= 250
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `uv run pytest tests/unit/test_chunking.py -v`
Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Implementar `src/workers/ingest/chunking.py`**

```python
def count_tokens_approx(text: str) -> int:
    """Aproximação simples: 1 token ≈ 4 caracteres. Substituir por tiktoken em B2 se necessário."""
    return max(1, len(text) // 4)


_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _split_with_separators(text: str, separators: list[str]) -> list[str]:
    """Divide text usando o primeiro separador disponível, recursivamente."""
    if not text:
        return []
    sep = separators[0]
    if sep == "":
        return [text]
    if sep not in text:
        return _split_with_separators(text, separators[1:])
    parts = text.split(sep)
    # Reanexa o separador a cada parte exceto a última, para preservar estrutura.
    out = []
    for i, p in enumerate(parts):
        if i < len(parts) - 1:
            out.append(p + sep)
        else:
            out.append(p)
    return out


def chunk_text(text: str, target_tokens: int, overlap_tokens: int) -> list[str]:
    """
    Chunking recursivo com fronteiras semânticas e overlap em caracteres.
    target_tokens: tamanho alvo de cada chunk (em tokens aproximados).
    overlap_tokens: quantidade de tokens repetidos entre chunks adjacentes.
    """
    target_chars = target_tokens * 4
    overlap_chars = overlap_tokens * 4

    if count_tokens_approx(text) <= target_tokens:
        return [text]

    pieces = _split_with_separators(text, _SEPARATORS)
    chunks: list[str] = []
    buffer = ""
    for piece in pieces:
        if not piece:
            continue
        # Se uma única peça já excede o alvo, força quebra dura por chars
        if len(piece) > target_chars:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            i = 0
            while i < len(piece):
                chunks.append(piece[i : i + target_chars])
                i += target_chars - overlap_chars
            continue
        if len(buffer) + len(piece) <= target_chars:
            buffer += piece
        else:
            if buffer:
                chunks.append(buffer)
            buffer = piece
    if buffer:
        chunks.append(buffer)

    # Aplica overlap: prepend dos últimos overlap_chars do anterior
    if overlap_chars > 0 and len(chunks) > 1:
        with_overlap = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap_chars:]
            with_overlap.append(prev_tail + chunks[i])
        chunks = with_overlap

    return chunks
```

- [ ] **Step 4: Rodar — deve passar**

Run: `uv run pytest tests/unit/test_chunking.py -v`
Expected: 5 passed.

---

## Task 10: Parsing de PDF (`workers/ingest/parsing.py`)

**Files:**
- Create: `src/workers/ingest/parsing.py`
- Modificar (sem teste novo): exercitado pelo smoke

- [ ] **Step 1: Implementar `src/workers/ingest/parsing.py`**

```python
import base64
import io

from pypdf import PdfReader

from src.shared.schemas import SourceType


def parse_document(content_b64: str, source_type: SourceType) -> list[tuple[int | None, str]]:
    """
    Devolve lista de (page_number, text) extraída do documento.
    Para md/html sem páginas, retorna [(None, conteúdo)].
    """
    raw = base64.b64decode(content_b64)
    if source_type == "pdf":
        return _parse_pdf(raw)
    if source_type == "md":
        return [(None, raw.decode("utf-8", errors="replace"))]
    if source_type == "html":
        # parsing rico fica para B2 (trafilatura). Aqui só decode bruto.
        return [(None, raw.decode("utf-8", errors="replace"))]
    raise ValueError(f"source_type não suportado: {source_type}")


def _parse_pdf(raw: bytes) -> list[tuple[int | None, str]]:
    reader = PdfReader(io.BytesIO(raw))
    out: list[tuple[int | None, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            out.append((i, text))
    return out
```

- [ ] **Step 2: Validar import**

Run: `uv run python -c "from src.workers.ingest.parsing import parse_document; print('ok')"`
Expected: `ok`.

---

## Task 11: Worker de ingestão fim-a-fim (`workers/ingest/main.py`)

**Files:**
- Create: `src/workers/ingest/main.py`

> Não há teste unitário — a validação acontece no smoke (Task 14). O worker conecta RabbitMQ, Ollama, Qdrant.

- [ ] **Step 1: Implementar `src/workers/ingest/main.py`**

```python
import asyncio
import hashlib
import socket

from langdetect import detect, LangDetectException
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from src.shared.config import settings
from src.shared.logging import bind_correlation_id, clear_correlation_id, configure_logging
from src.shared.messaging import connect, consume_forever
from src.shared.ollama_client import OllamaClient
from src.shared.schemas import DocumentMessage, ChunkMessage
from src.workers.ingest.chunking import chunk_text
from src.workers.ingest.parsing import parse_document


log = configure_logging("ingest-worker")
HOSTNAME = socket.gethostname()


async def ensure_qdrant_collection(qdrant: AsyncQdrantClient) -> None:
    collections = await qdrant.get_collections()
    names = {c.name for c in collections.collections}
    if settings.qdrant_collection not in names:
        await qdrant.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(
                size=settings.embedding_dim,
                distance=qmodels.Distance.COSINE,
            ),
        )
        log.info("qdrant.collection_created", name=settings.qdrant_collection)


async def handle_document(msg, payload: dict, ollama: OllamaClient, qdrant: AsyncQdrantClient) -> None:
    doc = DocumentMessage.model_validate(payload)
    bind_correlation_id(doc.correlation_id)
    try:
        log.info("ingest.document.received", doc_id=doc.doc_id, filename=doc.filename)
        pages = parse_document(doc.content_b64, doc.source_type)
        if not pages:
            log.warning("ingest.document.empty", doc_id=doc.doc_id)
            return

        # Detecta idioma com base nas primeiras 500 chars
        sample = " ".join(t for _, t in pages)[:500]
        try:
            lang = detect(sample)
        except LangDetectException:
            lang = "unk"

        # Chunking por página, mantendo page no payload
        points = []
        chunk_index = 0
        for page_num, page_text in pages:
            for chunk in chunk_text(
                page_text,
                target_tokens=settings.chunk_target_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            ):
                if not chunk.strip():
                    continue
                vec = await ollama.embed(chunk, model=settings.embedding_model)
                point_id = hashlib.sha256(
                    f"{doc.doc_id}:{chunk_index}".encode()
                ).hexdigest()[:32]
                points.append(
                    qmodels.PointStruct(
                        id=int(point_id, 16) % (2**63 - 1),
                        vector=vec,
                        payload={
                            "doc_id": doc.doc_id,
                            "chunk_id": f"{doc.doc_id}:{chunk_index}",
                            "text": chunk,
                            "source": doc.filename,
                            "page": page_num,
                            "lang": lang,
                            "chunk_index": chunk_index,
                        },
                    )
                )
                chunk_index += 1

        if points:
            await qdrant.upsert(collection_name=settings.qdrant_collection, points=points)
        log.info(
            "ingest.document.indexed",
            doc_id=doc.doc_id,
            chunks=len(points),
            host=HOSTNAME,
        )
    finally:
        clear_correlation_id()


async def main() -> None:
    log.info("ingest-worker.starting", rabbitmq=settings.rabbitmq_url)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    ollama = OllamaClient(base_url=settings.ollama_url)
    await ensure_qdrant_collection(qdrant)

    async with connect(settings.rabbitmq_url) as conn:
        async def handler(msg, payload):
            await handle_document(msg, payload, ollama, qdrant)

        log.info("ingest-worker.ready", queue=settings.queue_ingest_documents)
        await consume_forever(
            conn,
            settings.queue_ingest_documents,
            handler,
            prefetch=2,
        )


if __name__ == "__main__":
    asyncio.run(main())
```

> Nota técnica do plano: em B1 o worker faz parse → chunk → embed → upsert dentro do mesmo handler para simplificar. A separação em **2 filas** (`ingest.documents` → `ingest.chunks`) descrita no spec entra em B2.

---

## Task 12: Prompts mínimos versionados

**Files:**
- Create: `prompts/system_qa_pt.md`
- Create: `prompts/user_qa_template.md`

- [ ] **Step 1: Criar `prompts/system_qa_pt.md`**

```markdown
---
version: 0.1.0-b1
model_target: qwen2.5:7b-instruct
last_changed: 2026-05-09
notes: Versão mínima para o marco luz-verde do B1. Sem function calling ainda.
---

Você é um assistente especializado em engenharia de software. Responda à pergunta do usuário **estritamente** com base nos trechos de contexto fornecidos.

Regras:
1. Se o contexto não permite responder, diga "Não encontrei essa informação no corpus" e nada mais.
2. Cite explicitamente as fontes usadas no formato `[source: <arquivo>, page: <n>]` ao final de cada afirmação.
3. Responda em português brasileiro a menos que o usuário pergunte em outro idioma.
4. Seja conciso. Prefira 3-5 frases a parágrafos longos.
```

- [ ] **Step 2: Criar `prompts/user_qa_template.md`**

```markdown
---
version: 0.1.0-b1
model_target: qwen2.5:7b-instruct
last_changed: 2026-05-09
---

# Contexto

{% for c in context_blocks -%}
[source: {{ c.source }}, page: {{ c.page or "n/a" }}]
{{ c.text }}

{% endfor %}
# Pergunta

{{ question }}

# Resposta
```

---

## Task 13: Worker de query fim-a-fim

**Files:**
- Create: `src/workers/query/prompt_builder.py`
- Create: `src/workers/query/main.py`
- Create: `tests/unit/test_prompt_builder.py`

- [ ] **Step 1: Escrever teste falhando para `prompt_builder`**

`tests/unit/test_prompt_builder.py`:

```python
from src.workers.query.prompt_builder import build_prompt, ContextBlock


def test_build_prompt_includes_question_and_blocks():
    blocks = [
        ContextBlock(source="paper.pdf", page=2, text="Arquitetura hexagonal separa domínio."),
        ContextBlock(source="livro.md", page=None, text="Camadas de adaptadores."),
    ]
    prompt = build_prompt(question="O que é arquitetura hexagonal?", blocks=blocks, lang="pt")
    assert "arquitetura hexagonal" in prompt.lower()
    assert "paper.pdf" in prompt
    assert "Arquitetura hexagonal separa domínio." in prompt
    assert "Camadas de adaptadores." in prompt


def test_build_prompt_truncates_when_over_budget():
    blocks = [ContextBlock(source="x", page=1, text="x" * 50_000)]
    prompt = build_prompt(question="?", blocks=blocks, lang="pt", max_chars=8_000)
    assert len(prompt) <= 9_000  # alguma folga para system + user wrapper
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `uv run pytest tests/unit/test_prompt_builder.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `src/workers/query/prompt_builder.py`**

```python
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Template


_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


@dataclass
class ContextBlock:
    source: str
    page: int | None
    text: str


def _load(name: str) -> str:
    path = _PROMPTS_DIR / name
    raw = path.read_text(encoding="utf-8")
    # Remove frontmatter YAML simples (entre os primeiros dois "---")
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end != -1:
            raw = raw[end + 3 :].lstrip("\n")
    return raw


def build_prompt(
    question: str,
    blocks: list[ContextBlock],
    lang: str,
    max_chars: int = 24_000,
) -> str:
    system = _load(f"system_qa_{lang}.md") if lang in {"pt", "en"} else _load("system_qa_pt.md")
    user_tmpl = Template(_load("user_qa_template.md"))

    # Trunca blocos da cauda se ultrapassar orçamento
    truncated_blocks: list[ContextBlock] = []
    used = 0
    budget = max_chars - len(question) - len(system) - 500  # folga
    for b in blocks:
        remaining = budget - used
        if remaining <= 0:
            break
        if len(b.text) <= remaining:
            truncated_blocks.append(b)
            used += len(b.text)
        else:
            truncated_blocks.append(ContextBlock(source=b.source, page=b.page, text=b.text[:remaining]))
            break

    user = user_tmpl.render(question=question, context_blocks=truncated_blocks)
    return f"{system}\n\n{user}"
```

> Nota: precisa criar `prompts/system_qa_en.md` na Task 12 senão essa função quebra para queries em EN. Adicione um `system_qa_en.md` traduzido como o pt.

- [ ] **Step 4: Adicionar `prompts/system_qa_en.md`**

```markdown
---
version: 0.1.0-b1
model_target: qwen2.5:7b-instruct
last_changed: 2026-05-09
notes: B1 minimal version, English.
---

You are a software engineering assistant. Answer the user's question **strictly** based on the provided context snippets.

Rules:
1. If the context does not support an answer, say "I could not find this information in the corpus" and nothing else.
2. Cite sources explicitly as `[source: <file>, page: <n>]` at the end of each claim.
3. Answer in English if the user asked in English.
4. Be concise. 3-5 sentences are better than long paragraphs.
```

- [ ] **Step 5: Rodar — deve passar**

Run: `uv run pytest tests/unit/test_prompt_builder.py -v`
Expected: 2 passed.

- [ ] **Step 6: Implementar `src/workers/query/main.py`**

```python
import asyncio
import json
import socket
import time

import aio_pika
from langdetect import detect, LangDetectException
from qdrant_client import AsyncQdrantClient

from src.shared.config import settings
from src.shared.logging import bind_correlation_id, clear_correlation_id, configure_logging
from src.shared.messaging import connect, consume_forever
from src.shared.ollama_client import OllamaClient
from src.shared.schemas import Citation, QueryRequestMessage, QueryResponse
from src.workers.query.prompt_builder import ContextBlock, build_prompt


log = configure_logging("query-worker")
HOSTNAME = socket.gethostname()


async def handle_query(
    msg,
    payload: dict,
    ollama: OllamaClient,
    qdrant: AsyncQdrantClient,
    rabbit_conn,
) -> None:
    req = QueryRequestMessage.model_validate(payload)
    bind_correlation_id(req.correlation_id)
    started = time.perf_counter()
    try:
        log.info("query.received", question_len=len(req.question))

        try:
            lang = detect(req.question)
        except LangDetectException:
            lang = "pt"
        if lang not in {"pt", "en"}:
            lang = "pt"

        # 1) Embed da query
        q_vec = await ollama.embed(req.question, model=settings.embedding_model)

        # 2) Retrieval top-K (sem rerank em B1)
        hits = await qdrant.search(
            collection_name=settings.qdrant_collection,
            query_vector=q_vec,
            limit=max(req.top_k, 5),
        )
        log.info("query.retrieved", hits=len(hits))

        if not hits:
            answer_text = "Não encontrei essa informação no corpus" if lang == "pt" \
                else "I could not find this information in the corpus"
            response = QueryResponse(
                answer=answer_text,
                citations=[],
                usage={"tokens_in": 0, "tokens_out": 0},
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        else:
            blocks = [
                ContextBlock(
                    source=h.payload["source"],
                    page=h.payload.get("page"),
                    text=h.payload["text"],
                )
                for h in hits
            ]
            prompt = build_prompt(req.question, blocks, lang=lang)
            gen = await ollama.generate(
                prompt=prompt,
                model=settings.generation_model,
                options={
                    "temperature": settings.generation_temperature,
                    "num_ctx": settings.generation_num_ctx,
                },
            )
            citations = [
                Citation(
                    doc_id=h.payload["doc_id"],
                    chunk_id=h.payload["chunk_id"],
                    page=h.payload.get("page"),
                    snippet=h.payload["text"][:240],
                    source=h.payload["source"],
                )
                for h in hits[: req.top_k]
            ]
            response = QueryResponse(
                answer=gen["text"],
                citations=citations,
                usage={"tokens_in": gen["tokens_in"], "tokens_out": gen["tokens_out"]},
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        # 3) Publica no reply_to do gateway
        channel = await rabbit_conn.channel()
        try:
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=response.model_dump_json().encode(),
                    correlation_id=req.correlation_id,
                    content_type="application/json",
                ),
                routing_key=req.reply_to,
            )
        finally:
            await channel.close()

        log.info("query.responded", latency_ms=response.latency_ms, host=HOSTNAME)
    finally:
        clear_correlation_id()


async def main() -> None:
    log.info("query-worker.starting")
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    ollama = OllamaClient(base_url=settings.ollama_url)

    async with connect(settings.rabbitmq_url) as conn:
        async def handler(msg, payload):
            await handle_query(msg, payload, ollama, qdrant, conn)

        log.info("query-worker.ready", queue=settings.queue_query_requests)
        await consume_forever(
            conn,
            settings.queue_query_requests,
            handler,
            prefetch=1,
        )


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Task 14: Smoke test e Makefile

**Files:**
- Create: `scripts/smoke_test.py`
- Create: `Makefile`
- Create: `samples/exemplo.pdf` (qualquer PDF curto, manual)

- [ ] **Step 1: Adicionar PDF de teste em `samples/`**

Manualmente: copie qualquer PDF curto (1–5 páginas) sobre engenharia de software para `samples/exemplo.pdf`. Para B1 não importa o conteúdo exato.

- [ ] **Step 2: Implementar `scripts/smoke_test.py`**

```python
"""
Smoke test ponta-a-ponta do B1.

Pré-requisitos:
  1. docker compose --profile all up -d (ou make dev)
  2. Modelos Ollama já puxados:
       docker exec rag-ollama ollama pull nomic-embed-text
       docker exec rag-ollama ollama pull qwen2.5:7b-instruct  (ou llama3.2:1b para CPU)

Uso:
  uv run python scripts/smoke_test.py [--question "..."] [--file samples/exemplo.pdf]
"""
import argparse
import base64
import sys
import time
from pathlib import Path

import httpx


GATEWAY = "http://localhost:8000"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--file", default="samples/exemplo.pdf")
    p.add_argument("--question", default="Sobre o que fala este documento?")
    p.add_argument("--wait", type=float, default=30.0, help="segundos para indexação")
    args = p.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"ERRO: arquivo {path} não existe.", file=sys.stderr)
        return 2

    print(f"[smoke] health check em {GATEWAY}/health")
    h = httpx.get(f"{GATEWAY}/health", timeout=5)
    h.raise_for_status()
    assert h.json() == {"status": "ok"}, h.json()

    print(f"[smoke] enviando {path.name} para /ingest")
    content = base64.b64encode(path.read_bytes()).decode()
    r = httpx.post(
        f"{GATEWAY}/ingest",
        json={
            "filename": path.name,
            "content_b64": content,
            "source_type": "pdf" if path.suffix.lower() == ".pdf" else "md",
        },
        timeout=10,
    )
    r.raise_for_status()
    ingest = r.json()
    print(f"[smoke] aceito: doc_id={ingest['doc_id']}, correlation_id={ingest['correlation_id']}")

    print(f"[smoke] aguardando {args.wait}s para o ingest-worker indexar...")
    time.sleep(args.wait)

    print(f"[smoke] pergunta: {args.question!r}")
    started = time.perf_counter()
    r = httpx.post(
        f"{GATEWAY}/query",
        json={"question": args.question, "top_k": 3},
        timeout=180,
    )
    r.raise_for_status()
    resp = r.json()
    elapsed = time.perf_counter() - started

    print(f"[smoke] resposta em {elapsed:.1f}s, latency_ms={resp['latency_ms']}")
    print(f"[smoke] tokens_in={resp['usage']['tokens_in']} tokens_out={resp['usage']['tokens_out']}")
    print(f"[smoke] citations={len(resp['citations'])}")
    print("---")
    print(resp["answer"])
    print("---")
    if resp["citations"]:
        print("Citações:")
        for c in resp["citations"][:3]:
            print(f"  - {c['source']} (page {c.get('page', 'n/a')})")
    else:
        print("[smoke] AVISO: resposta sem citações.")

    if not resp["answer"].strip():
        print("[smoke] FALHA: resposta vazia.", file=sys.stderr)
        return 1
    print("[smoke] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Implementar `Makefile`**

```makefile
.PHONY: dev down logs smoke pull-models test lint clean

# Modo 1 — sobe tudo
dev:
	docker compose --profile all up -d --build
	@echo ""
	@echo "Serviços de pé:"
	@echo "  Gateway:        http://localhost:8000/docs"
	@echo "  RabbitMQ UI:    http://localhost:15672 (guest/guest)"
	@echo "  Qdrant:         http://localhost:6333/dashboard"
	@echo ""
	@echo "Próximo passo: make pull-models"

down:
	docker compose --profile all down

logs:
	docker compose --profile all logs -f --tail=200

# Puxa modelos no Ollama. Use MODEL=llama3.2:1b para CPU.
MODEL ?= qwen2.5:7b-instruct
pull-models:
	docker exec rag-ollama ollama pull nomic-embed-text
	docker exec rag-ollama ollama pull $(MODEL)

smoke:
	uv run python scripts/smoke_test.py

test:
	uv run pytest tests/unit -v

lint:
	uv run ruff check src tests

clean:
	docker compose --profile all down -v
	rm -rf .venv .pytest_cache .ruff_cache
```

- [ ] **Step 4: Documentar fluxo no README** (já feito na Task 1, atualize se quiser)

---

## Task 15: Validar marco luz-verde do B1

> Esta é a aceitação do bloco. Não tem código novo — só execução do smoke ponta-a-ponta.

- [ ] **Step 1: Subir serviços**

Run: `make dev`
Expected: containers `rag-rabbitmq`, `rag-qdrant`, `rag-redis`, `rag-ollama`, `rag-gateway`, `rag-ingest-worker`, `rag-query-worker` em estado `Up`.

- [ ] **Step 2: Puxar modelos**

Run com GPU: `make pull-models`
Run sem GPU: `make pull-models MODEL=llama3.2:1b` e edite `.env.local` adicionando `GENERATION_MODEL=llama3.2:1b`.

Expected: ambos os modelos baixados (alguns minutos).

- [ ] **Step 3: Confirmar healthcheck**

Run: `curl http://localhost:8000/health`
Expected: `{"status":"ok"}`.

- [ ] **Step 4: Confirmar UIs auxiliares**

Abra `http://localhost:15672` (guest/guest) — confirma que filas `ingest.documents`, `ingest.chunks`, `query.requests` estão declaradas.

Abra `http://localhost:6333/dashboard` — confirma que Qdrant responde.

- [ ] **Step 5: Rodar smoke**

Run: `make smoke`
Expected:
- Imprime `[smoke] OK`.
- A "resposta" contém algo relacionado ao conteúdo do PDF de teste.
- Pelo menos 1 citação na resposta.
- `latency_ms` registrado.

- [ ] **Step 6: Capturar evidência para o doc técnico**

Salve em `data/b1-smoke.txt` a saída completa do smoke + o output de `docker logs rag-ingest-worker --tail 50` mostrando as linhas JSON estruturadas. Vai virar evidência do marco no doc técnico.

- [ ] **Step 7: Marco atingido**

Critérios de aceite (todos devem passar):
- ✅ `make dev` sobe sem erros.
- ✅ `make test` passa (todos os unit tests).
- ✅ `make smoke` passa.
- ✅ Logs JSON estruturados visíveis em `docker logs`.
- ✅ Pelo menos 1 chunk indexado no Qdrant (verifique no dashboard).

Quando todos passarem: **B1 concluído**. Próximo passo: pedir para Claude gerar o plano de B2 (Pipeline Completo).

---

## Notas de execução paralela (Trilhas A/B/C)

Sugestão de divisão durante o B1 (3 dias) para minimizar lockstep:

- **Trilha A (autor / PC1):** Tasks 1, 2, 3, 7, 8, 12 (config, logging, schemas, compose, gateway, prompts).
- **Trilha B (colega 1):** Tasks 4, 5, 6, 9, 10, 11, 13 (schemas wider, ollama client, messaging, chunking, parsing, ingest+query workers).
- **Trilha C (colega 2):** Tasks 14, 15 + bootstrap manual de Tailscale + Docker nos PCs (em paralelo, fora deste plano — vira input do B3).

A ordem rígida do plano garante TDD; a divisão por trilhas é só sugestão de quem executa cada uma. Algumas tasks dependem de outras (B → A para configs/schemas), então considere pareamento nos primeiros dias.
