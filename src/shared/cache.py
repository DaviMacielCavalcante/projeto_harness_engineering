"""Cache distribuído em Redis, em duas camadas (padrão cache-aside).

- **L1 — embedding da query** (`emb:{hash}`, TTL longo): o vetor do
  `nomic-embed-text` para uma pergunta. Pergunta repetida não paga outra
  chamada de embedding no Ollama.
- **L2 — resposta inteira** (`resp:{hash}`, TTL curto): a `QueryResponse`
  já montada. Hit aqui curto-circuita o pipeline inteiro
  (retrieval + rerank + generate).

Por que um `Protocol` para o client em vez de importar `redis.asyncio`
direto? **Injeção de dependência**: `Cache` não precisa saber qual é o
client concreto, só que ele tem `get`/`setex`. Isso deixa o módulo testável
com um fake em memória (ver `tests/unit/test_cache.py`) sem subir Redis —
e é exatamente o bucket "TDD canônico" do CLAUDE.md.

Padrão cache-aside, para fixar antes de implementar:
    valor = cache.get(chave)
    se valor existe        -> usa (HIT)
    se valor é None (miss) -> calcula caro, cache.set(chave, valor), usa
"""

import hashlib
import json
from typing import Any, Protocol


def sha256_hex(s: str) -> str:
    """Hash hexadecimal estável de uma string (base de toda chave de cache).

    Parameters
    ----------
    s : str
        Texto a ser resumido (query, ou query+ids concatenados).

    Returns
    -------
    str
        Os 64 caracteres hex do SHA-256 de ``s``.
    """
    string_bytes = s.encode(encoding="utf8")

    hash_string = hashlib.sha256(string=string_bytes).hexdigest()

    return hash_string


class _RedisLike(Protocol):
    """Interface mínima que `Cache` exige de um client Redis.

    Só os dois métodos usados — qualquer objeto com essa forma (o
    `redis.asyncio` real ou o `FakeRedis` do teste) serve. É o contrato
    da injeção de dependência.
    """

    async def get(self, k: str) -> str | bytes | None: ...

    async def setex(self, k: str, ttl: int, v: str) -> Any: ...


class Cache:
    """Cache L1 (embedding de query) + L2 (resposta inteira) sobre Redis."""

    # TTLs como política de cache (constantes, não env — mudam raramente).
    # L1: embedding de uma pergunta praticamente não muda -> pode viver dias.
    # L2: resposta pode envelhecer quando o corpus muda -> janela curta.
    L1_TTL = 7 * 24 * 3600  # 7 dias, em segundos
    L2_TTL = 3600  # 1 hora, em segundos

    def __init__(self, client: _RedisLike) -> None:
        # Plumbing de DI (estrutura, não miolo): guarda o client injetado.
        self._r = client

    async def get_query_embedding(self, query: str) -> list[float] | None:
        """Lê o embedding cacheado da query, ou ``None`` se não houver.

        Returns
        -------
        list of float or None
            O vetor no hit; ``None`` no miss (não é erro — é cache-aside).
        """
        key = "emb:" + sha256_hex(query)

        cached_embedded = await self._r.get(key)

        if not cached_embedded:
            return None

        json_embedded: list[float] = json.loads(cached_embedded)

        return json_embedded

    async def set_query_embedding(self, query: str, vec: list[float]) -> None:
        """Grava o embedding da query com TTL de L1."""
        key = "emb:" + sha256_hex(query)

        string_or_bytes_query = json.dumps(vec)

        await self._r.setex(key, self.L1_TTL, string_or_bytes_query)

    @staticmethod
    def _resp_key(query: str, retrieved_ids: list[str]) -> str:
        """Deriva a chave de L2 a partir da query e dos ids recuperados.

        A resposta só é a mesma se a pergunta E o conjunto de chunks usados
        forem os mesmos — por isso a chave combina os dois.

        Parameters
        ----------
        query : str
            Pergunta do usuário.
        retrieved_ids : list of str
            Ids dos chunks que fundamentaram a resposta.

        Returns
        -------
        str
            Chave de cache L2 (com prefixo ``resp:``).
        """
        sorted_retrieved_ids = sorted(retrieved_ids)

        all_ids = ",".join(sorted_retrieved_ids)

        all_ids_with_query = all_ids + " | " + query

        resp_key = "resp:" + sha256_hex(s=all_ids_with_query)

        return resp_key

    async def get_response(self, query: str, retrieved_ids: list[str]) -> dict[str, Any] | None:
        """Lê a resposta cacheada (L2), ou ``None`` no miss."""
        resp_key = self._resp_key(query=query, retrieved_ids=retrieved_ids)

        cached_key = await self._r.get(resp_key)

        if not cached_key:
            return None

        json_embedded: dict[str, Any] = json.loads(cached_key)

        return json_embedded

    async def set_response(
        self, query: str, retrieved_ids: list[str], payload: dict[str, Any]
    ) -> None:
        """Grava a resposta (L2) com TTL curto."""
        key = self._resp_key(query=query, retrieved_ids=retrieved_ids)

        json_resp = json.dumps(payload)

        await self._r.setex(key, self.L2_TTL, json_resp)
