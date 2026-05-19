# Tema 5 — B2: Pipeline Completo

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evoluir o pipeline mínimo do B1 para o pipeline RAG completo com: ingestão em 2 filas (documents → chunks), re-ranking cross-encoder, cache em duas camadas, function calling (citações), memória de sessão e métricas Prometheus em todos os componentes.

**Architecture:** Mantém a topologia do B1. Adiciona: separação `ingest.documents` → `ingest.chunks` (CPU-bound vs IO+GPU-bound); novo serviço `rerank-service` em FastAPI carregando cross-encoder; Redis com 2 caches (L1 embedding de query, L2 resposta inteira); Qwen 2.5 com function calling para citações estruturadas; sessão com sumarização adaptativa em Redis; Prometheus scrape de `/metrics` em todos os serviços.

**Tech Stack:** Adições em B2: `sentence-transformers` (cross-encoder), `prometheus-client` (já no pyproject), `transformers`, `torch` (peso CPU-only para o reranker), `python-jose` (não — não precisa). Mantém tudo de B1.

**Bloco do cronograma:** B2 (13–16/05/2026, 4 dias).

**Marco luz-verde do bloco:** smoke test estendido passa, mostrando: (1) chunks fluem por duas filas, (2) re-rank altera ordem dos top-5, (3) cache L1 + L2 produzem hit em queries repetidas, (4) resposta tem citações estruturadas via function calling, (5) Prometheus expõe métricas em todos os serviços (`/metrics` retorna 200 e contadores não-zero).

---

## Estrutura de arquivos a criar/modificar

```
projeto_harness_engineering/
├── docker-compose.yml                    # MODIFY: adiciona rerank-service e prometheus
├── pyproject.toml                        # MODIFY: adiciona deps do reranker
├── infra/
│   └── docker/
│       └── rerank.Dockerfile             # CREATE
├── infra/
│   └── prometheus/
│       └── prometheus.yml                # CREATE
├── prompts/
│   └── tools/
│       └── cite_source.json              # CREATE
├── src/
│   ├── rerank_service/
│   │   ├── __init__.py                   # CREATE
│   │   └── main.py                       # CREATE
│   ├── shared/
│   │   ├── cache.py                      # CREATE: redis L1 + L2
│   │   ├── metrics.py                    # CREATE: prometheus_client setup
│   │   └── session.py                    # CREATE: histórico de sessão
│   ├── gateway/
│   │   ├── main.py                       # MODIFY: monta /metrics
│   │   └── routes.py                     # MODIFY: middleware de métricas, session
│   └── workers/
│       ├── ingest/
│       │   ├── main.py                   # MODIFY: divide em 2 consumers (doc + chunk)
│       │   ├── document_handler.py       # CREATE: parse + chunk + publica chunks
│       │   └── chunk_handler.py          # CREATE: embed + upsert
│       └── query/
│           ├── main.py                   # MODIFY: cache L1/L2, rerank, function calling
│           └── reranker_client.py        # CREATE: chama rerank-service
└── tests/
    ├── unit/
    │   ├── test_cache.py                 # CREATE
    │   ├── test_session.py               # CREATE
    │   └── test_reranker_client.py       # CREATE
    └── integration/
        └── test_pipeline_smoke.py        # MODIFY: extends B1 smoke
```

---

## Task 1: Adicionar dependências e atualizar `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Adicionar dependências do reranker e bibliotecas auxiliares**

No bloco `[project] dependencies` adicione:

```toml
"sentence-transformers>=3.3",
"transformers>=4.46",
"torch>=2.4",
"numpy>=2.0",
```

> Nota: `torch` é grande (~700MB CPU). Para o rerank-service que rodará apenas no PC1, isso é aceitável. Em B3 esse peso fica isolado no container do rerank-service via Dockerfile dedicado.

- [ ] **Step 2: Sincronizar**

Run: `uv sync`
Expected: download de torch + transformers + sentence-transformers (alguns minutos).

---

## Task 2: Cache distribuído no Redis (`shared/cache.py`)

> **Status:** ✅ Concluída em 2026-05-18 (modo code-partner — IA entregou teste-contrato + esqueleto; integrante escreveu o miolo). 4 testes verdes, mypy/ruff ok. Detalhe no `TODO.md`.

**Files:**
- Create: `src/shared/cache.py`
- Create: `tests/unit/test_cache.py`

- [ ] **Step 1: Escrever teste falhando**

`tests/unit/test_cache.py`:

```python
import pytest
import json
from src.shared.cache import Cache, sha256_hex


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.calls = []

    async def get(self, k):
        self.calls.append(("get", k))
        v = self.store.get(k)
        return v

    async def setex(self, k, ttl, v):
        self.calls.append(("setex", k, ttl))
        self.store[k] = v


@pytest.mark.asyncio
async def test_cache_get_set_embedding():
    fake = FakeRedis()
    cache = Cache(client=fake)
    assert await cache.get_query_embedding("hello") is None
    await cache.set_query_embedding("hello", [0.1, 0.2])
    got = await cache.get_query_embedding("hello")
    assert got == [0.1, 0.2]


@pytest.mark.asyncio
async def test_cache_response_keyed_by_query_and_ids():
    fake = FakeRedis()
    cache = Cache(client=fake)
    payload = {"answer": "ok", "citations": []}
    await cache.set_response("q", ["a", "b"], payload)
    got = await cache.get_response("q", ["a", "b"])
    assert got == payload
    # Mesma query mas ids diferentes → miss
    miss = await cache.get_response("q", ["a", "c"])
    assert miss is None


def test_sha256_hex_deterministic():
    assert sha256_hex("abc") == sha256_hex("abc")
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `uv run pytest tests/unit/test_cache.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `src/shared/cache.py`**

