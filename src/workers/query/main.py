"""Worker de query fim-a-fim (B2: cache L1/L2 + rerank + sessão + métricas).

Consome ``query.requests`` e, para cada pergunta, executa o pipeline completo:
detecta idioma → embed (cache L1) → retrieval top-N no Qdrant → rerank top-k
(cross-encoder, com fallback se o serviço cair) → cache L2 de resposta →
geração no Ollama (com preâmbulo de sessão, se houver ``session_id``) →
publica na fila ``reply_to`` (RPC sobre AMQP). Cada fase é cronometrada no
``query_pipeline_duration`` e os contadores de cache/throughput/erro são
incrementados ao longo do fluxo.

Sem teste unitário: glue de IO (RabbitMQ + Ollama + Qdrant + Redis +
rerank-service). A validação é o smoke estendido (Task 11).
"""

import asyncio
import json
import socket
import time
from pathlib import Path
from typing import Any

import redis.asyncio as aredis
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from langdetect import LangDetectException, detect
from qdrant_client import AsyncQdrantClient

from src.shared.cache import Cache
from src.shared.config import settings
from src.shared.logging import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
)
from src.shared.messaging import connect, consume_forever, publish_json
from src.shared.metrics import (
    cache_hits,
    cache_misses,
    errors,
    ollama_inflight,
    query_pipeline_duration,
    throughput_queries,
    tokens_total,
)
from src.shared.ollama_client import OllamaClient
from src.shared.schemas import Citation, QueryRequestMessage, QueryResponse
from src.shared.session import SessionStore
from src.shared.vllm_client import ChatGenerator, VllmClient
from src.shared.workers_metrics_server import start_metrics_server
from src.workers.query.prompt_builder import ContextBlock, build_messages
from src.workers.query.reranker_client import RerankerClient

log = configure_logging("query-worker")
HOSTNAME = socket.gethostname()

# src/workers/query/main.py -> parents[3] == raiz do repo (mesmo cálculo do prompt_builder)
_TOOLS_DIR = Path(__file__).resolve().parents[3] / "prompts" / "tools"


def load_cite_source_tool() -> dict[str, Any]:
    """Carrega a definição da tool ``cite_source`` de ``prompts/tools/``.

    Chamado uma vez no bootstrap (``main``) e passado ao handler — não é estado
    de módulo no import time (convenção do projeto).
    """
    tool: dict[str, Any] = json.loads((_TOOLS_DIR / "cite_source.json").read_text(encoding="utf-8"))
    return tool


