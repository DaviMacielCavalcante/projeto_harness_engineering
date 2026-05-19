"""Testes do cache distribuído (Redis L1/L2).

Usam um `FakeRedis` em memória — cache é barato de testar de verdade, não
precisa de Redis no ar para validar a lógica de chave/serialização. Estes
testes são o **contrato executável** da Task 2 do B2: enquanto falharem,
`cache.py` não está pronto.
"""

from src.shared.cache import Cache, sha256_hex

# ---------------------------------------------------------------------------
# Fake do client Redis: guarda exatamente o que recebe em setex e devolve
# em get (None quando a chave não existe — igual ao Redis real num miss).
# ---------------------------------------------------------------------------


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.calls: list[tuple[str, ...]] = []

    async def get(self, k: str) -> str | None:
        self.calls.append(("get", k))
        return self.store.get(k)

    async def setex(self, k: str, ttl: int, v: str) -> None:
        self.calls.append(("setex", k, str(ttl)))
        self.store[k] = v


# ---------------------------------------------------------------------------
# L1 — embedding da query
# ---------------------------------------------------------------------------


async def test_cache_get_set_embedding() -> None:
    """Miss devolve None; depois do set, o mesmo vetor volta intacto."""
    fake = FakeRedis()
    cache = Cache(client=fake)

    assert await cache.get_query_embedding("hello") is None

    await cache.set_query_embedding("hello", [0.1, 0.2])
    got = await cache.get_query_embedding("hello")

    assert got == [0.1, 0.2]


# ---------------------------------------------------------------------------
# L2 — resposta inteira, chaveada por query + ids recuperados
# ---------------------------------------------------------------------------


async def test_cache_response_keyed_by_query_and_ids() -> None:
    """Mesma query + mesmos ids → hit. Mesma query + ids diferentes → miss."""
    fake = FakeRedis()
    cache = Cache(client=fake)
    payload = {"answer": "ok", "citations": []}

    await cache.set_response("q", ["a", "b"], payload)

    assert await cache.get_response("q", ["a", "b"]) == payload
    # ids diferentes mudam a chave → não pode acertar o cache anterior
    assert await cache.get_response("q", ["a", "c"]) is None


async def test_cache_response_key_is_order_invariant() -> None:
    """A ordem dos ids recuperados não pode mudar a chave (rerank reordena)."""
    fake = FakeRedis()
    cache = Cache(client=fake)
    payload = {"answer": "ok", "citations": []}

    await cache.set_response("q", ["a", "b"], payload)

    # ["b", "a"] é o mesmo conjunto recuperado, só reordenado → deve dar HIT
    assert await cache.get_response("q", ["b", "a"]) == payload


# ---------------------------------------------------------------------------
# Hash determinístico (base de toda chave de cache)
# ---------------------------------------------------------------------------


def test_sha256_hex_deterministic() -> None:
    """Mesma entrada → sempre a mesma chave; é o que torna o cache estável."""
    assert sha256_hex("abc") == sha256_hex("abc")
    assert sha256_hex("abc") != sha256_hex("abd")
    # saída é a string hex do SHA-256 (64 chars)
    assert len(sha256_hex("abc")) == 64