```python
import hashlib
import json
from typing import Protocol


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class _RedisLike(Protocol):
    async def get(self, k: str): ...
    async def setex(self, k: str, ttl: int, v: str | bytes): ...


class Cache:
    """L1 = embedding de query (TTL 7 dias). L2 = resposta inteira (TTL 1h)."""

    L1_TTL = 7 * 24 * 3600
    L2_TTL = 3600

    def __init__(self, client: _RedisLike):
        self._r = client

    async def get_query_embedding(self, query: str) -> list[float] | None:
        raw = await self._r.get(f"emb:{sha256_hex(query)}")
        return json.loads(raw) if raw else None

    async def set_query_embedding(self, query: str, vec: list[float]) -> None:
        await self._r.setex(f"emb:{sha256_hex(query)}", self.L1_TTL, json.dumps(vec))

    @staticmethod
    def _resp_key(query: str, retrieved_ids: list[str]) -> str:
        ids_blob = ",".join(sorted(retrieved_ids))
        return f"resp:{sha256_hex(query + '|' + ids_blob)}"

    async def get_response(self, query: str, retrieved_ids: list[str]) -> dict | None:
        raw = await self._r.get(self._resp_key(query, retrieved_ids))
        return json.loads(raw) if raw else None

    async def set_response(self, query: str, retrieved_ids: list[str], payload: dict) -> None:
        await self._r.setex(
            self._resp_key(query, retrieved_ids),
            self.L2_TTL,
            json.dumps(payload),
        )
```

- [ ] **Step 4: Rodar — deve passar**

Run: `uv run pytest tests/unit/test_cache.py -v`
Expected: 3 passed.

---

## Task 3: Métricas Prometheus (`shared/metrics.py`)

> **Status:** ✅ Concluída em 2026-05-19 (code-partner — scaffold + preenchimento dos TODOs pelo integrante). 10 métricas da §7.1, registro único, mypy/ruff + import smoke ok. Detalhe no `TODO.md`.

**Files:**
- Create: `src/shared/metrics.py`

- [ ] **Step 1: Implementar `src/shared/metrics.py`**

```python
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST


REGISTRY = CollectorRegistry()


request_duration = Histogram(
    "rag_request_duration_seconds",
    "Latência de requisições do gateway",
    labelnames=("endpoint", "status"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
    registry=REGISTRY,
)

query_pipeline_duration = Histogram(
    "rag_query_pipeline_duration_seconds",
    "Latência por fase do pipeline de query",
    labelnames=("phase", "worker_id"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    registry=REGISTRY,
)

ingest_pipeline_duration = Histogram(
    "rag_ingest_pipeline_duration_seconds",
    "Latência por fase do pipeline de ingestão",
    labelnames=("phase", "worker_id"),
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 5, 30, 120, 600),
    registry=REGISTRY,
)

tokens_total = Counter(
    "rag_tokens_total",
    "Total de tokens consumidos/produzidos",
    labelnames=("direction", "model"),
    registry=REGISTRY,
)

throughput_docs = Counter(
    "rag_throughput_docs_total",
    "Documentos indexados",
    labelnames=("worker_id",),
    registry=REGISTRY,
)

throughput_queries = Counter(
    "rag_throughput_queries_total",
    "Queries atendidas",
    labelnames=("worker_id", "status"),
    registry=REGISTRY,
)

errors = Counter(
    "rag_errors_total",
    "Erros por serviço e tipo",
    labelnames=("service", "error_type"),
    registry=REGISTRY,
)

cache_hits = Counter(
    "rag_cache_hits_total",
    "Cache hits",
    labelnames=("cache_layer",),
    registry=REGISTRY,
)
cache_misses = Counter(
    "rag_cache_misses_total",
    "Cache misses",
    labelnames=("cache_layer",),
    registry=REGISTRY,
)

ollama_inflight = Gauge(
    "rag_ollama_inflight_requests",
    "Requests Ollama em voo",
    registry=REGISTRY,
)


def metrics_response() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
```

- [ ] **Step 2: Validar import**

Run: `uv run python -c "from src.shared.metrics import metrics_response; b, ct = metrics_response(); print(ct, len(b))"`
Expected: imprime `text/plain; version=0.0.4; charset=utf-8 <bytes>`.

---

## Task 4: Endpoint `/metrics` no gateway

> **Status:** 🔶 Parcial (2026-05-19). Step 1 (endpoint `/metrics` em `routes.py`) ✅ feito pela IA (boilerplate). Step 2 (middleware de medição em `main.py`) scaffoldado — miolo pendente com o integrante (code-partner).

