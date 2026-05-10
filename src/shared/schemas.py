from typing import Any, Literal

from pydantic import BaseModel

SourceType = Literal["pdf", "md", "html"]
StatusType = Literal["accepted"]


class IngestRequest(BaseModel):
    """Body do POST /ingest: documento em base64 para indexação."""

    filename: str
    content_b64: str
    source_type: SourceType


class IngestResponse(BaseModel):
    """Resposta do POST /ingest: aceite assíncrono; acompanhar via correlation_id."""

    correlation_id: str
    doc_id: str
    status: StatusType = "accepted"


class ChunkMessage(BaseModel):
    """Chunk pronto para embedding + upsert no Qdrant; fluxo da fila `chunk_handler`."""

    doc_id: str
    chunk_id: str
    text: str
    source: str
    page: int | None
    lang: str | None = "unk"


class DocumentMessage(BaseModel):
    """Documento bruto para parse + chunking; fluxo da fila `document_handler`."""

    correlation_id: str
    doc_id: str
    filename: str
    content_b64: str
    source_type: SourceType


class QueryRequest(BaseModel):
    """Body do POST /query: pergunta + sessão opcional + top_k do retrieval."""

    session_id: str | None = None
    question: str
    top_k: int = 5


class Citation(BaseModel):
    """Referência a um chunk que fundamenta a resposta (campo de `QueryResponse`)."""

    doc_id: str
    chunk_id: str
    page: int | None = None
    snippet: str
    source: str


class QueryResponse(BaseModel):
    """Resposta do POST /query: texto gerado + citações + métricas de uso e latência."""

    answer: str
    citations: list[Citation]
    usage: dict[str, Any]
    latency_ms: int


class QueryRequestMessage(BaseModel):
    """Mensagem da fila de queries; padrão RPC — worker responde em `reply_to`."""

    session_id: str | None = None
    correlation_id: str
    reply_to: str
    question: str
    top_k: int = 5
