"""Entrypoint do gateway FastAPI.

Responsabilidade: receber HTTP (`/ingest`, `/query`, `/health`), publicar
mensagens no RabbitMQ e — no caso de `/query` — aguardar resposta via
reply queue (padrão RPC).

A conexão com o RabbitMQ é aberta no startup (via `lifespan`) e armazenada
em `app.state.rabbitmq`, ficando disponível para as rotas via
`request.app.state.rabbitmq`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.gateway.routes import router
from src.shared.config import settings
from src.shared.logging import configure_logging
from src.shared.messaging import connect, declare_queues

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
        await declare_queues(
            conn,
            settings.queue_ingest_documents,
            settings.queue_ingest_chunks,
            settings.queue_query_requests,
        )
        app.state.rabbitmq = conn
        log.info("gateway.ready", rabbitmq=settings.rabbitmq_url)
        yield

    log.info("gateway.stopping", rabbitmq=settings.rabbitmq_url)


app = FastAPI(title="RAG Distribuído — Gateway", lifespan=lifespan)
app.include_router(router)
