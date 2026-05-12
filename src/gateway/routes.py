"""Rotas HTTP do gateway.

Endpoints:
    - `GET /health` — liveness probe trivial.
    - `POST /ingest` — aceita um documento e publica na fila de ingestão (fire-and-forget).
    - `POST /query` — pergunta sob padrão RPC sobre RabbitMQ (publica + aguarda reply queue).
"""

import hashlib
import json
import uuid

from fastapi import APIRouter, HTTPException, Request

from src.shared.config import settings
from src.shared.logging import bind_correlation_id, clear_correlation_id, configure_logging
from src.shared.messaging import publish_json
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
    # TODO 1: gerar correlation_id no formato "i-<8 chars hex>" usando uuid.uuid4().hex
    # TODO 2: bind_correlation_id(correlation_id) — pra todos os logs daqui pra
    #         frente carregarem esse id. Lembre do try/finally pra clear no fim.
    # TODO 3: gerar doc_id como sha256(filename + content_b64[:1024])[:16].
    #         Por que só os primeiros 1024 chars do b64? PDFs grandes geram
    #         strings enormes; o prefixo é estável o bastante pra deduplicar.
    # TODO 4: monte o payload com DocumentMessage(...).model_dump() — fonte
    #         única de verdade pros campos. Vai te pegar o erro cedo se você
    #         errar nome de campo.
    # TODO 5: publish_json(
    #             conn           = request.app.state.rabbitmq,
    #             queue          = settings.queue_ingest_documents,
    #             payload        = <o dict do model_dump>,
    #             correlation_id = correlation_id,
    #         )
    # TODO 6: log.info("ingest.accepted", doc_id=..., filename=...)
    #         e retornar IngestResponse(correlation_id=..., doc_id=...).
    #         O campo `status` tem default "accepted" no schema, não precisa passar.
    # TODO 7: clear_correlation_id() no finally
    raise NotImplementedError


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
    # TODO 1: gerar correlation_id no formato "q-<8 chars hex>" + bind_correlation_id
    # TODO 2: pegar a connection: conn = request.app.state.rabbitmq
    # TODO 3: abrir um channel NOVO (await conn.channel()) — esse canal é só
    #         pra DECLARAR e CONSUMIR a reply queue. Não é o canal do publish:
    #         o publish_json abre/fecha o canal dele próprio internamente.
    #         Por que canal próprio aqui? A reply queue é exclusiva ao canal
    #         que a declarou; quando esse canal fecha, ela some (auto_delete).
    #         Isso garante isolamento — duas /query simultâneas não se enxergam.
    # TODO 4: declarar reply_queue exclusiva e auto-delete com nome único:
    #             reply_queue = await channel.declare_queue(
    #                 name=f"query.responses.{correlation_id}",
    #                 exclusive=True,
    #                 auto_delete=True,
    #             )
    # TODO 5: monte o payload com QueryRequestMessage(...).model_dump().
    #         Lembre de incluir reply_to=reply_queue.name no model.
    # TODO 6: publish_json(
    #             conn, settings.queue_query_requests,
    #             payload        = <model_dump>,
    #             correlation_id = correlation_id,
    #             reply_to       = reply_queue.name,  # também vai no header AMQP
    #         )
    # TODO 7: iterar reply_queue com timeout=120:
    #             async with reply_queue.iterator(timeout=120) as it:
    #                 async for msg in it:
    #                     async with msg.process():
    #                         payload = json.loads(msg.body)
    #                         return QueryResponse(**payload)
    #         Se o iterator esgotar sem mensagem -> raise HTTPException(504).
    # TODO 8: fechar o channel no finally interno (await channel.close())
    # TODO 9: clear_correlation_id no finally externo
    raise NotImplementedError
