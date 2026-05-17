"""Worker de query fim-a-fim.

Consome a fila ``query.requests`` e, para cada pergunta, executa o pipeline
de resposta do B1 dentro de um único handler (detecta idioma → embed da
pergunta → retrieval no Qdrant → monta prompt → gera no Ollama → publica a
resposta na fila ``reply_to`` do gateway, padrão RPC sobre AMQP). Rerank
entra só no B2.

Sem teste unitário: este módulo é glue de IO (RabbitMQ + Ollama + Qdrant),
mesma decisão do ``workers/ingest/main.py`` — a validação acontece no smoke
ponta-a-ponta (Task 14).
"""

import asyncio
import socket
import time
from typing import Any

from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from langdetect import LangDetectException, detect
from qdrant_client import AsyncQdrantClient

from src.shared.config import settings
from src.shared.logging import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
)
from src.shared.messaging import connect, consume_forever, publish_json
from src.shared.ollama_client import OllamaClient
from src.shared.schemas import Citation, QueryRequestMessage, QueryResponse
from src.workers.query.prompt_builder import ContextBlock, build_prompt

log = configure_logging("query-worker")
HOSTNAME = socket.gethostname()


async def handle_query(
    payload: dict[str, object],
    ollama: OllamaClient,
    qdrant: AsyncQdrantClient,
    conn: AbstractRobustConnection,
) -> None:
    """Processa uma query da fila: embed → retrieval → generate → reply.

    Parameters
    ----------
    payload : dict
        Corpo JSON da mensagem (validar em :class:`QueryRequestMessage`).
    ollama : OllamaClient
        Cliente para embed da pergunta e geração da resposta.
    qdrant : AsyncQdrantClient
        Cliente para o retrieval vetorial (busca, não upsert).
    conn : AbstractRobustConnection
        Conexão RabbitMQ, usada para publicar a resposta no ``reply_to``.

    Notes
    -----
    Mesma estrutura do ``handle_document``: validar → ``bind_correlation_id``
    → corpo dentro de ``try`` → ``clear_correlation_id`` no ``finally``.
    """
    try:
        started = time.perf_counter()

        msg = QueryRequestMessage.model_validate(payload)

        bind_correlation_id(correlation_id=msg.correlation_id)

        try:
            lang = detect(text=msg.question)
        except LangDetectException:
            lang = "pt"

        vector = await ollama.embed(text=msg.question, model=settings.embedding_model)

        hits = await qdrant.query_points(
            collection_name=settings.qdrant_collection, query=vector, limit=msg.top_k
        )

        if not hits.points:
            if lang == "pt":
                response = QueryResponse(
                    answer="Não encontrei essa informação no corpus",
                    citations=[],
                    usage={"tokens_in": 0, "tokens_out": 0},
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )

            else:
                response = QueryResponse(
                    answer="I could not find this information in the corpus",
                    citations=[],
                    usage={"tokens_in": 0, "tokens_out": 0},
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )

            json_response = response.model_dump(mode="json")

            await publish_json(
                conn=conn,
                payload=json_response,
                correlation_id=msg.correlation_id,
                queue=msg.reply_to,
            )
        else:
            blocks = []

            for hit in hits.points:
                if hit.payload is None:
                    continue

                block = ContextBlock(
                    page=hit.payload["page"], source=hit.payload["source"], text=hit.payload["text"]
                )

                blocks.append(block)

            prompt = build_prompt(question=msg.question, blocks=blocks, lang=lang)

            generated_answer = await ollama.generate(
                model=settings.generation_model,
                prompt=prompt,
                options={
                    "temperature": settings.generation_temperature,
                    "num_ctx": settings.generation_num_ctx,
                },
            )

            citation: list[Citation] = [
                Citation(
                    doc_id=hit.payload["doc_id"],
                    chunk_id=hit.payload["chunk_id"],
                    page=hit.payload["page"],
                    snippet=hit.payload["text"][:240],
                    source=hit.payload["source"],
                )
                for hit in hits.points
                if hit.payload is not None
            ]

            response = QueryResponse(
                answer=generated_answer["text"],
                citations=citation,
                usage={
                    "tokens_in": generated_answer["tokens_in"],
                    "tokens_out": generated_answer["tokens_out"],
                },
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

            json_response = response.model_dump(mode="json")

            await publish_json(
                conn=conn,
                payload=json_response,
                correlation_id=msg.correlation_id,
                queue=msg.reply_to,
            )

    finally:
        clear_correlation_id()


async def main() -> None:
    """Bootstrap do worker: conecta dependências e consome a fila para sempre.

    Diferente do ingest, o query-worker só lê do Qdrant — não precisa
    garantir/criar a collection aqui.
    """
    qdrant_client = AsyncQdrantClient(url=settings.qdrant_url)
    ollama_client = OllamaClient(base_url=settings.ollama_url)

    log.info("query-worker.ready", queue=settings.queue_query_requests)

    async with connect(settings.rabbitmq_url) as conn:

        async def handler(msg: AbstractIncomingMessage, payload: dict[str, Any]) -> None:
            # Lembrete (já te pegou 2x): isto é coroutine — sem `await` ela é
            # criada e descartada, a msg é ack'd e a resposta nunca sai.
            return await handle_query(
                payload=payload, ollama=ollama_client, qdrant=qdrant_client, conn=conn
            )

        await consume_forever(
            conn=conn, queue_name=settings.queue_query_requests, handler=handler, prefetch=1
        )


if __name__ == "__main__":
    asyncio.run(main())
