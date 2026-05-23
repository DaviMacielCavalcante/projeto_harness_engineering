"""Entrypoint do gateway FastAPI.

Responsabilidade: receber HTTP (`/ingest`, `/query`, `/health`), publicar
mensagens no RabbitMQ e — no caso de `/query` — aguardar resposta via
reply queue (padrão RPC).

A conexão com o RabbitMQ é aberta no startup (via `lifespan`) e armazenada
em `app.state.rabbitmq`, ficando disponível para as rotas via
`request.app.state.rabbitmq`.
"""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from qdrant_client import AsyncQdrantClient
from starlette.middleware.base import RequestResponseEndpoint

from src.gateway.routes import router
from src.shared.config import settings
from src.shared.logging import configure_logging
from src.shared.messaging import connect, declare_topology
from src.shared.metrics import request_duration
from src.shared.ollama_client import OllamaClient

log = configure_logging("gateway")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Ciclo de vida do app: conecta no RabbitMQ no startup, fecha no shutdown.

    Tudo antes do `yield` roda no startup; tudo depois roda no shutdown.
    A conexão fica viva durante toda a vida do app e é compartilhada com
    as rotas via `app.state.rabbitmq`.
    """
    log.info("gateway.starting", rabbitmq=settings.rabbitmq_url)

    async with connect(settings.rabbitmq_url) as conn:
        await declare_topology(
            conn,
            settings.queue_ingest_documents,
            settings.queue_ingest_chunks,
            settings.queue_query_requests,
        )
        app.state.rabbitmq = conn

        app.state.qdrant = AsyncQdrantClient(url=settings.qdrant_url)
        app.state.ollama = OllamaClient(base_url=settings.ollama_url)

        log.info("gateway.ready", rabbitmq=settings.rabbitmq_url)
        yield

    log.info("gateway.stopping", rabbitmq=settings.rabbitmq_url)


app = FastAPI(title="RAG Distribuído — Gateway", lifespan=lifespan)
app.include_router(router)


@app.middleware("http")
async def measure_requests(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Cronometra cada request HTTP e alimenta o Histogram request_duration.

    Roda em volta de toda request (FastAPI middleware). O resultado vira a
    base dos painéis de latência p50/p95/p99 do Grafana (spec §7.2).
    """
    if request.url.path == "/metrics":
        return await call_next(request)

    start = time.perf_counter()
    status_code = "500"

    try:
        response = await call_next(request)

        status_code = str(response.status_code)

        return response
    finally:
        time_elapsed = time.perf_counter() - start
        request_duration.labels(endpoint=request.url.path, status=status_code).observe(time_elapsed)
