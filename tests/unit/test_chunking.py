"""Testes do recursive character splitter (`src/workers/ingest/chunking.py`).

Os testes funcionam como spec executável: cada um define um contrato que a
implementação precisa satisfazer. Estratégia recursive splitter, com fronteiras
semânticas (parágrafo → linha → frase → palavra → char) e overlap em chars
entre chunks adjacentes para preservar contexto na recuperação.
"""

from src.workers.ingest.chunking import chunk_text, count_tokens_approx


def test_count_tokens_approx_uses_4chars_per_token() -> None:
    assert count_tokens_approx("a" * 400) == 100


def test_chunk_text_short_returns_single_chunk() -> None:
    chunks = chunk_text("texto curto", target_tokens=800, overlap_tokens=120)
    assert len(chunks) == 1
    assert chunks[0] == "texto curto"


def test_chunk_text_breaks_on_paragraph_boundary() -> None:
    text = ("a" * 1000) + "\n\n" + ("b" * 1000) + "\n\n" + ("c" * 1000)
    chunks = chunk_text(text, target_tokens=300, overlap_tokens=20)
    assert len(chunks) >= 3
    # cada chunk começa com letra esperada (sem partir parágrafo no meio)
    starts = [c.lstrip()[0] for c in chunks if c.strip()]
    assert "a" in starts and "b" in starts and "c" in starts


def test_chunk_text_overlap_is_applied() -> None:
    text = "a" * 4000  # ~1000 tokens
    chunks = chunk_text(text, target_tokens=200, overlap_tokens=40)
    assert len(chunks) >= 4
    # overlap entre adjacentes (chunks compartilham caracteres em sequência)
    for i in range(len(chunks) - 1):
        tail = chunks[i][-50:]
        head = chunks[i + 1][:200]
        # algum sufixo do anterior aparece no início do próximo
        overlap_chars = sum(1 for ch in tail if ch in head)
        assert overlap_chars > 0


def test_chunk_text_no_chunk_exceeds_target_significantly() -> None:
    text = "frase. " * 1000
    chunks = chunk_text(text, target_tokens=200, overlap_tokens=20)
    for c in chunks:
        # Tolerância de 25% acima do alvo
        assert count_tokens_approx(c) <= 250