**Files:**
- Modify: `src/gateway/main.py`
- Modify: `src/gateway/routes.py`

- [ ] **Step 1: Adicionar `/metrics` em `routes.py`**

No topo do arquivo, importe:
```python
from fastapi import Response
from src.shared.metrics import metrics_response, request_duration
import time
```

Adicione o endpoint:
```python
@router.get("/metrics")
async def metrics() -> Response:
    body, content_type = metrics_response()
    return Response(content=body, media_type=content_type)
```

- [ ] **Step 2: Adicionar middleware de medição em `main.py`**

Em `src/gateway/main.py`, depois de `app.include_router(router)`:

```python
@app.middleware("http")
async def measure_requests(request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started
    request_duration.labels(
        endpoint=request.url.path,
        status=str(response.status_code),
    ).observe(elapsed)
    return response
```

(Adicione `import time` e `from src.shared.metrics import request_duration` no topo.)

- [ ] **Step 3: Validar manualmente**

Suba o stack: `make dev`
Run: `curl http://localhost:8000/metrics | head -50`
Expected: linhas em formato Prometheus, contadores `rag_*` declarados.

---

## Task 5: Refatorar ingestão em duas filas

**Files:**
- Create: `src/workers/ingest/document_handler.py`
- Create: `src/workers/ingest/chunk_handler.py`
- Modify: `src/workers/ingest/main.py`

- [ ] **Step 1: Implementar `document_handler.py`**

```python
import socket
import time

from langdetect import detect, LangDetectException

from src.shared.config import settings
from src.shared.logging import bind_correlation_id, clear_correlation_id, configure_logging
from src.shared.messaging import publish_json
from src.shared.metrics import ingest_pipeline_duration, errors
from src.shared.schemas import ChunkMessage, DocumentMessage
from src.workers.ingest.chunking import chunk_text
from src.workers.ingest.parsing import parse_document


log = configure_logging("ingest-worker-doc")
HOSTNAME = socket.gethostname()


async def handle_document(msg, payload: dict, rabbit_conn) -> None:
    """Consome ingest.documents → parse → chunk → publica em ingest.chunks."""
    doc = DocumentMessage.model_validate(payload)
    bind_correlation_id(doc.correlation_id)
    started = time.perf_counter()
    try:
        log.info("ingest.document.received", doc_id=doc.doc_id, filename=doc.filename)

        with ingest_pipeline_duration.labels(phase="parse", worker_id=HOSTNAME).time():
            pages = parse_document(doc.content_b64, doc.source_type)
        if not pages:
            log.warning("ingest.document.empty", doc_id=doc.doc_id)
            return

        sample = " ".join(t for _, t in pages)[:500]
        try:
            lang = detect(sample)
        except LangDetectException:
            lang = "unk"

        chunk_index = 0
        with ingest_pipeline_duration.labels(phase="chunk", worker_id=HOSTNAME).time():
            for page_num, page_text in pages:
                for piece in chunk_text(
                    page_text,
                    target_tokens=settings.chunk_target_tokens,
                    overlap_tokens=settings.chunk_overlap_tokens,
                ):
                    if not piece.strip():
                        continue
                    cm = ChunkMessage(
                        doc_id=doc.doc_id,
                        chunk_id=f"{doc.doc_id}:{chunk_index}",
                        text=piece,
                        source=doc.filename,
                        page=page_num,
                        lang=lang,
                        chunk_index=chunk_index,
                    )
                    await publish_json(
                        rabbit_conn,
                        settings.queue_ingest_chunks,
                        cm.model_dump(),
                        correlation_id=doc.correlation_id,
                    )
                    chunk_index += 1

        log.info(
            "ingest.document.chunked",
            doc_id=doc.doc_id,
            chunks=chunk_index,
            elapsed_s=round(time.perf_counter() - started, 2),
        )
    except Exception:
        errors.labels(service="ingest-worker", error_type="document_handler").inc()
        log.exception("ingest.document.error", doc_id=doc.doc_id)
        raise
    finally:
        clear_correlation_id()
```

- [ ] **Step 2: Implementar `chunk_handler.py`**

