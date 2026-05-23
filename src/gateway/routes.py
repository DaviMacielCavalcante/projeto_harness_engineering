"""Rotas HTTP do gateway.

Endpoints:
    - `GET /health` — liveness probe trivial.
    - `GET /metrics` — registro Prometheus em formato texto (scrape).
    - `POST /ingest` — aceita um documento e publica na fila de ingestão (fire-and-forget).
    - `POST /query` — pergunta sob padrão RPC sobre RabbitMQ (publica + aguarda reply queue).
"""

import hashlib
import json
import time
import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from src.shared.config import settings
from src.shared.logging import bind_correlation_id, clear_correlation_id, configure_logging
from src.shared.messaging import publish_json
from src.shared.metrics import errors, metrics_response
from src.shared.schemas import (
    Citation,
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
    """Pergunta sob padrão RPC sobre RabbitMQ, com fallback degraded em timeout.

    Caminho feliz: cria uma reply queue exclusiva, publica a pergunta em
    ``queue_query_requests`` com ``reply_to=<reply_queue>``, e aguarda o
    query-worker responder na reply queue (timeout 120s).

    Caminho degraded (B3 Task 2): se o ``iterator(timeout=120)`` estourar
    (query-worker fora, Ollama travado, pool sobrecarregado), o handler
    NÃO devolve 504 vazio — em vez disso vai direto no Qdrant + Ollama
    (via ``app.state.qdrant`` / ``app.state.ollama``), faz retrieval bruto,
    e responde com ``answer="[degraded mode] sem síntese; veja as citações
    abaixo."``. Filosofia "degradar > quebrar". Logs/métrica:
    ``log.warning("query.degraded.*")`` + ``errors{service=gateway,
    error_type=query_timeout}`` incrementado.

    Parameters
    ----------
    req : QueryRequest
        Pergunta (question, top_k, session_id opcional).
    request : Request
        Request FastAPI — usado para acessar ``app.state.rabbitmq`` (caminho
        feliz) e ``app.state.qdrant`` / ``app.state.ollama`` (fallback).

    Returns
    -------
    QueryResponse
        Resposta normal do query-worker (texto sintetizado + citações +
        latência), OU resposta degraded (sentinel ``[degraded mode] ...``
        + citações brutas + ``usage={"tokens_in": 0, "tokens_out": 0}``).

    Raises
    ------
    HTTPException
        503 se o fallback degraded também falhar (Ollama fora + worker fora,
        Qdrant indisponível, payload malformado) — serviço genuinamente
        indisponível.
        504 só em cenário raro: o ``iterator`` do reply queue sai sem msg
        sem disparar ``TimeoutError`` (improvável em runtime).
    """
    correlation_id = f"q-{uuid.uuid4().hex[:8]}"

    timeout_detail = "query timeout"

    t0 = time.perf_counter()

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

                errors.labels(service="gateway", error_type="query_timeout").inc()

                try:
                    log.warning("query.degraded.starting")

                    q_vec = await request.app.state.ollama.embed(
                        text=req.question, model=settings.embedding_model
                    )

                    result = await request.app.state.qdrant.query_points(
                        collection_name=settings.qdrant_collection, query=q_vec, limit=req.top_k
                    )

                    citations = [
                        Citation(
                            doc_id=h.payload["doc_id"],
                            chunk_id=h.payload["chunk_id"],
                            page=h.payload.get("page"),
                            snippet=h.payload["text"][:240],
                            source=h.payload["source"],
                        )
                        for h in result.points
                    ]

                    log.warning("query.degraded.responded", n_citations=len(citations))

                    return QueryResponse(
                        answer="[degraded mode] sem síntese; veja as citações abaixo.",
                        citations=citations,
                        usage={"tokens_in": 0, "tokens_out": 0},
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                    )

                except Exception as e:
                    log.error("query.degraded.failed", error=str(e))
                    raise HTTPException(status_code=503, detail="serviço indisponível") from None
        finally:
            await channel.close()

    finally:
        clear_correlation_id()
