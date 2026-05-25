"""Testes do recursive character splitter (`src/workers/ingest/chunking.py`).

Os testes funcionam como spec executável: cada um define um contrato que a
implementação precisa satisfazer. Estratégia recursive splitter, com fronteiras
semânticas (parágrafo → linha → frase → palavra → char) e overlap em chars
entre chunks adjacentes para preservar contexto na recuperação.

O contrato central (Task 15): todo chunk devolvido, **já com overlap aplicado**,
cabe no teto duro do modelo de embedding (nomic-v1.5, 2048 tokens), com fator
de segurança para a aproximação chars/4 errar em PT + extração de PDF.
"""

import pytest

from src.workers.ingest.chunking import chunk_text, count_tokens_approx


def test_count_tokens_approx_uses_4chars_per_token() -> None:
    assert count_tokens_approx("a" * 400) == 100


def test_chunk_text_short_returns_single_chunk() -> None:
    chunks = chunk_text("texto curto", target_tokens=800, overlap_tokens=120, max_tokens=2048)
    assert len(chunks) == 1
    assert chunks[0] == "texto curto"


def test_chunk_text_breaks_on_paragraph_boundary() -> None:
    text = ("a" * 1000) + "\n\n" + ("b" * 1000) + "\n\n" + ("c" * 1000)
    chunks = chunk_text(text, target_tokens=300, overlap_tokens=20, max_tokens=2048)
    # 1 chunk por parágrafo (fronteira respeitada — não partiu no meio do bloco)
    assert len(chunks) >= 3
    # cada bloco íntegro aparece em algum chunk (overlap pode prefixar com cauda
    # do anterior, mas o conteúdo do parágrafo continua presente como substring)
    assert any("a" * 1000 in c for c in chunks)
    assert any("b" * 1000 in c for c in chunks)
    assert any("c" * 1000 in c for c in chunks)


def test_chunk_text_overlap_is_applied() -> None:
    text = "a" * 4000  # ~1000 tokens
    chunks = chunk_text(text, target_tokens=200, overlap_tokens=40, max_tokens=2048)
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
    chunks = chunk_text(text, target_tokens=200, overlap_tokens=20, max_tokens=2048)
    for c in chunks:
        # Tolerância de 25% acima do alvo
        assert count_tokens_approx(c) <= 250


# --- Contrato do teto duro (Task 15) -----------------------------------------


# Inputs patológicos: o que detonou na Task 15. O teste antigo
# (test_..._exceeds_target_significantly) passou porque usava "frase. " * 1000
# (separador fácil) e só checava target+25% — não o teto real do modelo.
# Estes não têm separador utilizável e medem contra o teto duro pós-overlap.
@pytest.mark.parametrize(
    "text",
    [
        pytest.param("x" * 60_000, id="sem-separadores"),
        pytest.param("palavra" * 9_000, id="palavra-colada"),
        pytest.param(("a" * 12_000) + "\n\n" + ("b" * 12_000), id="paragrafos-gigantes"),
    ],
)
def test_chunk_text_garante_teto_pos_overlap(text: str) -> None:
    max_tokens = 2048
    overlap_tokens = 120
    safe_budget = max_tokens // 2 - overlap_tokens  # 904

    chunks = chunk_text(
        text,
        target_tokens=800,
        overlap_tokens=overlap_tokens,
        max_tokens=max_tokens,
    )

    assert chunks, "chunk_text não pode devolver lista vazia para texto não-vazio"
    for c in chunks:
        # Invariante central: TODO chunk, JÁ com overlap, cabe no orçamento seguro.
        assert count_tokens_approx(c) <= safe_budget, (
            f"chunk com {count_tokens_approx(c)} tokens-aprox excede o teto "
            f"{safe_budget} (max_tokens={max_tokens}, overlap={overlap_tokens})"
        )


def test_chunk_text_short_ainda_single_chunk_com_max_tokens() -> None:
    chunks = chunk_text(
        "texto curto",
        target_tokens=800,
        overlap_tokens=120,
        max_tokens=2048,
    )
    assert len(chunks) == 1
    assert chunks[0] == "texto curto"


def test_chunk_text_overlap_nao_estoura_teto() -> None:
    # Regressão direta do bug: overlap somado após o dimensionamento.
    # target alto força o caminho de acumulação; overlap não pode furar o teto.
    text = "a" * 40_000
    max_tokens = 2048
    overlap_tokens = 200
    safe_budget = max_tokens // 2 - overlap_tokens

    chunks = chunk_text(
        text,
        target_tokens=900,
        overlap_tokens=overlap_tokens,
        max_tokens=max_tokens,
    )

    assert len(chunks) >= 2
    for c in chunks:
        assert count_tokens_approx(c) <= safe_budget