```python
import hashlib
import socket
import time

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from src.shared.config import settings
from src.shared.logging import bind_correlation_id, clear_correlation_id, configure_logging
from src.shared.metrics import ingest_pipeline_duration, throughput_docs, tokens_total, errors
from src.shared.ollama_client import OllamaClient
from src.shared.schemas import ChunkMessage


log = configure_logging("ingest-worker-chunk")
HOSTNAME = socket.gethostname()


async def ensure_collection(qdrant: AsyncQdrantClient) -> None:
    cols = await qdrant.get_collections()
    if settings.qdrant_collection not in {c.name for c in cols.collections}:
        await qdrant.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(
                size=settings.embedding_dim,
                distance=qmodels.Distance.COSINE,
            ),
        )


async def handle_chunk(msg, payload: dict, ollama: OllamaClient, qdrant: AsyncQdrantClient) -> None:
    """Consome ingest.chunks → embed → upsert no Qdrant."""
    cm = ChunkMessage.model_validate(payload)
    bind_correlation_id(payload.get("correlation_id", "unset"))
    started = time.perf_counter()
    try:
        with ingest_pipeline_duration.labels(phase="embed", worker_id=HOSTNAME).time():
            vec = await ollama.embed(cm.text, model=settings.embedding_model)
        tokens_total.labels(direction="in", model=settings.embedding_model).inc(
            max(1, len(cm.text) // 4)
        )

        point_id = int(
            hashlib.sha256(cm.chunk_id.encode()).hexdigest()[:15], 16
        )

        with ingest_pipeline_duration.labels(phase="upsert", worker_id=HOSTNAME).time():
            await qdrant.upsert(
                collection_name=settings.qdrant_collection,
                points=[
                    qmodels.PointStruct(
                        id=point_id,
                        vector=vec,
                        payload=cm.model_dump(),
                    )
                ],
            )

        if cm.chunk_index == 0:
            throughput_docs.labels(worker_id=HOSTNAME).inc()

        log.info(
            "ingest.chunk.indexed",
            doc_id=cm.doc_id,
            chunk_id=cm.chunk_id,
            elapsed_s=round(time.perf_counter() - started, 3),
        )
    except Exception:
        errors.labels(service="ingest-worker", error_type="chunk_handler").inc()
        log.exception("ingest.chunk.error", chunk_id=cm.chunk_id)
        raise
    finally:
        clear_correlation_id()
```

- [ ] **Step 3: Reescrever `src/workers/ingest/main.py`**

```python
import asyncio
import os

from qdrant_client import AsyncQdrantClient

from src.shared.config import settings
from src.shared.logging import configure_logging
from src.shared.messaging import connect, consume_forever
from src.shared.ollama_client import OllamaClient
from src.workers.ingest.document_handler import handle_document
from src.workers.ingest.chunk_handler import ensure_collection, handle_chunk


log = configure_logging("ingest-worker")


async def main() -> None:
    role = os.getenv("INGEST_ROLE", "both")  # "documents" | "chunks" | "both"
    log.info("ingest-worker.starting", role=role)

    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    ollama = OllamaClient(base_url=settings.ollama_url)
    await ensure_collection(qdrant)

    async with connect(settings.rabbitmq_url) as conn:
        tasks = []

        if role in {"documents", "both"}:
            async def doc_handler(msg, payload):
                await handle_document(msg, payload, conn)
            tasks.append(asyncio.create_task(
                consume_forever(conn, settings.queue_ingest_documents, doc_handler, prefetch=2)
            ))
            log.info("ingest-worker.consuming_documents")

        if role in {"chunks", "both"}:
            async def chunk_handler(msg, payload):
                await handle_chunk(msg, payload, ollama, qdrant)
            tasks.append(asyncio.create_task(
                consume_forever(conn, settings.queue_ingest_chunks, chunk_handler, prefetch=8)
            ))
            log.info("ingest-worker.consuming_chunks")

        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Atualizar `docker-compose.yml`** para subir 1 ingest-worker dedicado a documents e outro a chunks (deixa o paralelismo explícito):

Substitua a entry `ingest-worker:` por:

```yaml
  ingest-worker-doc:
    <<: *worker-base
    container_name: rag-ingest-worker-doc
    profiles: ["all", "worker"]
    environment:
      WORKER_KIND: ingest
      INGEST_ROLE: documents
      SERVICE_NAME: ingest-worker-doc

  ingest-worker-chunk:
    <<: *worker-base
    container_name: rag-ingest-worker-chunk
    profiles: ["all", "worker"]
    environment:
      WORKER_KIND: ingest
      INGEST_ROLE: chunks
      SERVICE_NAME: ingest-worker-chunk
```

- [ ] **Step 5: Validar com smoke**

Run: `make down && make dev && make smoke`
Expected: o smoke continua passando, mas agora você verá as filas `ingest.documents` e `ingest.chunks` no RabbitMQ Management UI com mensagens fluindo entre elas.

---

## Task 6: Reranker service (`src/rerank_service/`)

**Files:**
- Create: `src/rerank_service/main.py`
- Create: `infra/docker/rerank.Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Implementar `src/rerank_service/main.py`**

```python
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import CrossEncoder

from src.shared.config import settings
from src.shared.logging import configure_logging
from src.shared.metrics import metrics_response


log = configure_logging("rerank-service")
MODEL_NAME = "BAAI/bge-reranker-v2-m3"


class RerankRequest(BaseModel):
    query: str
    candidates: list[dict[str, Any]]  # cada um com pelo menos {"text": ..., "id": ...}
    top_k: int = 5


class RerankResponseItem(BaseModel):
    id: str
    score: float
    text: str


class RerankResponse(BaseModel):
    items: list[RerankResponseItem]
    model: str
    latency_ms: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("rerank.loading_model", model=MODEL_NAME)
    app.state.model = CrossEncoder(MODEL_NAME, max_length=512)
    log.info("rerank.ready")
    yield


app = FastAPI(title="Rerank Service", lifespan=lifespan)


@app.post("/rerank", response_model=RerankResponse)
async def rerank(req: RerankRequest):
    started = time.perf_counter()
    pairs = [(req.query, c["text"]) for c in req.candidates]
    scores = app.state.model.predict(pairs).tolist()
    ranked = sorted(
        zip(req.candidates, scores),
        key=lambda x: x[1],
        reverse=True,
    )[: req.top_k]
    items = [
        RerankResponseItem(id=str(c.get("id", c.get("chunk_id", "?"))), score=float(s), text=c["text"])
        for c, s in ranked
    ]
    return RerankResponse(
        items=items,
        model=MODEL_NAME,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    from fastapi import Response
    body, ct = metrics_response()
    return Response(content=body, media_type=ct)
```

