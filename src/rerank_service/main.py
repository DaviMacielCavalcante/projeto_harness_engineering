"""FastAPI service do reranker (Task 6 do plano B2).

Carrega o cross-encoder `bge-reranker-v2-m3` uma vez no startup (via
`lifespan`) e expõe `POST /rerank` pra que o query-worker chame em cada
request — top-20 vetorial → top-5 cross-encoder, conforme spec §4.3.

Por que serviço separado e não chamada in-process do query-worker?
- O cross-encoder ocupa ~600MB em memória e arrasta `torch` como dep.
  Se cada réplica de query-worker carregasse, multiplicaríamos esse
  custo desnecessariamente.
- Isolar permite escalar o rerank independentemente e, em B4, comparar
  CPU vs GPU sem mexer no resto.
- Em B3 esse serviço fica num container dedicado. O Dockerfile da Task 6
  Step 2 pré-baixa o modelo no `docker build` e seta a env oficial do
  huggingface_hub ``HF_HOME=/models`` — em runtime o mesmo env aponta
  pro cache populado, sem cold start de download. Em dev local, sem
  HF_HOME, o stack cai no cache default (``~/.cache/huggingface/``).
"""

import time
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response
from pydantic import BaseModel
from sentence_transformers import CrossEncoder

from src.shared.logging import configure_logging
from src.shared.metrics import metrics_response

log = configure_logging("rerank-service")

# Cross-encoder multilíngue: recebe (query, candidate) e devolve um score
# de relevância. Diferente do bi-encoder (que vira dois embeddings
# independentes e compara por cosine), o cross-encoder concatena query +
# candidato e faz atenção cruzada — mais lento, mais preciso. Por isso ele
# é o SEGUNDO estágio (re-rank de top-20 vindo do vetorial), nunca o
# primeiro (não escalaria pra busca em centenas de milhares de chunks).
#
# O nome vem da env MODEL_NAME quando rodando em container (definida via
# ARG no Dockerfile e exportada como ENV); em dev local cai no fallback.
# Manter a env como fonte de verdade evita divergência entre o modelo
# pré-baixado no `docker build` e o que o `lifespan` tenta carregar.
MODEL_NAME = os.getenv("MODEL_NAME", "BAAI/bge-reranker-v2-m3")


# ---- Schemas (contrato HTTP — estrutura, não miolo) ----


class RerankRequest(BaseModel):
    """Payload aceito por POST /rerank.

    `candidates` é uma lista de dicts com **pelo menos** ``text`` e algum
    identificador (``id`` ou ``chunk_id``). Outros campos passam
    transparentes — não usamos aqui, mas o query-worker pode anexar
    metadados (page, source) que voltam intactos pra ele depois.
    """

    query: str
    candidates: list[dict[str, Any]]
    top_k: int = 5


class RerankResponseItem(BaseModel):
    """Item ranqueado: id, score do cross-encoder, texto original."""

    id: str
    score: float
    text: str


class RerankResponse(BaseModel):
    """Resposta de POST /rerank.

    ``items`` vem ordenado por score decrescente, truncado em ``top_k``.
    """

    items: list[RerankResponseItem]
    model: str
    latency_ms: int


# ---- Lifespan: carrega o modelo uma vez ----


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Carrega o CrossEncoder no startup e guarda em ``app.state.model``.

    Path do cache: controlado pela env oficial do huggingface_hub
    ``HF_HOME`` — `sentence-transformers` e `transformers` honram essa
    var por baixo. Dois cenários:

    - **Em container**: o Dockerfile seta ``HF_HOME=/models`` (cache
      populado no `docker build`) e ainda ``HF_HUB_OFFLINE=1`` +
      ``TRANSFORMERS_OFFLINE=1`` em runtime — o stack lê só do disco
      local, sem nenhuma chamada de rede (nem validação ETag). Startup
      sub-segundo. Se o cache estiver ausente por algum motivo (build
      quebrado), o ``CrossEncoder`` levanta ``LocalEntryNotFoundError``
      e o container entra em crashloop — falha visível, não silenciosa.
    - **Em dev local** (``uv run uvicorn ...``): nenhuma dessas envs
      está setada, o stack cai no comportamento padrão ``online``: tenta
      cache em ``~/.cache/huggingface/`` e, se faltar, baixa ~600MB.

    Tentar passar ``cache_folder=`` aqui não ajudaria — esse argumento
    é ignorado quando o modelo não tem ``modules.json``, caso do
    bge-reranker-v2-m3. Por isso a única alavanca é a env HF_HOME.

    Em ambos os casos o `lifespan` é o único ponto que carrega o modelo
    — ele fica vivo em ``app.state.model`` enquanto o app vive.
    """
    
    log.info("rerank.loading_model", model=MODEL_NAME)
    app.state.model = CrossEncoder(MODEL_NAME, max_length=512)

    log.info("rerank.ready")
    yield


app = FastAPI(title="Rerank Service", lifespan=lifespan)


# ---- Endpoints ----


@app.post("/rerank", response_model=RerankResponse)
async def rerank(req: RerankRequest) -> RerankResponse:
    """Re-ranqueia candidatos com o cross-encoder e devolve top_k.

    Fluxo: monta pares ``(query, candidate.text)`` → ``model.predict(pairs)``
    devolve um score por par → ordena decrescente → trunca em ``top_k``
    → serializa.
    """
    started = time.perf_counter()

    pairs = [(req.query, c["text"]) for c in req.candidates]

    scores = app.state.model.predict(pairs).tolist()

    zipped_scores = zip(req.candidates, scores)

    sorted_scores = sorted(zipped_scores, key=lambda par: par[1], reverse=True)

    relevat_scores = sorted_scores[: req.top_k]

    list_rerank_response_items: list[RerankResponseItem] = []

    for cand, sc in relevat_scores:
        list_rerank_response_items.append(
            RerankResponseItem(
                id=cand.get("id") or cand.get("chunk_id") or "?", score=float(sc), text=cand["text"]
            )
        )

    elapsed_time = int((time.perf_counter() - started) * 1000)

    return RerankResponse(
        items=list_rerank_response_items, model=MODEL_NAME, latency_ms=elapsed_time
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe: confirma que o app subiu e o event loop responde."""
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    """Expõe o registro Prometheus (mesma cola do gateway)."""
    body, content_type = metrics_response()
    return Response(content=body, media_type=content_type)
