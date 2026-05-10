"""Testes dos schemas Pydantic compartilhados.

Aqui o teste é a especificação: ele define o contrato dos dados que cruzam
fronteiras do sistema (HTTP requests, mensagens RabbitMQ). Se um teste mudar,
todo o resto do código que troca essa mensagem precisa acompanhar.
"""

import pytest
from pydantic import ValidationError

from src.shared.schemas import (
    ChunkMessage,
    Citation,
    DocumentMessage,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryRequestMessage,
    QueryResponse,
)

# ---------------------------------------------------------------------------
# IngestRequest
# ---------------------------------------------------------------------------


def test_ingest_request_accepts_valid_pdf() -> None:
    req = IngestRequest(filename="paper.pdf", content_b64="aGVsbG8=", source_type="pdf")
    assert req.filename == "paper.pdf"
    assert req.source_type == "pdf"


def test_ingest_request_accepts_md_and_html() -> None:
    for st in ("md", "html"):
        IngestRequest(filename=f"x.{st}", content_b64="aGk=", source_type=st)


def test_ingest_request_rejects_unknown_source_type() -> None:
    """Pydantic com Literal['pdf', 'md', 'html'] deve recusar 'docx'."""
    with pytest.raises(ValidationError):
        IngestRequest(filename="x.docx", content_b64="aGk=", source_type="docx")  # type: ignore[arg-type]


def test_ingest_request_requires_all_fields() -> None:
    with pytest.raises(ValidationError):
        IngestRequest(filename="x.pdf")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# IngestResponse
# ---------------------------------------------------------------------------


def test_ingest_response_status_default_is_accepted() -> None:
    """O status default deve ser literalmente 'accepted'."""
    resp = IngestResponse(correlation_id="i-abc", doc_id="d-xyz")
    assert resp.status == "accepted"


def test_ingest_response_rejects_other_status_values() -> None:
    """Status é Literal['accepted'] — qualquer outra coisa deve falhar."""
    with pytest.raises(ValidationError):
        IngestResponse(correlation_id="i-abc", doc_id="d-xyz", status="processing")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# QueryRequest
# ---------------------------------------------------------------------------


def test_query_request_minimal() -> None:
    req = QueryRequest(question="O que é arquitetura hexagonal?")
    assert req.top_k == 5
    assert req.session_id is None


def test_query_request_with_overrides() -> None:
    req = QueryRequest(question="?", top_k=10, session_id="s-001")
    assert req.top_k == 10
    assert req.session_id == "s-001"


# ---------------------------------------------------------------------------
# Citation
# ---------------------------------------------------------------------------


def test_citation_roundtrip_preserves_data() -> None:
    """model_dump → model_validate deve devolver o objeto idêntico."""
    c = Citation(
        doc_id="abc",
        chunk_id="abc:0",
        page=2,
        snippet="texto curto do trecho",
        source="paper.pdf",
    )
    raw = c.model_dump()
    restored = Citation.model_validate(raw)
    assert c == restored


def test_citation_allows_null_page() -> None:
    """Documentos sem páginas (MD, HTML) usam page=None."""
    c = Citation(doc_id="abc", chunk_id="abc:0", page=None, snippet="x", source="readme.md")
    assert c.page is None


# ---------------------------------------------------------------------------
# QueryResponse
# ---------------------------------------------------------------------------


def test_query_response_serializes_to_json_with_all_fields() -> None:
    resp = QueryResponse(
        answer="Arquitetura hexagonal isola o domínio.",
        citations=[
            Citation(doc_id="a", chunk_id="a:0", page=1, snippet="s", source="paper.pdf"),
        ],
        usage={"tokens_in": 120, "tokens_out": 35},
        latency_ms=1450,
    )
    payload = resp.model_dump_json()
    # Sem assertar string exata: a ordem pode variar entre versões do pydantic.
    assert "tokens_in" in payload
    assert "tokens_out" in payload
    assert "Arquitetura hexagonal" in payload
    assert "1450" in payload


def test_query_response_empty_citations_is_valid() -> None:
    """Quando o retrieval não traz nada, citations=[] deve ser aceito."""
    resp = QueryResponse(
        answer="Não encontrei essa informação no corpus",
        citations=[],
        usage={"tokens_in": 0, "tokens_out": 0},
        latency_ms=42,
    )
    assert resp.citations == []


# ---------------------------------------------------------------------------
# ChunkMessage / DocumentMessage / QueryRequestMessage
# ---------------------------------------------------------------------------


def test_chunk_message_with_required_fields() -> None:
    """ChunkMessage é a unidade de trabalho da fila ingest.chunks (B2)."""
    msg = ChunkMessage(
        doc_id="a",
        chunk_id="a:0",
        text="conteúdo do chunk",
        source="paper.pdf",
        page=2,
        lang="pt",
    )
    assert msg.chunk_id == "a:0"
    assert msg.lang == "pt"


def test_chunk_message_lang_defaults_to_unk() -> None:
    """Se a detecção de idioma falhar, default 'unk' deve permitir prosseguir."""
    msg = ChunkMessage(
        doc_id="a",
        chunk_id="a:0",
        text="x",
        source="x.pdf",
        page=None,
    )
    assert msg.lang == "unk"


def test_document_message_carries_correlation_and_payload() -> None:
    """DocumentMessage é o que o gateway publica na fila ingest.documents."""
    msg = DocumentMessage(
        correlation_id="i-abc",
        doc_id="d-xyz",
        filename="paper.pdf",
        content_b64="aGVsbG8=",
        source_type="pdf",
    )
    assert msg.correlation_id == "i-abc"
    assert msg.source_type == "pdf"


def test_query_request_message_carries_reply_to() -> None:
    """QueryRequestMessage tem reply_to porque o atendimento é assíncrono.

    O gateway cria uma fila temporária `query.responses.{correlation_id}` e
    passa o nome dela em reply_to. O worker publica a resposta lá.
    """
    msg = QueryRequestMessage(
        correlation_id="q-7af3",
        reply_to="query.responses.q-7af3",
        question="?",
        top_k=5,
    )
    assert msg.session_id is None  # default, sessão é opcional
    assert msg.reply_to.startswith("query.responses.")
