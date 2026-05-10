from pydantic import BaseModel
from typing import Literal

SourceType = Literal["pdf", "md", "html"]
StatusType = Literal["accepted"]

class IngestRequest(BaseModel):
    
    filename: str
    content_b64: str
    source_type: SourceType
    
class IngestResponse(BaseModel):
    
    correlation_id: str 
    doc_id: str
    status: StatusType = "accepted"

class ChunkMessage(BaseModel):
    
    doc_id: str
    chunk_id: str
    text: str 
    source: str 
    page: int | None
    lang: str | None = "unk"
    
class DocumentMessage(BaseModel):
    
    correlation_id: str
    doc_id: str
    filename: str
    content_b64: str 
    source_type: SourceType

class QueryRequest(BaseModel):
    
    session_id: str = None
    question: str
    top_k: int = 5

class Citation(BaseModel):
    
    doc_id: str
    chunk_id: str 
    page: int | None = None
    snippet: str 
    source: str

class QueryResponse(BaseModel):
    
    answer: str 
    citations: list[Citation]
    usage: dict 
    latency_ms: int

class QueryRequestMessage(BaseModel):
    
    session_id: str | None = None
    correlation_id: str 
    reply_to: str 
    question: str 
    top_k: int = 5