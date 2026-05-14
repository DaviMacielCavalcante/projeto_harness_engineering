"""Testes do parser de documentos (`src/workers/ingest/parsing.py`).

Cobre só os ramos triviais e isoláveis: decode base64 + routing por tipo +
guard de tipo inválido. PDF (rota `_parse_pdf`) é validado pelo smoke
ponta-a-ponta — testar com PDF real em unit é frágil (ou exige fixture binária,
ou mocka `PdfReader`, que é anti-pattern).
"""

import base64

import pytest

from src.workers.ingest.parsing import parse_document


@pytest.mark.parametrize("source_type", ["md", "html"])
def test_parse_document_round_trips_text_for_non_paginated_types(
    source_type: str,
) -> None:
    original = "# título\n\nparágrafo com acentuação: ção, ã, é."
    content_b64 = base64.b64encode(original.encode("utf-8")).decode("ascii")

    pages = parse_document(content_b64, source_type)  # type: ignore[arg-type]

    assert pages == [(None, original)]


def test_parse_document_decodes_invalid_utf8_with_replacement() -> None:
    # bytes 0x80, 0x81 não formam sequência UTF-8 válida. Esperamos que o
    # decode com errors="replace" troque por '�' em vez de levantar.
    raw = b"texto valido " + b"\x80\x81" + b" mais texto"
    content_b64 = base64.b64encode(raw).decode("ascii")

    pages = parse_document(content_b64, "md")

    assert len(pages) == 1
    page_number, text = pages[0]
    assert page_number is None
    assert "texto valido" in text
    assert "mais texto" in text
    assert "�" in text  # caractere de substituição entrou


def test_parse_document_raises_on_unsupported_source_type() -> None:
    content_b64 = base64.b64encode(b"qualquer coisa").decode("ascii")

    with pytest.raises(ValueError, match="source_type"):
        parse_document(content_b64, "docx")  # type: ignore[arg-type]