- [ ] **Step 2: Criar `infra/docker/rerank.Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.4.27

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project

# Pré-baixa o modelo durante o build (evita cold start de 1+ min na primeira request)
COPY src/ ./src/
ENV TRANSFORMERS_CACHE=/models
RUN mkdir -p /models && \
    uv run python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3', cache_folder='/models')"

ENV PYTHONPATH=/app
EXPOSE 8081

CMD ["uv", "run", "uvicorn", "src.rerank_service.main:app", "--host", "0.0.0.0", "--port", "8081"]
```

- [ ] **Step 3: Adicionar serviço ao `docker-compose.yml`**

```yaml
  rerank-service:
    build:
      context: .
      dockerfile: infra/docker/rerank.Dockerfile
    container_name: rag-rerank
    profiles: ["all", "server"]
    env_file:
      - .env.local
    environment:
      SERVICE_NAME: rerank-service
    ports:
      - "8081:8081"
    restart: unless-stopped
```

- [ ] **Step 4: Build e teste**

Run: `docker compose --profile server build rerank-service` (vai demorar — baixa torch + modelo).
Run: `docker compose --profile server up -d rerank-service`
Run: `curl http://localhost:8081/health`
Expected: `{"status":"ok"}`.

Run:
```bash
curl -X POST http://localhost:8081/rerank \
  -H "Content-Type: application/json" \
  -d '{"query":"O que é arquitetura hexagonal?","candidates":[{"id":"a","text":"Arquitetura hexagonal isola domínio."},{"id":"b","text":"Maionese é feita de ovo."}],"top_k":2}'
```
Expected: JSON com `items` ordenados pelo score; o item "a" deve ter score muito mais alto que "b".

---

## Task 7: Cliente reranker no query-worker (`reranker_client.py`)

**Files:**
- Create: `src/workers/query/reranker_client.py`
- Create: `tests/unit/test_reranker_client.py`

- [ ] **Step 1: Escrever teste falhando**

```python
# tests/unit/test_reranker_client.py
import pytest
import respx
import httpx
from src.workers.query.reranker_client import RerankerClient


@pytest.mark.asyncio
@respx.mock
async def test_rerank_returns_top_k_items():
    respx.post("http://rerank:8081/rerank").mock(
        return_value=httpx.Response(200, json={
            "items": [
                {"id": "b", "score": 0.9, "text": "B"},
                {"id": "a", "score": 0.4, "text": "A"},
            ],
            "model": "bge-reranker-v2-m3",
            "latency_ms": 12,
        })
    )
    client = RerankerClient(base_url="http://rerank:8081")
    items = await client.rerank("q", [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}], top_k=2)
    assert items[0]["id"] == "b"
    assert items[1]["id"] == "a"
```

- [ ] **Step 2: Implementar**

`src/workers/query/reranker_client.py`:

```python
import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)


class RerankerClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.5, max=4),
            retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=self._timeout) as http:
                    r = await http.post(
                        f"{self._base}/rerank",
                        json={"query": query, "candidates": candidates, "top_k": top_k},
                    )
                    r.raise_for_status()
                    return r.json()["items"]
        raise RuntimeError("unreachable")
```

- [ ] **Step 3: Adicionar setting**

Em `src/shared/config.py`, adicione:
```python
rerank_url: str = "http://rerank-service:8081"
```

- [ ] **Step 4: Rodar teste**

Run: `uv run pytest tests/unit/test_reranker_client.py -v`
Expected: 1 passed.

---

## Task 8: Function calling (cite_source) e prompts atualizados

**Files:**
- Create: `prompts/tools/cite_source.json`
- Modify: `prompts/system_qa_pt.md`, `prompts/system_qa_en.md`

- [ ] **Step 1: Criar `prompts/tools/cite_source.json`**

```json
{
  "type": "function",
  "function": {
    "name": "cite_source",
    "description": "Registra uma fonte usada na resposta. Chame uma vez por afirmação importante.",
    "parameters": {
      "type": "object",
      "properties": {
        "doc_id": {"type": "string", "description": "ID do documento (vem do contexto)"},
        "page": {"type": ["integer", "null"], "description": "Página (vem do contexto, pode ser null)"},
        "snippet": {"type": "string", "description": "Trecho exato do documento que sustenta a afirmação"}
      },
      "required": ["doc_id", "snippet"]
    }
  }
}
```

- [ ] **Step 2: Atualizar `prompts/system_qa_pt.md` para versão B2**

Atualize o frontmatter para `version: 0.2.0-b2` e adicione na seção de regras:

