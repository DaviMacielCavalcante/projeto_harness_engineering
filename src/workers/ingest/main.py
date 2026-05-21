"""Bootstrap do worker de ingestão (B2): roteia por ``INGEST_ROLE``.

Substitui a versão "fat" do B1 (parse → chunk → embed → upsert num único
handler). Agora o pipeline está dividido em dois handlers independentes:

- ``document_handler.handle_document`` consome ``ingest.documents``.
- ``chunk_handler.handle_chunk`` consome ``ingest.chunks``.

A env ``INGEST_ROLE`` controla qual(is) consumer(s) este processo roda:

- ``"documents"`` — só doc handler (não precisa de Ollama nem Qdrant)
- ``"chunks"``    — só chunk handler (não toca em parsing/chunking)
- ``"both"``      — roda os dois em paralelo, no mesmo processo (default,
  útil em dev/Modo 1; no compose o profile ``all`` sobe 2 serviços
  separados, um por role).

Sem teste unitário (glue de IO). Validação no smoke estendido (Task 11/B2).
"""

import asyncio
import socket
from typing import Any

from aio_pika.abc import AbstractIncomingMessage
from qdrant_client import AsyncQdrantClient

from src.shared.config import settings
from src.shared.logging import configure_logging
from src.shared.messaging import connect, consume_forever
from src.shared.ollama_client import OllamaClient
from src.workers.ingest.chunk_handler import ensure_qdrant_collection, handle_chunk
from src.workers.ingest.document_handler import handle_document

log = configure_logging("ingest-worker")
HOSTNAME = socket.gethostname()


async def main() -> None:
    """Conecta dependências conforme o role e consome as filas atribuídas."""
    role = settings.ingest_role
    log.info("ingest-worker.starting", role=role, host=HOSTNAME)

    async with connect(settings.rabbitmq_url) as conn:
        tasks: list[asyncio.Task[None]] = []

        # --- Consumer de DOCUMENTOS (parse + chunk + publish) ---
        if role in {"documents", "both"}:

            async def doc_handler(msg: AbstractIncomingMessage, payload: dict[str, Any]) -> None:
                await handle_document(payload=payload, rabbit_conn=conn)

            tasks.append(
                asyncio.create_task(
                    consume_forever(
                        conn=conn,
                        queue_name=settings.queue_ingest_documents,
                        handler=doc_handler,
                        prefetch=2,
                    )
                )
            )

        # --- Consumer de CHUNKS (embed + upsert) ---
        if role in {"chunks", "both"}:
            qdrant = AsyncQdrantClient(url=settings.qdrant_url)
            ollama = OllamaClient(base_url=settings.ollama_url)

            await ensure_qdrant_collection(qdrant=qdrant)

            async def on_chunk(msg: AbstractIncomingMessage, payload: dict[str, Any]) -> None:
                await handle_chunk(msg=msg, payload=payload, ollama=ollama, qdrant=qdrant)

            tasks.append(
                asyncio.create_task(
                    consume_forever(
                        conn=conn,
                        queue_name=settings.queue_ingest_chunks,
                        handler=on_chunk,
                        prefetch=8,
                    )
                )
            )

        log.info("ingest-worker.ready")
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
