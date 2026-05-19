"""Registro Prometheus único do projeto (cobre o requisito 4.4 / spec §7.1).

Todo componente (gateway, workers, rerank-service) importa as métricas
**deste módulo** e expõe `metrics_response()` no seu `/metrics`. Registro
único = um `CollectorRegistry` compartilhado, sem métricas duplicadas.

Como escolher o tipo de métrica (use isto para preencher os TODOs):

- **Counter** — só sobe, nunca desce. Totais acumulados: nº de erros,
  tokens, docs indexados, cache hits. Lê-se via `rate()` no Prometheus.
- **Histogram** — distribuição de valores observados (latência). Gera
  buckets + soma + contagem → permite p50/p95/p99. Os `buckets` precisam
  cobrir a faixa real do que você mede (ms a s para query; s a min para
  ingestão de doc grande).
- **Gauge** — valor instantâneo que sobe **e** desce: profundidade de fila,
  requests em voo. Não é acumulado.

Cuidado com **cardinalidade de label**: label só com conjunto pequeno e
fechado de valores (`status`, `phase`, `cache_layer`). NUNCA use
`correlation_id`, query crua ou `doc_id` como label — explode a memória do
Prometheus. Isso vai pro log estruturado (Loki), não pra label de métrica.

Mapa das métricas ↔ spec §7.1 está nos TODOs abaixo.
"""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Registro compartilhado: todas as métricas se registram aqui, e
# metrics_response() serializa este registro.
REGISTRY = CollectorRegistry()

request_duration = Histogram(
    "rag_request_duration_seconds",
    "Latência das requisições HTTP do gateway",
    labelnames=("endpoint", "status"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
    registry=REGISTRY,
)

errors = Counter(
    "rag_errors_total",
    "Erros por serviço e tipo",
    labelnames=("service", "error_type"),
    registry=REGISTRY,
)

query_pipeline_duration = Histogram(
    "rag_query_pipeline_duration_seconds",
    "Latência por fase do pipeline de query",
    labelnames=("phase", "worker_id"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    registry=REGISTRY,
)

ingest_pipeline_duration = Histogram(
    "rag_ingest_pipeline_duration_seconds",
    "Latência por fase do pipeline de ingestão",
    labelnames=("phase", "worker_id"),
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 5, 30, 120, 600),
    registry=REGISTRY,
)

tokens_total = Counter(
    "rag_tokens_total",
    "Quantidade de tokens utilizada",
    labelnames=("direction", "model"),
    registry=REGISTRY,
)

throughput_docs = Counter(
    "rag_throughput_docs_total",
    "Documentos indexados",
    labelnames=("worker_id",),
    registry=REGISTRY,
)

throughput_queries = Counter(
    "rag_throughput_queries_total",
    "Queries atendidas",
    labelnames=("worker_id", "status"),
    registry=REGISTRY,
)

cache_hits = Counter(
    "rag_cache_hits_total", "Cache hits", labelnames=("cache_layer",), registry=REGISTRY
)

cache_misses = Counter(
    "rag_cache_misses_total", "Cache misses", labelnames=("cache_layer",), registry=REGISTRY
)

queue_depth = Gauge(
    "rag_queue_depth",
    "Profundidade das filas RabbitMQ",
    labelnames=("queue_name",),
    registry=REGISTRY,
)

ollama_inflight = Gauge(
    "rag_ollama_inflight_requests", "Requisições ao Ollama em voo", registry=REGISTRY
)


def metrics_response() -> tuple[bytes, str]:
    """Serializa o registro no formato texto do Prometheus.

    Returns
    -------
    tuple of (bytes, str)
        Corpo da resposta e o `Content-Type` que o endpoint `/metrics`
        deve devolver.
    """
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