async def handle_query(
    payload: dict[str, object],
    ollama: OllamaClient,
    generator: ChatGenerator,
    qdrant: AsyncQdrantClient,
    conn: AbstractRobustConnection,
    cache: Cache,
    reranker: RerankerClient,
    sessions: SessionStore,
    cite_tool: dict[str, Any],
) -> None:
    """Pipeline de query do B2: embed(L1) → retrieve → rerank → L2 → generate.

    Parameters
    ----------
    payload : dict
        Corpo JSON da mensagem (validar em :class:`QueryRequestMessage`).
    ollama : OllamaClient
        Cliente para o embed da pergunta (FASE 1). A geração NÃO passa mais por
        aqui — ela usa ``generator`` (que pode ser Ollama ou vLLM).
    generator : ChatGenerator
        Backend de geração da resposta (FASE 6). É o próprio ``ollama`` quando
        ``inference_backend="ollama"``, ou um :class:`VllmClient` quando
        ``"vllm"`` (Exp 3). Embeddings ficam sempre no Ollama.
    qdrant : AsyncQdrantClient
        Cliente para o retrieval vetorial (busca, não upsert).
    conn : AbstractRobustConnection
        Conexão RabbitMQ, usada para publicar a resposta no ``reply_to``.
    cache : Cache
        Cache distribuído: L1 (embedding de query), L2 (resposta inteira).
    reranker : RerankerClient
        Cliente do rerank-service (top-N → top-k via cross-encoder).
    sessions : SessionStore
        Histórico/resumo de conversa, usado só quando há ``session_id``.
    cite_tool : dict
        Definição da tool ``cite_source`` (function calling), passada ao
        ``generator.chat`` em ``tools=[cite_tool]``. No backend vLLM é ignorada.

    Notes
    -----
    Mesma moldura do B1: validar → ``bind_correlation_id`` → corpo no ``try``
    → ``clear_correlation_id`` no ``finally``. As fases novas (cache, rerank,
    sessão) entram no meio; cada uma é um bloco numerado abaixo.
    """
    try:
        started = time.perf_counter()

        msg = QueryRequestMessage.model_validate(payload)
        bind_correlation_id(correlation_id=msg.correlation_id)
        log.info("query.received", question_len=len(msg.question))

        try:
            lang = detect(text=msg.question)
        except LangDetectException:
            lang = "pt"
        if lang not in {"pt", "en"}:
            lang = "pt"

        # ------------------------------------------------------------------
        # FASE 1 — Embedding da pergunta, com cache L1 (cache-aside)
        # ------------------------------------------------------------------
        # Padrão cache-aside (mesmo do cache.py): tenta o cache; no hit usa o
        # valor, no miss calcula e grava. NÃO inverta a polaridade (o hit é
        # quando get devolve algo != None).
        with query_pipeline_duration.labels(phase="embed", worker_id=HOSTNAME).time():
            vector = await cache.get_query_embedding(msg.question)

            if vector is not None:
                cache_hits.labels(cache_layer="L1").inc()
            else:
                cache_misses.labels(cache_layer="L1").inc()
                ollama_inflight.inc()
                try:
                    vector = await ollama.embed(text=msg.question, model=settings.embedding_model)
                finally:
                    ollama_inflight.dec()

                await cache.set_query_embedding(msg.question, vector)

        # ------------------------------------------------------------------
        # FASE 2 — Retrieval inicial (top-N) no Qdrant
        # ------------------------------------------------------------------
        # Atenção: agora busca retrieval_top_k_initial (20), NÃO msg.top_k. O
        # rerank é quem corta pros top-k finais — buscar pouco aqui mata o
        # ganho do cross-encoder.
        with query_pipeline_duration.labels(phase="retrieve", worker_id=HOSTNAME).time():
            hits = await qdrant.query_points(
                collection_name=settings.qdrant_collection,
                query=vector,
                limit=settings.retrieval_top_k_initial,
            )

        # Short-circuit sem-hits: não chama o LLM à toa
        if not hits.points:
            answer = (
                "Não encontrei essa informação no corpus"
                if lang == "pt"
                else "I could not find this information in the corpus"
            )
            response = QueryResponse(
                answer=answer,
                citations=[],
                usage={"tokens_in": 0, "tokens_out": 0},
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            await publish_json(
                conn=conn,
                payload=response.model_dump(mode="json"),
                correlation_id=msg.correlation_id,
                queue=msg.reply_to,
            )
            throughput_queries.labels(worker_id=HOSTNAME, status="empty").inc()
            return

        # ------------------------------------------------------------------
        # FASE 3 — Rerank top-N → top-k (com fallback se o serviço cair)
        # ------------------------------------------------------------------
        with query_pipeline_duration.labels(phase="rerank", worker_id=HOSTNAME).time():
            try:
                candidates = []

                for hit in hits.points:
                    if hit.payload is None:
                        continue

                    candidate = {
                        "id": hit.payload["chunk_id"],
                        "text": hit.payload["text"],
                        "doc_id": hit.payload["doc_id"],
                        "source": hit.payload["source"],
                        "page": hit.payload["page"],
                    }

                    candidates.append(candidate)

                candidates_by_id = {c["id"]: c for c in candidates}

                items = await reranker.rerank(msg.question, candidates, top_k=msg.top_k)

                retrieved_ids = []

                blocks = []

                for item in items:
                    orig = candidates_by_id[item["id"]]
                    block = ContextBlock(
                        doc_id=orig["doc_id"],
                        text=orig["text"],
                        source=orig["source"],
                        page=orig["page"],
                    )

                    blocks.append(block)
                    retrieved_ids.append(item["id"])

            except Exception:
                # Fallback: reranker fora do ar → usa os top-k brutos do Qdrant
                # (degrada, não quebra — mesma filosofia do §8.4/§7.4).
                errors.labels(service="query-worker", error_type="rerank_fallback").inc()
                log.warning("rerank.skipped_fallback")

                blocks = []

                retrieved_ids = []

                for hit in hits.points[: msg.top_k]:
                    if hit.payload is None:
                        continue

                    block = ContextBlock(
                        doc_id=hit.payload["doc_id"],
                        text=hit.payload["text"],
                        source=hit.payload["source"],
                        page=hit.payload["page"],
                    )

                    blocks.append(block)
                    retrieved_ids.append(hit.payload["chunk_id"])

        # ------------------------------------------------------------------
        # FASE 4 — Cache L2 (resposta inteira, chaveada por query + ids)
        # ------------------------------------------------------------------
        cached = await cache.get_response(msg.question, retrieved_ids=retrieved_ids)

        if cached is not None:
            cache_hits.labels(cache_layer="L2").inc()
            response = QueryResponse.model_validate(cached)

            await publish_json(
                conn=conn,
                payload=response.model_dump(mode="json"),
                correlation_id=msg.correlation_id,
                queue=msg.reply_to,
            )

            throughput_queries.labels(worker_id=HOSTNAME, status="cache_hit").inc()

            return
        else:
            cache_misses.labels(cache_layer="L2").inc()

        # ------------------------------------------------------------------
        # FASE 5 — Monta as mensagens (system+user); se houver sessão, prefixa
        #          histórico/resumo ao conteúdo do user (mantém o system isolado)
        # ------------------------------------------------------------------
        messages: list[dict[str, Any]] = build_messages(
            question=msg.question, blocks=blocks, lang=lang
        )
        if msg.session_id:
            history = await sessions.get_history(msg.session_id)
            summary = await sessions.get_summary(msg.session_id)

            history_in_one_line = "\n".join(f"Q: {t['q']}\nA: {t['a']}" for t in history)

            base_message = messages[1]["content"]

            pieces: list[str] = []

            if summary:
                pieces.append(f"# Resumo: \n{summary}")

            if history:
                pieces.append("# Histórico recente\n" + "\n" + history_in_one_line)

            if pieces:
                messages[1]["content"] = "\n\n".join(pieces) + "\n\n" + base_message
        # ------------------------------------------------------------------
        # FASE 6 — Geração no Ollama via /api/chat (com a tool cite_source)
        # ------------------------------------------------------------------
        # Troca de generate→chat: passamos a tool e o modelo PODE emitir
        # tool_calls (citações estruturadas). O `generated` ganha "tool_calls".
        # No backend vLLM (Exp 3) a tool é ignorada e tool_calls volta []: o
        # bloco da FASE 7 já lida com isso via fallback estrutural.
        with query_pipeline_duration.labels(phase="generate", worker_id=HOSTNAME).time():
            ollama_inflight.inc()
            try:
                generated = await generator.chat(
                    messages=messages,
                    model=settings.generation_model,
                    tools=[cite_tool],
                    options={
                        "temperature": settings.generation_temperature,
                        "num_ctx": settings.generation_num_ctx,
                    },
                )

            finally:
                ollama_inflight.dec()

        tokens_total.labels(direction="in", model=settings.generation_model).inc(
            generated["tokens_in"]
        )
        tokens_total.labels(direction="out", model=settings.generation_model).inc(
            generated["tokens_out"]
        )

        # ------------------------------------------------------------------
        # FASE 7 — Citações a partir dos blocks reranqueados, monta a resposta,
        #          grava no cache L2 e na sessão, publica
        # ------------------------------------------------------------------

        citations: list[Citation] = []

        if generated["tool_calls"]:
            source_by_doc_id_and_page = {}

            for i, block in enumerate(blocks):
                source_by_doc_id_and_page[(block.doc_id, block.page)] = (
                    retrieved_ids[i],
                    block.source,
                )

            for tc in generated["tool_calls"]:
                args = tc["function"]["arguments"]
                chunk_id, source = source_by_doc_id_and_page.get(
                    (args["doc_id"], args.get("page")), ("", args["doc_id"])
                )

                c = Citation(
                    doc_id=args["doc_id"],
                    chunk_id=chunk_id,
                    page=args.get("page"),
                    snippet=args["snippet"],
                    source=source,
                )

                citations.append(c)
            log.info("query.citations", via="tool_calls", n=len(generated["tool_calls"]))

        else:
            for index, block in enumerate(blocks):
                c = Citation(
                    doc_id=block.doc_id,
                    chunk_id=retrieved_ids[index],
                    page=block.page,
                    snippet=block.text[:240],
                    source=block.source,
                )
                citations.append(c)
            log.info("query.citations", via="structural", n=len(blocks))

        response = QueryResponse(
            answer=generated["text"],
            citations=citations,
            usage={"tokens_in": generated["tokens_in"], "tokens_out": generated["tokens_out"]},
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

        await cache.set_response(
            msg.question, retrieved_ids=retrieved_ids, payload=response.model_dump(mode="json")
        )

        if msg.session_id:
            await sessions.append(sid=msg.session_id, question=msg.question, answer=response.answer)

        await publish_json(
            conn=conn,
            payload=response.model_dump(mode="json"),
            correlation_id=msg.correlation_id,
            queue=msg.reply_to,
        )

        throughput_queries.labels(worker_id=HOSTNAME, status="ok").inc()

        log.info("query.responded", latency_ms=int((time.perf_counter() - started) * 1000))

    except Exception:
        errors.labels(service="query-worker", error_type="handler").inc()
        throughput_queries.labels(worker_id=HOSTNAME, status="error").inc()
        log.exception("query.error")
        raise
    finally:
        clear_correlation_id()


async def main() -> None:
    """Bootstrap do worker: conecta dependências e consome a fila para sempre.

    Diferente do ingest, o query-worker só lê do Qdrant — não precisa
    garantir/criar a collection aqui. O B2 adiciona Redis (cache L1/L2 +
    sessão) e o cliente do rerank-service.
    """
    qdrant_client = AsyncQdrantClient(url=settings.qdrant_url)
    ollama_client = OllamaClient(base_url=settings.ollama_url)
    reranker_client = RerankerClient(base_url=settings.rerank_url)

    # Geração: Ollama (linha-base) ou vLLM (Exp 3). Embeddings ficam sempre no
    # ollama_client; só a geração troca. A seleção é em runtime via env.
    generator: ChatGenerator
    if settings.inference_backend == "vllm":
        generator = VllmClient(
            base_url=settings.vllm_url,
            model=settings.vllm_model,
            max_tokens=settings.generation_max_tokens,
        )
        log.info(
            "query-worker.generator",
            backend="vllm",
            url=settings.vllm_url,
            model=settings.vllm_model,
        )
    else:
        generator = ollama_client
        log.info("query-worker.generator", backend="ollama", model=settings.generation_model)
    # Any na fronteira: a redis-py tipa get/setex como `Awaitable[Any] | Any`
    # com param `name` (não `k`), então o cliente real não casa estruturalmente
    # com o Protocol _RedisLike — que existe pro seam de teste (FakeRedis). A
    # checagem de tipo da interface vale onde importa (nos testes). DÉBITO: o
    # _RedisLike está duplicado em cache.py e session.py; consolidar num só.
    redis_client: Any = aredis.from_url(settings.redis_url, decode_responses=True)
    cache = Cache(client=redis_client)
    sessions = SessionStore(client=redis_client)
    cite_tool = load_cite_source_tool()

    _metrics_runner = await start_metrics_server(port=settings.worker_metrics_port)
    log.info("query-worker.metrics_ready", port=settings.worker_metrics_port)
    log.info("query-worker.ready", queue=settings.queue_query_requests)

    async with connect(settings.rabbitmq_url) as conn:

        async def handler(msg: AbstractIncomingMessage, payload: dict[str, Any]) -> None:
            return await handle_query(
                payload=payload,
                ollama=ollama_client,
                generator=generator,
                qdrant=qdrant_client,
                conn=conn,
                cache=cache,
                reranker=reranker_client,
                sessions=sessions,
                cite_tool=cite_tool,
            )

        await consume_forever(
            conn=conn, queue_name=settings.queue_query_requests, handler=handler, prefetch=1
        )


if __name__ == "__main__":
    asyncio.run(main())
