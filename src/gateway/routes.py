"""Rotas HTTP do gateway.

Endpoints:
    - `GET /health` — liveness probe trivial.
    - `GET /metrics` — registro Prometheus em formato texto (scrape).
    - `POST /ingest` — aceita um documento e publica na fila de ingestão (fire-and-forget).
    - `POST /query` — pergunta sob padrão RPC sobre RabbitMQ (publica + aguarda reply queue).
"""

import hashlib
import json
import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from src.shared.config import settings
from src.shared.logging import bind_correlation_id, clear_correlation_id, configure_logging
from src.shared.messaging import publish_json
from src.shared.metrics import metrics_response
from src.shared.schemas import (
    DocumentMessage,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryRequestMessage,
    QueryResponse,
)

log = configure_logging("gateway")
router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe: confirma que o app subiu e o event loop responde."""
    return {"status": "ok"}


@router.get("/metrics")
async def metrics() -> Response:
    """Expõe o registro Prometheus no formato texto (scrape do Prometheus).

    Boilerplate de cola: serializa o `REGISTRY` de `src.shared.metrics` e
    devolve com o `Content-Type` que o Prometheus espera.
    """
    body, content_type = metrics_response()
    return Response(content=body, media_type=content_type)


@router.post("/ingest", response_model=IngestResponse, status_code=202)
async def ingest(req: IngestRequest, request: Request) -> IngestResponse:
    """Aceita um documento e publica na fila de ingestão.

    Padrão fire-and-forget: gera identificadores, publica no RabbitMQ e devolve
    202 imediatamente. O worker de ingestão processa em background.

    Parameters
    ----------
    req : IngestRequest
        Documento codificado (filename, content_b64, source_type).
    request : Request
        Request FastAPI — usado para acessar `app.state.rabbitmq`.

    Returns
    -------
    IngestResponse
        `correlation_id` (para rastrear nos logs) e `doc_id` (estável por conteúdo).
    """
    correlation_id = f"i-{uuid.uuid4().hex[:8]}"

    try:
        bind_correlation_id(correlation_id=correlation_id)

        b64_prefix = req.content_b64[:1024]

        fingerprint_source = req.filename + b64_prefix

        sha256_hex = hashlib.sha256(fingerprint_source.encode()).hexdigest()

        doc_id = sha256_hex[:16]

        payload = DocumentMessage(
            correlation_id=correlation_id,
            content_b64=req.content_b64,
            doc_id=doc_id,
            filename=req.filename,
            source_type=req.source_type,
        ).model_dump()

        await publish_json(
            payload=payload,
            correlation_id=correlation_id,
            conn=request.app.state.rabbitmq,
            queue=settings.queue_ingest_documents,
        )

        log.info("ingest.accepted", doc_id=doc_id, filename=req.filename)

        return IngestResponse(correlation_id=correlation_id, doc_id=doc_id)
    finally:
        clear_correlation_id()


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, request: Request) -> QueryResponse:
    """Pergunta sob padrão RPC sobre RabbitMQ.

    Cria uma reply queue exclusiva, publica a pergunta em `queue_query_requests`
    com `reply_to=<reply_queue>`, e aguarda o query-worker responder na reply
    queue. Timeout de 120s.

    Parameters
    ----------
    req : QueryRequest
        Pergunta (question, top_k, session_id opcional).
    request : Request
        Request FastAPI — usado para acessar `app.state.rabbitmq`.

    Returns
    -------
    QueryResponse
        Resposta do query-worker (texto + citações + latência).

    Raises
    ------
    HTTPException
        504 se nenhuma resposta chegar dentro do timeout.
    """
    correlation_id = f"q-{uuid.uuid4().hex[:8]}"

    timeout_detail = "query timeout"

    try:
        bind_correlation_id(correlation_id=correlation_id)

        log.info("query.received", question_len=len(req.question), top_k=req.top_k)

        conn = request.app.state.rabbitmq

        channel = await conn.channel()
        try:
            reply_queue = await channel.declare_queue(
                name=f"query.responses.{correlation_id}", exclusive=True, auto_delete=True
            )

            payload = QueryRequestMessage(
                session_id=req.session_id,
                correlation_id=correlation_id,
                question=req.question,
                top_k=req.top_k,
                reply_to=reply_queue.name,
            ).model_dump()

            await publish_json(
                conn=conn,
                queue=settings.queue_query_requests,
                correlation_id=correlation_id,
                reply_to=reply_queue.name,
                payload=payload,
            )

            try:
                async with reply_queue.iterator(timeout=120) as it:
                    async for msg in it:
                        async with msg.process():
                            response_payload = json.loads(msg.body)
                            log.info("query.answered")
                            return QueryResponse(**response_payload)
                raise HTTPException(status_code=504, detail=timeout_detail)
            except TimeoutError:
                log.warning("query.timeout")
                raise HTTPException(status_code=504, detail=timeout_detail) from None
        finally:
            await channel.close()

    finally:
        clear_correlation_id()
