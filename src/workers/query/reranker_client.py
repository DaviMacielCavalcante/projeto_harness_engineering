"""Cliente HTTP do rerank-service (Task 7 do B2).

Wrapper fino sobre `POST /rerank`, com retry via tenacity — mesmo pattern do
`src/shared/ollama_client.py`. O serviço já devolve os candidatos ordenados
por score e truncados em `top_k`; o client só repassa a lista `items`.
Testável isolado com respx (`tests/unit/test_reranker_client.py`).
"""

from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)


class RerankerClient:
    """Client assíncrono do rerank-service (cross-encoder bge-reranker-v2-m3)."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def rerank(
        self, query: str, candidates: list[dict[str, Any]], top_k: int
    ) -> list[dict[str, Any]]:
        """Re-ranqueia `candidates` via POST /rerank e devolve os `items`.

        Parameters
        ----------
        query : str
            Pergunta do usuário (o cross-encoder pareia com cada candidato).
        candidates : list of dict
            Candidatos do retrieval vetorial; cada um com ao menos `text` e um
            id (`id` ou `chunk_id`). Metadados extras passam transparentes.
        top_k : int
            Quantos itens o serviço deve devolver (já ordenados por score).

        Returns
        -------
        list of dict
            Os `items` da resposta — `[{id, score, text}, ...]`, em ordem
            decrescente de score.
        """
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.5, max=4),
            retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        url=f"{self._base}/rerank",
                        json={"query": query, "candidates": candidates, "top_k": top_k},
                    )

                    resp.raise_for_status()
                    
                    resp_json: list[dict[str, Any]] = resp.json()["items"]

                    return resp_json

        raise RuntimeError("unreachable")
