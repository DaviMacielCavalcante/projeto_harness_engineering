"""Configuração centralizada do projeto, carregada de variáveis de ambiente.

Todas as URLs de serviços, nomes de filas, modelos e parâmetros de pipeline
ficam aqui. Cada componente (gateway, workers, rerank-service) importa a
mesma instância `settings` — fonte única da verdade.

Em runtime:
- Modo 1 (single-host): defaults do compose já funcionam (DNS interno).
- Modo 2 (distribuído): preencher .env.distributed com IPs Tailscale.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Schema das variáveis de ambiente do projeto.

    Pydantic-settings lê automaticamente:
    1. variáveis de ambiente do processo (case-insensitive),
    2. arquivo `.env` na raiz (se existir).

    Quem ganha em conflito? Variável de ambiente do processo > .env > default.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Mensageria
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    queue_ingest_documents: str = "ingest.documents"
    queue_ingest_chunks: str = "ingest.chunks"
    queue_query_requests: str = "query.requests"

    #Inferência
    ollama_url: str = "http://ollama:11434"
    embedding_model: str = "nomic-embed-text"
    generation_model: str = "qwen2.5:7b-instruct"
    generation_num_ctx: int = 8192
    generation_temperature: float = 0.2

    # Vector DB (Qdrant)
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "se_corpus"
    embedding_dim: int = 768

    # Cache (Redis)
    redis_url: str = "redis://redis:6379/0"

    # Chunking
    chunk_target_tokens: int = 800
    chunk_overlap_tokens: int = 120

    # Observabilidade
    log_level: str = "INFO"
    service_name: str = "unset"

    # Retrieval
    retrieval_top_k_initial: int = 20
    retrieval_top_k_final: int = 5


# Singleton: importe `settings` em qualquer módulo que precise de config.
# Evita re-ler env a cada chamada e garante que todos os componentes vêem o mesmo.
settings = Settings()
