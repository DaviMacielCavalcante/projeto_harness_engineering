"""Testes do histórico de sessão com sumarização adaptativa.

Mesmo espírito do `test_cache.py`: `FakeRedis` em memória, sem subir Redis.
Estes testes são o **contrato executável** da Task 9 do B2 — enquanto
falharem, `session.py` não está pronto.

A sumarização do B2 é um *stub* (concat de texto). O ponto de extensão é o
`summarizer` injetável: o último teste fixa que o `SessionStore` apenas
*chama* a estratégia, sem conhecer como ela resume. No B3 troca-se por um
summarizer que chama o LLM, sem tocar nesta classe.
"""

from src.shared.session import SessionStore, concat_summarizer

# ---------------------------------------------------------------------------
# Fake do client Redis: idêntico ao do test_cache (só get/setex).
# ---------------------------------------------------------------------------


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, k: str) -> str | None:
        return self.store.get(k)

    async def setex(self, k: str, ttl: int, v: str) -> None:
        self.store[k] = v


# ---------------------------------------------------------------------------
# Histórico recente: cap em max_turns, mantendo os mais novos
# ---------------------------------------------------------------------------


async def test_history_caps_at_max_turns() -> None:
    """Após N appends > max_turns, só os max_turns mais recentes ficam."""
    store = SessionStore(client=FakeRedis(), max_turns=3)

    for i in range(5):
        await store.append("s1", question=f"q{i}", answer=f"a{i}")

    history = await store.get_history("s1")

    assert len(history) == 3
    # mantém os 3 mais recentes, em ordem cronológica
    assert [turn["q"] for turn in history] == ["q2", "q3", "q4"]


async def test_overflow_moves_oldest_to_summary() -> None:
    """Os turnos despejados (q0, q1) precisam aparecer no resumo."""
    store = SessionStore(client=FakeRedis(), max_turns=3)

    for i in range(5):
        await store.append("s1", question=f"q{i}", answer=f"a{i}")

    summary = await store.get_summary("s1")

    assert summary is not None
    assert "q0" in summary
    assert "q1" in summary


# ---------------------------------------------------------------------------
# Sessão vazia: miss devolve estruturas vazias, não erro
# ---------------------------------------------------------------------------


async def test_empty_session_returns_empty() -> None:
    """Sessão inexistente: histórico [] e resumo None (igual a um miss de cache)."""
    store = SessionStore(client=FakeRedis())

    assert await store.get_history("none") == []
    assert await store.get_summary("none") is None


# ---------------------------------------------------------------------------
# Ponto de extensão: a estratégia injetada é quem resume (Strategy/DI)
# ---------------------------------------------------------------------------


async def test_injected_summarizer_is_used() -> None:
    """O SessionStore só chama o summarizer; a regra de resumo mora nele.

    Injeta uma estratégia-espiã que registra cada turno despejado e produz
    um resumo determinístico, provando que o B3 pode trocar a concat por um
    summarizer-LLM sem mexer no SessionStore.
    """
    seen: list[dict[str, str]] = []

    def spy_summarizer(current: str, evicted: dict[str, str]) -> str:
        seen.append(evicted)
        return f"{current}|{evicted['q']}"

    store = SessionStore(client=FakeRedis(), max_turns=2, summarizer=spy_summarizer)

    for i in range(4):
        await store.append("s1", question=f"q{i}", answer=f"a{i}")

    # max_turns=2 e 4 appends → q0 e q1 foram despejados, nessa ordem
    assert [turn["q"] for turn in seen] == ["q0", "q1"]
    assert await store.get_summary("s1") == "|q0|q1"


def test_concat_summarizer_appends_turn() -> None:
    """A estratégia default do B2 anexa o turno ao resumo existente (sem perder o atual)."""
    out = concat_summarizer("resumo previo", {"q": "qx", "a": "ax"})

    assert "resumo previo" in out
    assert "qx" in out
    assert "ax" in out