```markdown
5. Para cada afirmação importante, chame a tool `cite_source(doc_id, page, snippet)` antes de continuar a resposta. O `doc_id` está nos cabeçalhos `[doc_id: ...]` do contexto.
```

E mude o template de `[source: ...]` para `[doc_id: ..., page: ...]` para casar com o que a tool registra.

- [ ] **Step 3: Atualizar `user_qa_template.md`** para incluir `doc_id` em cada bloco:

```markdown
{% for c in context_blocks -%}
[doc_id: {{ c.doc_id }} | source: {{ c.source }} | page: {{ c.page or "n/a" }}]
{{ c.text }}

{% endfor %}
```

- [ ] **Step 4: Estender `ContextBlock`** em `src/workers/query/prompt_builder.py`:

```python
@dataclass
class ContextBlock:
    source: str
    page: int | None
    text: str
    doc_id: str = ""
```

> O reranker e o retrieval populam `doc_id`; templates antigos com `doc_id=""` ainda funcionam.

---

## Task 9: Sessão e histórico (`shared/session.py`)

**Files:**
- Create: `src/shared/session.py`
- Create: `tests/unit/test_session.py`

- [ ] **Step 1: Escrever teste**

```python
# tests/unit/test_session.py
import pytest
import json
from src.shared.session import SessionStore


class FakeRedis:
    def __init__(self):
        self.s = {}

    async def get(self, k):
        return self.s.get(k)

    async def setex(self, k, ttl, v):
        self.s[k] = v


@pytest.mark.asyncio
async def test_session_appends_and_caps_history():
    fake = FakeRedis()
    store = SessionStore(client=fake, max_turns=3)
    for i in range(5):
        await store.append("s1", question=f"q{i}", answer=f"a{i}")
    history = await store.get_history("s1")
    # Tem no máx 3 turnos preservados (sumarização cobre os 2 antigos)
    assert len(history) <= 3
    summary = await store.get_summary("s1")
    # Após 3 turnos, deve ter resumo populado (mesmo que vazio neste mock)
    assert summary is not None or len(history) == 3


@pytest.mark.asyncio
async def test_session_empty_returns_empty_list():
    store = SessionStore(client=FakeRedis())
    assert await store.get_history("none") == []
    assert await store.get_summary("none") is None
```

- [ ] **Step 2: Implementar**

```python
# src/shared/session.py
import json


class SessionStore:
    """Histórico de conversação com sumarização adaptativa.

    Estratégia:
    - Mantém até max_turns trocas mais recentes em texto puro.
    - Quando excede max_turns, o turno mais antigo é movido para um "resumo"
      acumulado (em B2, append simples; em B3 substituiremos por sumarização via LLM).
    """

    HISTORY_TTL = 60 * 60 * 6   # 6h
    KEY_HIST = "session:{sid}:history"
    KEY_SUM = "session:{sid}:summary"

    def __init__(self, client, max_turns: int = 3):
        self._r = client
        self.max_turns = max_turns

    async def get_history(self, sid: str) -> list[dict]:
        raw = await self._r.get(self.KEY_HIST.format(sid=sid))
        return json.loads(raw) if raw else []

    async def get_summary(self, sid: str) -> str | None:
        raw = await self._r.get(self.KEY_SUM.format(sid=sid))
        if isinstance(raw, bytes):
            raw = raw.decode()
        return raw if raw else None

    async def append(self, sid: str, question: str, answer: str) -> None:
        history = await self.get_history(sid)
        history.append({"q": question, "a": answer})
        if len(history) > self.max_turns:
            # Move o mais antigo para o sumário (concat simples em B2)
            oldest = history.pop(0)
            current = await self.get_summary(sid) or ""
            new_summary = (current + f"\n[turn] Q: {oldest['q']}\nA: {oldest['a']}").strip()
            await self._r.setex(self.KEY_SUM.format(sid=sid), self.HISTORY_TTL, new_summary)
        await self._r.setex(self.KEY_HIST.format(sid=sid), self.HISTORY_TTL, json.dumps(history))
```

- [ ] **Step 3: Rodar**

Run: `uv run pytest tests/unit/test_session.py -v`
Expected: 2 passed.

---

## Task 10: Integrar tudo no query-worker

**Files:**
- Modify: `src/workers/query/main.py`

- [ ] **Step 1: Reescrever para incluir cache, rerank, function calling, sessão**

