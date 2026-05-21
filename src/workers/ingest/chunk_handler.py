"""Handler do estágio 2 da ingestão (B2): embed + upsert no Qdrant.

Consome ``ingest.chunks`` — 1 mensagem = 1 chunk independente. Sem try/except
em volta de embed/upsert: erros propagam → ``consume_forever`` rejeita a msg.
Quando DLX entrar em B3, mensagens ruins vão pra ``ingest.chunks.dlq``; até
lá o RabbitMQ descarta (sem requeue, então sem loop infinito).

Sem teste unitário: módulo é glue de IO (Ollama + Qdrant). Validação no
smoke estendido (Task 11 do B2).
"""

import hashlib
import socket
import time
from typing import Any

from aio_pika.abc import AbstractIncomingMessage
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from src.shared.config import settings
from src.shared.logging import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
)
from src.shared.metrics import errors, ingest_pipeline_duration, tokens_total
from src.shared.ollama_client import OllamaClient
from src.shared.schemas import ChunkMessage

log = configure_logging("ingest-worker-chunk")
HOSTNAME = socket.gethostname()


async def ensure_qdrant_collection(qdrant: AsyncQdrantClient) -> None:
    """Cria a collection do Qdrant se ainda não existir (idempotente).

    Parameters
    ----------
    qdrant : AsyncQdrantClient
        Cliente já conectado ao Qdrant.

    Notes
    -----
    Mantida igual ao B1: vetores ``settings.embedding_dim`` (768d nomic) com
    distância cosseno. Foi movida do antigo ``main.py`` pra cá porque só o
    chunk_handler precisa do Qdrant — o document_handler nem instancia.
    """
    collections = await qdrant.get_collections()
    collections_names = [collection.name for collection in collections.collections]
    if settings.qdrant_collection not in collections_names:
        await qdrant.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(
                size=settings.embedding_dim, distance=qmodels.Distance.COSINE
            ),
        )
        log.info("qdrant.collection_created")


async def handle_chunk(
    msg: AbstractIncomingMessage,
    payload: dict[str, Any],
    ollama: OllamaClient,
    qdrant: AsyncQdrantClient,
) -> None:
    """Processa um chunk da fila ``ingest.chunks``.

    Parameters
    ----------
    msg : AbstractIncomingMessage
        Mensagem AMQP crua — usada para puxar o ``correlation_id`` do header
        (foi setado pelo ``document_handler`` via ``publish_json(..., correlation_id=...)``).
    payload : dict
        Corpo JSON da mensagem (validar como :class:`ChunkMessage`).
    ollama : OllamaClient
        Cliente Ollama compartilhado, já instanciado no ``main``.
    qdrant : AsyncQdrantClient
        Cliente Qdrant compartilhado, já instanciado no ``main``.

    Notes
    -----
    Pipeline interno: bind correlation_id (do header) → validar →
    embed (com histograma) → contar tokens → calcular point_id determinístico
    → upsert (com histograma).
    """
    started = time.perf_counter()
    try:
        correlation_id = msg.correlation_id or "unset"
        bind_correlation_id(correlation_id=correlation_id)

        cm: ChunkMessage = ChunkMessage.model_validate(payload)

        with ingest_pipeline_duration.labels(phase="embed", worker_id=HOSTNAME).time():
            vector = await ollama.embed(text=cm.text, model=settings.embedding_model)

        tokens_total.labels(direction="in", model=settings.embedding_model).inc(
            max(1, len(cm.text) // 4)
        )

        sha_id = hashlib.sha256(cm.chunk_id.encode())

        hex_id = sha_id.hexdigest()

        point_id = int(hex_id, 16) % (2**63 - 1)

        point = qmodels.PointStruct(id=point_id, vector=vector, payload=cm.model_dump())

        with ingest_pipeline_duration.labels(phase="upsert", worker_id=HOSTNAME).time():
            await qdrant.upsert(collection_name=settings.qdrant_collection, points=[point])

        log.info(
            "ingest.chunk.indexed",
            doc_id=cm.doc_id,
            chunk_id=cm.chunk_id,
            elapsed_s=round(time.perf_counter() - started, 3),
        )

    except Exception:
        errors.labels(service="ingest-worker-chunk", error_type="chunk_handler").inc()
        log.exception("ingest.chunk.error")
        raise
    finally:
        clear_correlation_id()
