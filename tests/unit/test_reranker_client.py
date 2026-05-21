"""Testes-spec do RerankerClient (contrato executável, Task 7 do B2).

O client é um wrapper HTTP fino sobre `POST /rerank` do rerank-service, com
retry via tenacity (mesmo pattern do `ollama_client`). Mockamos o HTTP com
`respx` — não subimos o serviço real, que arrasta torch + modelo de ~600MB.

Contrato do serviço (ver `src/rerank_service/main.py`):
- request:  {"query": str, "candidates": list[dict], "top_k": int}
- response: {"items": [{"id", "score", "text"}], "model": str, "latency_ms": int}
  `items` já vem ordenado por score decrescente e truncado em top_k —
  o client NÃO reordena; só devolve a lista `items`.
"""

import json

import httpx
import pytest
import respx

from src.workers.query.reranker_client import RerankerClient

RERANK_URL = "http://rerank:8081"


@pytest.mark.asyncio
@respx.mock
async def test_rerank_returns_items_in_service_order() -> None:
    respx.post(f"{RERANK_URL}/rerank").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {"id": "b", "score": 0.9, "text": "B"},
                    {"id": "a", "score": 0.4, "text": "A"},
                ],
                "model": "bge-reranker-v2-m3",
                "latency_ms": 12,
            },
        )
    )
    client = RerankerClient(base_url=RERANK_URL)
    items = await client.rerank("q", [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}], top_k=2)
    assert [it["id"] for it in items] == ["b", "a"]
    assert items[0]["score"] == 0.9


@pytest.mark.asyncio
@respx.mock
async def test_rerank_sends_query_candidates_and_top_k() -> None:
    route = respx.post(f"{RERANK_URL}/rerank").mock(
        return_value=httpx.Response(200, json={"items": [], "model": "m", "latency_ms": 1})
    )
    client = RerankerClient(base_url=RERANK_URL)
    candidates = [{"id": "a", "text": "A"}]
    await client.rerank("minha pergunta", candidates, top_k=5)

    sent = json.loads(route.calls.last.request.content)
    assert sent == {"query": "minha pergunta", "candidates": candidates, "top_k": 5}


@pytest.mark.asyncio
@respx.mock
async def test_rerank_retries_on_500_then_succeeds() -> None:
    respx.post(f"{RERANK_URL}/rerank").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(
                200,
                json={
                    "items": [{"id": "a", "score": 0.5, "text": "A"}],
                    "model": "m",
                    "latency_ms": 3,
                },
            ),
        ]
    )
    client = RerankerClient(base_url=RERANK_URL)
    items = await client.rerank("q", [{"id": "a", "text": "A"}], top_k=1)
    assert items[0]["id"] == "a"