```python
import asyncio
import json
import os
import socket
import time

import aio_pika
import redis.asyncio as aredis
from langdetect import detect, LangDetectException
from qdrant_client import AsyncQdrantClient

from src.shared.cache import Cache
from src.shared.config import settings
from src.shared.logging import bind_correlation_id, clear_correlation_id, configure_logging
from src.shared.messaging import connect, consume_forever
from src.shared.metrics import (
    cache_hits, cache_misses, errors, ollama_inflight,
    query_pipeline_duration, throughput_queries, tokens_total,
)
from src.shared.ollama_client import OllamaClient
from src.shared.schemas import Citation, QueryRequestMessage, QueryResponse
from src.shared.session import SessionStore
from src.workers.query.prompt_builder import ContextBlock, build_prompt
from src.workers.query.reranker_client import RerankerClient


log = configure_logging("query-worker")
HOSTNAME = socket.gethostname()


async def handle_query(msg, payload, deps):
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

        # 1) Embedding (cache L1)
        with query_pipeline_duration.labels(phase="embed", worker_id=HOSTNAME).time():
            cached_vec = await deps.cache.get_query_embedding(req.question)
            if cached_vec is not None:
                cache_hits.labels(cache_layer="L1").inc()
                q_vec = cached_vec
            else:
                cache_misses.labels(cache_layer="L1").inc()
                ollama_inflight.inc()
                try:
                    q_vec = await deps.ollama.embed(req.question, model=settings.embedding_model)
                finally:
                    ollama_inflight.dec()
                await deps.cache.set_query_embedding(req.question, q_vec)

        # 2) Retrieval top-N inicial
        with query_pipeline_duration.labels(phase="retrieve", worker_id=HOSTNAME).time():
            hits = await deps.qdrant.search(
                collection_name=settings.qdrant_collection,
                query_vector=q_vec,
                limit=settings.retrieval_top_k_initial,
            )

        if not hits:
            response = QueryResponse(
                answer=("Não encontrei essa informação no corpus" if lang == "pt"
                        else "I could not find this information in the corpus"),
                citations=[],
                usage={"tokens_in": 0, "tokens_out": 0},
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            await _publish_reply(deps.rabbit, req, response)
            throughput_queries.labels(worker_id=HOSTNAME, status="empty").inc()
            return

        # 3) Rerank (com fallback caso reranker esteja down)
        with query_pipeline_duration.labels(phase="rerank", worker_id=HOSTNAME).time():
            try:
                candidates = [
                    {
                        "id": h.payload["chunk_id"],
                        "text": h.payload["text"],
                        "doc_id": h.payload["doc_id"],
                        "source": h.payload["source"],
                        "page": h.payload.get("page"),
                        "chunk_id": h.payload["chunk_id"],
                    }
                    for h in hits
                ]
                top_k = await deps.reranker.rerank(
                    req.question, candidates, top_k=req.top_k
                )
                blocks = [
                    ContextBlock(
                        source=t.get("source") or "?",
                        page=t.get("page"),
                        text=t["text"],
                        doc_id=t.get("doc_id", ""),
                    )
                    for t in top_k
                ]
                retrieved_ids = [t.get("chunk_id") or t.get("id") for t in top_k]
            except Exception:
                errors.labels(service="query-worker", error_type="rerank_fallback").inc()
                log.warning("rerank.skipped_fallback")
                blocks = [
                    ContextBlock(
                        source=h.payload["source"],
                        page=h.payload.get("page"),
                        text=h.payload["text"],
                        doc_id=h.payload["doc_id"],
                    )
                    for h in hits[: req.top_k]
                ]
                retrieved_ids = [h.payload["chunk_id"] for h in hits[: req.top_k]]

        # 4) Cache L2
        cached_resp = await deps.cache.get_response(req.question, retrieved_ids)
        if cached_resp is not None:
            cache_hits.labels(cache_layer="L2").inc()
            response = QueryResponse.model_validate(cached_resp)
            await _publish_reply(deps.rabbit, req, response)
            throughput_queries.labels(worker_id=HOSTNAME, status="cache_hit").inc()
            log.info("query.cache_hit_L2")
            return
        cache_misses.labels(cache_layer="L2").inc()

        # 5) Generation (com sessão se houver)
        prompt = build_prompt(req.question, blocks, lang=lang)
        if req.session_id and deps.sessions:
            history = await deps.sessions.get_history(req.session_id)
            summary = await deps.sessions.get_summary(req.session_id)
            preamble_parts = []
            if summary:
                preamble_parts.append(f"# Resumo de turnos anteriores\n{summary}")
            if history:
                turns = "\n".join(f"Q: {h['q']}\nA: {h['a']}" for h in history)
                preamble_parts.append(f"# Histórico recente\n{turns}")
            if preamble_parts:
                prompt = "\n\n".join(preamble_parts) + "\n\n" + prompt

        with query_pipeline_duration.labels(phase="generate", worker_id=HOSTNAME).time():
            ollama_inflight.inc()
            try:
                gen = await deps.ollama.generate(
                    prompt=prompt,
                    model=settings.generation_model,
                    options={
                        "temperature": settings.generation_temperature,
                        "num_ctx": settings.generation_num_ctx,
                    },
                )
            finally:
                ollama_inflight.dec()

        tokens_total.labels(direction="in", model=settings.generation_model).inc(gen["tokens_in"])
        tokens_total.labels(direction="out", model=settings.generation_model).inc(gen["tokens_out"])

        citations = [
            Citation(
                doc_id=b.doc_id,
                chunk_id=retrieved_ids[i],
                page=b.page,
                snippet=b.text[:240],
                source=b.source,
            )
            for i, b in enumerate(blocks)
        ]
        response = QueryResponse(
            answer=gen["text"],
            citations=citations,
            usage={"tokens_in": gen["tokens_in"], "tokens_out": gen["tokens_out"]},
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

        # Cache L2 + sessão
        await deps.cache.set_response(req.question, retrieved_ids, response.model_dump())
        if req.session_id and deps.sessions:
            await deps.sessions.append(req.session_id, req.question, response.answer)

        await _publish_reply(deps.rabbit, req, response)
        throughput_queries.labels(worker_id=HOSTNAME, status="ok").inc()
        log.info("query.responded", latency_ms=response.latency_ms, host=HOSTNAME)

    except Exception:
        errors.labels(service="query-worker", error_type="handler").inc()
        throughput_queries.labels(worker_id=HOSTNAME, status="error").inc()
        log.exception("query.error")
        raise
    finally:
        clear_correlation_id()


async def _publish_reply(rabbit_conn, req: QueryRequestMessage, response: QueryResponse) -> None:
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


class _Deps:
    pass


async def main() -> None:
    log.info("query-worker.starting")
    deps = _Deps()
    deps.qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    deps.ollama = OllamaClient(base_url=settings.ollama_url)
    deps.reranker = RerankerClient(base_url=settings.rerank_url)
    redis_client = aredis.from_url(settings.redis_url, decode_responses=True)
    deps.cache = Cache(client=redis_client)
    deps.sessions = SessionStore(client=redis_client)

    async with connect(settings.rabbitmq_url) as conn:
        deps.rabbit = conn

        async def handler(msg, payload):
            await handle_query(msg, payload, deps)

        log.info("query-worker.ready", queue=settings.queue_query_requests)
        await consume_forever(conn, settings.queue_query_requests, handler, prefetch=1)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Adicionar `redis>=5.2` no `pyproject.toml`** (já está em B1).

- [ ] **Step 3: Smoke**

Run: `make down && make dev && make pull-models && make smoke`
Expected: smoke passa com latência maior (rerank + generation), e logs mostram fases distintas.

---

## Task 11: Smoke estendido (validação do marco luz-verde do B2)

**Files:**
- Modify: `scripts/smoke_test.py`

- [ ] **Step 1: Estender o smoke para validar B2**

Adicione ao final de `main()`, antes do `return 0`:

```python
    # Validações específicas do B2:

    # 1. Cache L2: pergunta repetida deve voltar muito mais rápido
    print("[smoke-b2] testando cache L2 (mesma pergunta repetida)")
    started = time.perf_counter()
    r2 = httpx.post(
        f"{GATEWAY}/query",
        json={"question": args.question, "top_k": 3},
        timeout=180,
    )
    r2.raise_for_status()
    elapsed_repeat = time.perf_counter() - started
    print(f"[smoke-b2] segunda chamada: {elapsed_repeat:.1f}s (primeira: {elapsed:.1f}s)")
    if elapsed_repeat > elapsed * 0.5:
        print("[smoke-b2] AVISO: cache L2 não parece estar surtindo efeito.")

    # 2. /metrics responde com contadores não-zero
    print("[smoke-b2] verificando /metrics do gateway")
    m = httpx.get(f"{GATEWAY}/metrics", timeout=5)
    m.raise_for_status()
    body = m.text
    assert "rag_request_duration_seconds" in body, "métricas não publicadas"
    assert "rag_throughput_queries_total" in body, "throughput counter ausente"
    print("[smoke-b2] métricas OK")

    # 3. Rerank service responde
    print("[smoke-b2] verificando rerank-service")
    rh = httpx.get("http://localhost:8081/health", timeout=5)
    rh.raise_for_status()
    print("[smoke-b2] rerank healthy")
