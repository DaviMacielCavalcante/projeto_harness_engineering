"""Handler do estágio 1 da ingestão (B2): parse + chunk + publish.

Consome ``ingest.documents`` e publica N mensagens ``ChunkMessage`` em
``ingest.chunks``, uma por chunk. Não fala com Ollama nem com Qdrant — quem
embeda e grava é o ``chunk_handler``. A separação em duas filas troca um
handler "fat" do B1 (parse → chunk → embed → upsert) por dois consumers
independentes que escalam separados: muitos workers de chunk (embedding é
caro) atrás de poucos workers de doc (parsing é barato).

Sem teste unitário: módulo é glue de IO (parse + RabbitMQ). Validação no
smoke estendido (Task 11 do B2).
"""

import socket
import time
from typing import Any

from aio_pika.abc import AbstractRobustConnection
from langdetect import LangDetectException, detect

from src.shared.config import settings
from src.shared.logging import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
)
from src.shared.messaging import publish_json
from src.shared.metrics import errors, ingest_pipeline_duration, throughput_docs
from src.shared.schemas import ChunkMessage, DocumentMessage
from src.workers.ingest.chunking import chunk_text
from src.workers.ingest.parsing import parse_document

log = configure_logging("ingest-worker-doc")
HOSTNAME = socket.gethostname()


async def handle_document(
    payload: dict[str, Any],
    rabbit_conn: AbstractRobustConnection,
) -> None:
    """Processa um documento da fila ``ingest.documents``.

    Parameters
    ----------
    payload : dict
        Corpo JSON da mensagem (validar como :class:`DocumentMessage`).
    rabbit_conn : AbstractRobustConnection
        Conexão aberta com RabbitMQ — usada para publicar os chunks
        resultantes em ``settings.queue_ingest_chunks``.

    Notes
    -----
    Pipeline interno: validar → bind correlation_id → parse → detect lang →
    para cada (page, text) → chunk → publish ChunkMessage por chunk.
    Ao final, contabiliza 1 doc particionado em ``throughput_docs``.
    """
    started = time.perf_counter()
    try:
        doc: DocumentMessage = DocumentMessage.model_validate(payload)

        bind_correlation_id(correlation_id=doc.correlation_id)

        log.info("ingest.document.received", doc_id=doc.doc_id, filename=doc.filename)

        with ingest_pipeline_duration.labels(phase="parse", worker_id=HOSTNAME).time():
            parsed: list[tuple[int | None, str]] = parse_document(
                content_b64=doc.content_b64, source_type=doc.source_type
            )

        if not parsed:
            log.warning("ingest.document.empty", doc_id=doc.doc_id)
            return

        sample_from_doc = " ".join(text for _, text in parsed)[:500]
        try:
            lang = detect(text=sample_from_doc)
        except LangDetectException:
            lang = "unk"

        chunk_index = 0

        with ingest_pipeline_duration.labels(phase="chunk", worker_id=HOSTNAME).time():
            for page, text in parsed:
                if not text.strip():
                    continue

                chunks = chunk_text(
                    text=text,
                    target_tokens=settings.chunk_target_tokens,
                    overlap_tokens=settings.chunk_overlap_tokens,
                    max_tokens=settings.embedding_max_tokens,
                )

                for chunk in chunks:
                    if not chunk.strip():
                        continue

                    chunk_msg = ChunkMessage(
                        doc_id=doc.doc_id,
                        chunk_id=f"{doc.doc_id}:{chunk_index}",
                        text=chunk,
                        source=doc.filename,
                        page=page,
                        lang=lang,
                    )

                    await publish_json(
                        rabbit_conn,
                        settings.queue_ingest_chunks,
                        chunk_msg.model_dump(),
                        correlation_id=doc.correlation_id,
                    )

                    chunk_index += 1

        throughput_docs.labels(worker_id=HOSTNAME).inc()

        log.info(
            "ingest.document.chunked",
            doc_id=doc.doc_id,
            chunks=chunk_index,
            elapsed_s=round(time.perf_counter() - started, 2),
        )

    except Exception:
        errors.labels(service="ingest-orker-doc", error_type="document_handler").inc()
        log.exception("ingest.document.error")
        raise
    finally:
        clear_correlation_id()
