"""Testes do módulo de configuração.

Estes testes travam o contrato dos defaults e do override via env.
Se alguém mudar um default sem querer, o teste avisa antes de virar bug em runtime.
"""

import pytest

from src.shared.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Limpa variáveis de ambiente que poderiam interferir nos testes.

    Sem isso, um shell que tem RABBITMQ_URL=algo herdado faria os testes
    de defaults falharem misteriosamente. autouse=True aplica a todos os testes
    deste módulo automaticamente.
    """
    for var in [
        "RABBITMQ_URL",
        "OLLAMA_URL",
        "QDRANT_URL",
        "REDIS_URL",
        "EMBEDDING_MODEL",
        "GENERATION_MODEL",
        "LOG_LEVEL",
        "SERVICE_NAME",
    ]:
        monkeypatch.delenv(var, raising=False)


def test_settings_loads_expected_defaults():
    """Sem nenhuma env var, todos os defaults batem com o esperado pelo plano B1."""
    s = Settings(_env_file=None)

    # Mensageria
    assert s.rabbitmq_url == "amqp://guest:guest@rabbitmq:5672/"
    assert s.queue_ingest_documents == "ingest.documents"
    assert s.queue_ingest_chunks == "ingest.chunks"
    assert s.queue_query_requests == "query.requests"

    # Inferência
    assert s.ollama_url == "http://ollama:11434"
    assert s.embedding_model == "nomic-embed-text"
    assert s.generation_model == "qwen2.5:7b-instruct"
    assert s.generation_num_ctx == 8192
    assert s.generation_temperature == 0.2

    # Vector DB
    assert s.qdrant_url == "http://qdrant:6333"
    assert s.qdrant_collection == "se_corpus"
    assert s.embedding_dim == 768

    # Cache
    assert s.redis_url == "redis://redis:6379/0"

    # Chunking
    assert s.chunk_target_tokens == 800
    assert s.chunk_overlap_tokens == 120

    # Observabilidade
    assert s.log_level == "INFO"
    assert s.service_name == "unset"

    # Retrieval
    assert s.retrieval_top_k_initial == 20
    assert s.retrieval_top_k_final == 5


def test_settings_overrides_via_env(monkeypatch):
    """Variável de ambiente do processo deve sobrescrever o default.

    TODO (Davi):
        1. Use `monkeypatch.setenv("RABBITMQ_URL", "<algum valor diferente do default>")`
           para definir a variável.
        2. Instancie `Settings(_env_file=None)` (igual o teste de cima).
        3. Asserte que `s.rabbitmq_url` é o valor que você setou.
        4. Faça o mesmo para mais 1-2 campos de tipos diferentes
           (ex: int como `chunk_target_tokens`, float como `generation_temperature`).
           Note como o pydantic-settings converte string -> int/float automaticamente.

    Por que isso importa: confirma que o Modo 2 (distribuído via Tailscale)
    vai funcionar — quando o .env.distributed estiver com URLs do PC1,
    elas têm que sobrescrever os defaults do compose.
    """
    
    monkeypatch.setenv("RABBITMQ_URL", "override-rabbit")
    monkeypatch.setenv("OLLAMA_URL", "override-ollama")
    monkeypatch.setenv("QDRANT_URL", "override-qdrant")
    monkeypatch.setenv("REDIS_URL", "override-redis")
    monkeypatch.setenv("GENERATION_TEMPERATURE", "0.9")
    monkeypatch.setenv("CHUNK_TARGET_TOKENS", "1000")
    
    s = Settings(_env_file=None)
    
    assert s.ollama_url == "override-ollama"
    assert s.qdrant_url == "override-qdrant"
    assert s.redis_url == "override-redis"
    assert s.rabbitmq_url == "override-rabbit"
    assert s.generation_temperature == 0.9
    assert isinstance(s.generation_temperature, float)
    assert s.chunk_target_tokens == 1000
    assert isinstance(s.chunk_target_tokens, int)
    


def test_settings_ignores_unknown_env_vars(monkeypatch):
    """Variáveis não declaradas no schema devem ser silenciosamente ignoradas.

    Isso evita que um typo numa env var (ex: OLAMA_URL em vez de OLLAMA_URL)
    quebre o boot do gateway. Em vez de erro, pydantic-settings só ignora
    e usa o default — o que é coerente com `extra="ignore"` no model_config.
    """
    monkeypatch.setenv("THIS_IS_NOT_A_REAL_SETTING", "whatever")
    s = Settings(_env_file=None)
    # Se não levantou exceção, está bom. Sanity check em algum default conhecido:
    assert s.ollama_url == "http://ollama:11434"