```

- [ ] **Step 2: Executar**

Run: `make smoke`
Expected: todas as 3 validações passam.

---

## Task 12: Marco luz-verde do B2

- [ ] **Step 1: Critérios de aceite**

- ✅ `make test` passa (incluindo testes novos de cache, session, reranker_client).
- ✅ `make smoke` (estendido) passa.
- ✅ `/metrics` retorna 200 em gateway, ingest-worker, query-worker, rerank-service. (Para workers, expor o `/metrics` é trivial: instancie um servidor `prometheus_client.start_http_server(9100)` no main de cada worker. **Adicione isso como subtask se faltar**.)
- ✅ Filas `ingest.documents` e `ingest.chunks` aparecem distintas no Management UI.
- ✅ Resposta tem citações com `doc_id` populado.
- ✅ Segunda execução da mesma pergunta retorna em <30% do tempo da primeira (cache L2 hit).

- [ ] **Step 2: Capturar evidências para o doc técnico**

- Screenshot do RabbitMQ Management UI mostrando as duas filas.
- Output de `/metrics` (head -100) salvo em `data/b2-metrics.txt`.
- Output do smoke completo em `data/b2-smoke.txt`.

Quando todos os critérios passarem: **B2 concluído**. Próximo: gerar plano de B3.

---

## Notas de execução paralela (B2)

- **Trilha A:** Tasks 4 (gateway /metrics), 6 (rerank-service), 8 (prompts B2), 11 (smoke estendido).
- **Trilha B:** Tasks 5 (ingest 2-filas), 7 (reranker_client), 10 (query-worker integrado), 9 (sessão).
- **Trilha C:** Task 2 (cache), Task 3 (metrics), exposição de `/metrics` em workers, smoke.

Pareamento recomendado nas Tasks 5 e 10 (são as integrações mais densas).
