"""Worker de ingestão fim-a-fim.

Consome a fila ``ingest.documents``, e para cada documento executa o pipeline
completo do B1 dentro de um único handler (parse → detecta idioma → chunk →
embed → upsert no Qdrant). A separação em duas filas
(``ingest.documents`` → ``ingest.chunks``) descrita no spec entra só no B2.

Sem teste unitário: este módulo é glue de IO (RabbitMQ + Ollama + Qdrant), a
validação acontece no smoke ponta-a-ponta (Task 14).
"""

import asyncio
import hashlib
import socket
from typing import Any

from aio_pika.abc import AbstractIncomingMessage
from langdetect import LangDetectException, detect
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from src.shared.config import settings
from src.shared.logging import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
)
from src.shared.messaging import connect, consume_forever
from src.shared.ollama_client import OllamaClient
from src.shared.schemas import DocumentMessage
from src.workers.ingest.chunking import chunk_text
from src.workers.ingest.parsing import parse_document

log = configure_logging("ingest-worker")
HOSTNAME = socket.gethostname()


async def ensure_qdrant_collection(qdrant: AsyncQdrantClient) -> None:
    """Cria a collection do Qdrant se ainda não existir (idempotente).

    Parameters
    ----------
    qdrant : AsyncQdrantClient
        Cliente já conectado ao Qdrant.

    Notes
    -----
    Vetores ``settings.embedding_dim`` (768d nomic) com distância cosseno.
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


async def handle_document(
    payload: dict[str, object],
    ollama: OllamaClient,
    qdrant: AsyncQdrantClient,
) -> None:
    """Processa um documento da fila: parse → chunk → embed → upsert.

    Parameters
    ----------
    payload : dict
        Corpo JSON da mensagem (validar em :class:`DocumentMessage`).
    ollama : OllamaClient
        Cliente para gerar embeddings dos chunks.
    qdrant : AsyncQdrantClient
        Cliente para upsert dos pontos vetorizados.

    Notes
    -----
    Envolver o corpo em ``bind_correlation_id`` / ``clear_correlation_id``
    (try/finally) para que toda linha de log carregue o ``correlation_id``.
    """
    # TODO 1: validar payload -> DocumentMessage; bind_correlation_id(doc.correlation_id)

    try:
        doc = DocumentMessage.model_validate(payload)

        bind_correlation_id(correlation_id=doc.correlation_id)

        parsed_doc = parse_document(content_b64=doc.content_b64, source_type=doc.source_type)

        if parsed_doc == []:
            log.info("ingest.document.empty")
            return

        sample_doc = " ".join(text for _, text in parsed_doc)

        try:
            lang = detect(text=sample_doc[:500])
        except LangDetectException:
            lang = "unk"

        points: list[qmodels.PointStruct] = []
        chunk_index = 0

        for page, text in parsed_doc:
            if not text.strip():
                continue
            chunks = chunk_text(
                text=text,
                target_tokens=settings.chunk_target_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )

            for chunk in chunks:
                if not chunk.strip():
                    continue
                vector = await ollama.embed(model=settings.embedding_model, text=chunk)

                vector_id = f"{doc.doc_id}:{chunk_index}"

                qdrant_id = hashlib.sha256(vector_id.encode()).hexdigest()

                id_int = int(qdrant_id, 16) % (2**63 - 1)

                point = qmodels.PointStruct(
                    id=id_int,
                    vector=vector,
                    payload={
                        "doc_id": doc.doc_id,
                        "chunk_id": vector_id,
                        "text": chunk,
                        "source": doc.filename,
                        "page": page,
                        "lang": lang,
                        "chunk_index": chunk_index,
                    },
                )

                points.append(point)
                chunk_index += 1

        if points:
            await qdrant.upsert(collection_name=settings.qdrant_collection, points=points)

        log.info("ingest.document.indexed", doc_id=doc.doc_id, chunks=len(points), host=HOSTNAME)

    finally:
        clear_correlation_id()


async def main() -> None:
    """Bootstrap do worker: conecta dependências e consome a fila para sempre."""
    qdrant_client = AsyncQdrantClient(url=settings.qdrant_url)
    ollama_client = OllamaClient(base_url=settings.ollama_url)

    await ensure_qdrant_collection(qdrant=qdrant_client)
    log.info("ingest-worker.ready")

    async with connect(settings.rabbitmq_url) as conn:

        async def handler(msg: AbstractIncomingMessage, payload: dict[str, Any]) -> None:
            return await handle_document(
                payload=payload, qdrant=qdrant_client, ollama=ollama_client
            )

        await consume_forever(
            conn=conn, queue_name=settings.queue_ingest_documents, handler=handler, prefetch=2
        )


if __name__ == "__main__":
    asyncio.run(main())
