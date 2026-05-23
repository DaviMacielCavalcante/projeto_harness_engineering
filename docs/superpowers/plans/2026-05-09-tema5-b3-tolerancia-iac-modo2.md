# Tema 5 — B3: Tolerância a Falhas + IaC + Modo 2 Distribuído

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o sistema resiliente (DLQ, retry, fallback) e operável em produção: provisionar os 3 PCs via Ansible, distribuir os containers via Terraform (provider docker), conectar tudo via Tailscale, validar smoke distribuído, completar a stack de observabilidade (Grafana + Loki + Promtail + dashboards) e ingerir o corpus de ~80 PDFs.

**Architecture:** Mantém arquitetura do B2. Adições: DLX (Dead-Letter Exchange) RabbitMQ + filas `*.dlq`. Estratégia de fallback no gateway (degraded mode). Terraform descreve containers com `host_role ∈ {server, worker}`. Ansible provisiona Docker, Tailscale, NVIDIA toolkit (PC1) e roda Terraform via SSH. Grafana datasources Prometheus + Loki, dashboard "RAG Distribuído" com 4 painéis. Promtail em cada PC envia logs JSON para Loki em PC1.

**Tech Stack:** Adições: Terraform >=1.9 com provider `kreuzwerker/docker` v3.x, Ansible >=2.16, Loki + Promtail (`grafana/loki`, `grafana/promtail`), Grafana com provisioning. Tailscale instalado nativamente em cada host.

**Bloco do cronograma:** B3 (17–20/05/2026, 4 dias).

**Marco luz-verde do bloco:** sistema funcionando em Modo 2 distribuído (3 PCs reais via Tailscale); chaos test passa (mata worker, mata Ollama, sistema se recupera); Grafana mostra dashboards populados; corpus de ~80 docs indexado.

---

## Estrutura de arquivos a criar/modificar

```
projeto_harness_engineering/
├── .env.distributed                                  # CREATE: template Modo 2
├── docker-compose.yml                                # MODIFY: adiciona loki, promtail, grafana
├── infra/
│   ├── ansible/
│   │   ├── inventory.yml                             # CREATE
│   │   ├── ansible.cfg                               # CREATE
│   │   ├── playbook-bootstrap.yml                    # CREATE
│   │   ├── playbook-deploy.yml                       # CREATE
│   │   └── roles/
│   │       ├── docker/tasks/main.yml                 # CREATE
│   │       ├── tailscale/tasks/main.yml              # CREATE
│   │       └── nvidia/tasks/main.yml                 # CREATE (só PC1)
│   ├── terraform/
│   │   ├── main.tf                                   # CREATE
│   │   ├── variables.tf                              # CREATE
│   │   ├── outputs.tf                                # CREATE
│   │   ├── modules/
│   │   │   ├── server/main.tf                        # CREATE
│   │   │   └── worker/main.tf                        # CREATE
│   │   └── envs/
│   │       ├── pc1.tfvars                            # CREATE
│   │       ├── pc2.tfvars                            # CREATE
│   │       └── pc3.tfvars                            # CREATE
│   ├── grafana/
│   │   ├── datasources/datasources.yml               # CREATE
│   │   └── dashboards/rag-distribuido.json           # CREATE
│   ├── loki/loki-config.yml                          # CREATE
│   ├── promtail/promtail-config.yml                  # CREATE
│   └── prometheus/prometheus.yml                     # CREATE (se não veio do B2)
├── src/
│   ├── shared/
│   │   ├── messaging.py                              # MODIFY: declara DLX/DLQ
│   │   └── workers_metrics_server.py                 # CREATE: /metrics em workers
│   ├── gateway/routes.py                             # MODIFY: degraded mode no /query
│   └── workers/{ingest,query}/main.py                # MODIFY: chamar workers_metrics_server
├── scripts/
│   ├── seed_corpus.py                                # CREATE: ingere ~80 PDFs
│   ├── chaos_test.sh                                 # CREATE: kill workers, kill ollama
│   ├── dlq_inspector.py                              # CREATE
│   └── deploy.sh                                     # CREATE: wrapper de Ansible
└── tests/integration/
    └── test_dlq.py                                   # CREATE
```

---

## Task 1: DLX e DLQ no RabbitMQ

**Files:**
- Modify: `src/shared/messaging.py`
- Create: `tests/integration/test_dlq.py`

- [x] **Step 1: Reescrever `declare_queues` para criar DLX + filas com `x-dead-letter-exchange`** ✓ 2026-05-22: `declare_topology(conn, *bases)` substituiu `declare_queues`. DLX `rag.dlx` (DIRECT, durable), e por base: DLQ `f"{base}.dlq"` (durable) bindada com `routing_key=base` + fila principal com `arguments={"x-dead-letter-exchange": "rag.dlx", "x-dead-letter-routing-key": base}`. Em `gateway/main.py`, lifespan passou a chamar `declare_topology(conn, settings.queue_ingest_documents, settings.queue_ingest_chunks, settings.queue_query_requests)`. Code-partner.

Em `src/shared/messaging.py`, substitua a função `declare_queues` por:

```python
async def declare_topology(conn) -> None:
    """Declara filas principais com DLX + filas DLQ correspondentes.

    Política: 3 nacks → mensagem vai para a DLQ (configurado por consumer via reject sem requeue).
    """
    channel = await conn.channel()
    try:
        # Exchange dead-letter (todas as DLQs ficam atrás dele)
        dlx = await channel.declare_exchange(
            "rag.dlx",
            type=aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

        for base in ("ingest.documents", "ingest.chunks", "query.requests"):
            # DLQ: queue + binding na DLX
            dlq = await channel.declare_queue(f"{base}.dlq", durable=True)
            await dlq.bind(dlx, routing_key=base)

            # Queue principal com x-dead-letter-exchange/key
            await channel.declare_queue(
                base,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "rag.dlx",
                    "x-dead-letter-routing-key": base,
                },
            )
    finally:
        await channel.close()
```

E onde quer que `declare_queues` era chamado (gateway main.py), substitua por `declare_topology(conn)`.

> Nota: queues criadas em B1/B2 sem esses argumentos precisam ser apagadas e recriadas. O smoke test do B3 inclui essa limpeza:
>
> ```bash
> docker exec rag-rabbitmq rabbitmqctl list_queues
> docker exec rag-rabbitmq rabbitmqctl delete_queue ingest.documents
> docker exec rag-rabbitmq rabbitmqctl delete_queue ingest.chunks
> docker exec rag-rabbitmq rabbitmqctl delete_queue query.requests
> # ou: make down -v && make dev (mais limpo)
> ```

- [x] **Step 2: Atualizar `consume_forever` para nack-sem-requeue depois de N tentativas** ✓ 2026-05-22: ack/nack agora manual (saiu o `async with msg.process()`). Contador de tentativas vive no header `x-attempts` da mensagem; cada iteração calcula `attempts = 1 + cast(int, (msg.headers or {}).get("x-attempts", 0))`. No except: `attempts >= max_attempts` → `reject(requeue=False)` (cai na DLX via arguments → DLQ); senão republica cópia na mesma fila com `dict(msg.headers or {})` + `x-attempts` incrementado, e ack do original. **Divergência mínima do plano:** usei `cast(int, ...)` em vez de `int(...)` na leitura do header — o union de `FieldValue` (bytes/Decimal/FieldArray/datetime/None/...) inclui tipos não-conversíveis pra `int`, mypy rejeita `int(...)`; `cast` é promessa pura, consistente com a convenção do projeto (`RerankerClient`, §8.7 do relatório). Code-partner.

Substituir o bloco `async with msg.process(requeue=False)` por uma estratégia explícita:

```python
async def consume_forever(
    conn,
    queue_name: str,
    handler,
    prefetch: int = 1,
    max_attempts: int = 3,
) -> None:
    import json
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=prefetch)
    queue = await channel.declare_queue(queue_name, passive=True)
    async with queue.iterator() as it:
        async for msg in it:
            attempts = 1 + int((msg.headers or {}).get("x-attempts", 0) or 0)
            try:
                payload = json.loads(msg.body)
                await handler(msg, payload)
                await msg.ack()
            except Exception as exc:  # noqa: BLE001
                if attempts >= max_attempts:
                    # Estoura tentativas → vai para DLQ (reject sem requeue, com x-dead-letter-*)
                    await msg.reject(requeue=False)
                else:
                    # Republica com header incrementado para retentar
                    headers = dict(msg.headers or {})
                    headers["x-attempts"] = attempts
                    await channel.default_exchange.publish(
                        aio_pika.Message(
                            body=msg.body,
                            headers=headers,
                            correlation_id=msg.correlation_id,
                            reply_to=msg.reply_to,
                            content_type=msg.content_type,
                        ),
                        routing_key=queue_name,
                    )
                    await msg.ack()  # ack do original; o requeue foi via republish manual
```

- [x] **Step 3: Teste de integração da DLQ** ✓ 2026-05-22 (IA implementou — teste é contrato executável, fronteira code-partner §2.5 do `USO_DE_IA.md`). `tests/integration/test_dlq.py`: `test_message_lands_in_dlq_after_max_attempts` declara topologia com nomes únicos (`test.b3.dlx`/`test.b3.dlq.queue`/`...dlq` — isolam de filas reais em broker compartilhado), handler `always_fails` registrando cada entrega numa lista, consumer em `asyncio.create_task`, publish, polling com teto ~15s, cancel limpo (`cancel()` + `await task` + `except CancelledError`), assert `len(attempts_seen) == 3` + `dlq.declaration_result.message_count >= 1` (com `passive=True`). **Divergências do template do plano:** (a) tipagem strict adicionada (`list[int]`, `AbstractIncomingMessage`, `dict[str, Any]`); (b) `await consumer_task` após `cancel()` pra evitar warning de "task was destroyed but it is pending" no teardown do pytest-asyncio; (c) mensagens `f"..."` nos asserts pra diagnóstico de timing flaky. **Validação:** `RUN_INTEGRATION=1 uv run pytest tests/integration/test_dlq.py -v` → 1 passed em 0.59s; `make smoke` verde sem regressão (B1 + B2 todos os asserts: 41.99s/8.7s/3 citações).

`tests/integration/test_dlq.py`:

```python
"""Testa que mensagens com erro vão para a DLQ após max_attempts.

Requer: RabbitMQ rodando localmente.
Rode com: RUN_INTEGRATION=1 uv run pytest tests/integration/test_dlq.py -v
"""
import asyncio
import json
import os
import pytest
import aio_pika

from src.shared.messaging import connect, consume_forever, declare_topology, publish_json


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="define RUN_INTEGRATION=1 e suba RabbitMQ"
)


@pytest.mark.asyncio
async def test_message_lands_in_dlq_after_3_attempts():
    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    queue_name = "test.dlq.queue"
    dlq_name = f"{queue_name}.dlq"

    async with connect(url) as conn:
        # Setup: declara DLX + queue com argumentos
        ch = await conn.channel()
        dlx = await ch.declare_exchange("test.dlx", aio_pika.ExchangeType.DIRECT, durable=True)
        dlq = await ch.declare_queue(dlq_name, durable=True)
        await dlq.bind(dlx, routing_key=queue_name)
        await ch.declare_queue(queue_name, durable=True, arguments={
            "x-dead-letter-exchange": "test.dlx",
            "x-dead-letter-routing-key": queue_name,
        })
        await ch.close()

        attempts_seen = []

        async def always_fails(msg, payload):
            attempts_seen.append(1)
            raise RuntimeError("explode")

        async def consume():
            await consume_forever(conn, queue_name, always_fails, max_attempts=3)

        consumer_task = asyncio.create_task(consume())

        await publish_json(conn, queue_name, {"x": 1})

        # Aguarda 3 tentativas
        for _ in range(30):
            if len(attempts_seen) >= 3:
                break
            await asyncio.sleep(0.5)

        consumer_task.cancel()

        # Verifica que mensagem está na DLQ
        ch = await conn.channel()
        dlq_queue = await ch.declare_queue(dlq_name, durable=True, passive=True)
        assert dlq_queue.declaration_result.message_count >= 1
        await ch.close()
```

Run: `RUN_INTEGRATION=1 uv run pytest tests/integration/test_dlq.py -v`
Expected: PASS.

---

## Task 2: Fallback "degraded mode" no gateway

**Files:**
- Modify: `src/gateway/routes.py`

- [ ] **Step 1: Adicionar timeout configurável e fallback chunks-only**

No endpoint `/query`, quando o `iterator(timeout=120)` expirar (servidor de inferência caído ou pool sobrecarregado), em vez de devolver 504 vazio, fazer um retrieval direto contra o Qdrant e devolver os chunks brutos com status `degraded`.

Acrescente import:
```python
from qdrant_client import AsyncQdrantClient
from src.shared.ollama_client import OllamaClient
```

Em `lifespan` de `main.py`, instancie clients para `app.state.qdrant` e `app.state.ollama`:
```python
app.state.qdrant = AsyncQdrantClient(url=settings.qdrant_url)
app.state.ollama = OllamaClient(base_url=settings.ollama_url)
```

Em `routes.py`, substitua o `raise HTTPException(504, ...)` por:

```python
            # Timeout no atendimento por worker → fallback degraded mode
            log.warning("query.timeout_fallback")
            try:
                q_vec = await request.app.state.ollama.embed(req.question, model=settings.embedding_model)
                hits = await request.app.state.qdrant.search(
                    collection_name=settings.qdrant_collection,
                    query_vector=q_vec,
                    limit=req.top_k,
                )
                citations = [
                    {
                        "doc_id": h.payload["doc_id"],
                        "chunk_id": h.payload["chunk_id"],
                        "page": h.payload.get("page"),
                        "snippet": h.payload["text"][:240],
                        "source": h.payload["source"],
                    }
                    for h in hits
                ]
                return QueryResponse(
                    answer="[degraded mode] sem síntese; veja as citações abaixo.",
                    citations=citations,
                    usage={"tokens_in": 0, "tokens_out": 0},
                    latency_ms=int(time.perf_counter() * 1000) % 1_000_000,
                )
            except Exception:
                raise HTTPException(status_code=503, detail="serviço indisponível")
```

(adicione `import time` no topo se ainda não estiver).

- [ ] **Step 2: Smoke do fallback**

```bash
docker stop rag-query-worker
make smoke   # deve devolver "[degraded mode]" + citações
docker start rag-query-worker
```

Expected: resposta `[degraded mode]` em poucos segundos.

---

## Task 3: `/metrics` em workers (Prometheus scrape)

**Files:**
- Create: `src/shared/workers_metrics_server.py`
- Modify: `src/workers/ingest/main.py`, `src/workers/query/main.py`

- [ ] **Step 1: Implementar servidor HTTP simples para `/metrics`**

```python
# src/shared/workers_metrics_server.py
import asyncio
from aiohttp import web
from src.shared.metrics import metrics_response


async def _metrics(request):
    body, ct = metrics_response()
    return web.Response(body=body, content_type=ct)


async def _health(request):
    return web.json_response({"status": "ok"})


async def start_metrics_server(port: int = 9100) -> asyncio.Task:
    app = web.Application()
    app.router.add_get("/metrics", _metrics)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    async def _wait_forever():
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    return asyncio.create_task(_wait_forever())
```

- [ ] **Step 2: Adicionar dependência**

Em `pyproject.toml`, adicione `"aiohttp>=3.10"`.

- [ ] **Step 3: Chamar no início do `main()` dos workers**

Em `src/workers/ingest/main.py` e `src/workers/query/main.py`, no início de `async def main()`:

```python
from src.shared.workers_metrics_server import start_metrics_server
metrics_port = int(os.getenv("METRICS_PORT", "9100"))
asyncio.create_task(start_metrics_server(metrics_port))
```

- [ ] **Step 4: Expor portas no compose**

Para cada worker, exponha porta `9100`:

```yaml
  ingest-worker-doc:
    ...
    ports:
      - "9100:9100"
  ingest-worker-chunk:
    ...
    ports:
      - "9101:9100"
  query-worker:
    ...
    ports:
      - "9102:9100"
```

- [ ] **Step 5: Validar**

Run: `curl http://localhost:9100/metrics | head`
Expected: métricas `rag_*`.

---

## Task 4: Stack de observabilidade (Prometheus + Grafana + Loki + Promtail)

**Files:**
- Create: `infra/prometheus/prometheus.yml`
- Create: `infra/loki/loki-config.yml`
- Create: `infra/promtail/promtail-config.yml`
- Create: `infra/grafana/datasources/datasources.yml`
- Create: `infra/grafana/dashboards/rag-distribuido.json`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Criar `infra/prometheus/prometheus.yml`**

```yaml
global:
  scrape_interval: 5s
  evaluation_interval: 15s

scrape_configs:
  - job_name: gateway
    static_configs:
      - targets: ["gateway:8000"]

  - job_name: rerank-service
    static_configs:
      - targets: ["rerank-service:8081"]

  - job_name: workers
    static_configs:
      - targets:
          - "ingest-worker-doc:9100"
          - "ingest-worker-chunk:9100"
          - "query-worker:9100"

  - job_name: rabbitmq
    static_configs:
      - targets: ["rabbitmq:15692"]
```

> Nota: para o RabbitMQ exporter de métricas Prometheus, habilite o plugin `rabbitmq_prometheus` (incluso na imagem `rabbitmq:3-management`, exposto na porta 15692).

- [ ] **Step 2: Criar `infra/loki/loki-config.yml`** (config minimal de Loki)

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

common:
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory
  replication_factor: 1
  path_prefix: /loki

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

storage_config:
  tsdb_shipper:
    active_index_directory: /loki/index
    cache_location: /loki/cache
  filesystem:
    directory: /loki/chunks

limits_config:
  retention_period: 168h
```

- [ ] **Step 3: Criar `infra/promtail/promtail-config.yml`**

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: docker-logs
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        target_label: container
      - source_labels: ['__meta_docker_container_label_com_docker_compose_service']
        target_label: service
    pipeline_stages:
      - json:
          expressions:
            level: level
            event: event
            correlation_id: correlation_id
            service: service
      - labels:
          level:
          service:
          correlation_id:
```

- [ ] **Step 4: Criar `infra/grafana/datasources/datasources.yml`**

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
```

- [ ] **Step 5: Adicionar serviços ao `docker-compose.yml`**

```yaml
  prometheus:
    image: prom/prometheus:latest
    container_name: rag-prometheus
    profiles: ["all", "server"]
    ports:
      - "9090:9090"
    volumes:
      - ./infra/prometheus:/etc/prometheus
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.retention.time=7d"

  grafana:
    image: grafana/grafana:latest
    container_name: rag-grafana
    profiles: ["all", "server"]
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_USERS_ALLOW_SIGN_UP: "false"
    volumes:
      - ./infra/grafana/datasources:/etc/grafana/provisioning/datasources
      - ./infra/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - grafana_data:/var/lib/grafana

  loki:
    image: grafana/loki:3.2.0
    container_name: rag-loki
    profiles: ["all", "server"]
    ports:
      - "3100:3100"
    volumes:
      - ./infra/loki:/etc/loki
      - loki_data:/loki
    command: -config.file=/etc/loki/loki-config.yml

  promtail:
    image: grafana/promtail:3.2.0
    container_name: rag-promtail
    profiles: ["all", "server", "worker"]
    volumes:
      - ./infra/promtail:/etc/promtail
      - /var/run/docker.sock:/var/run/docker.sock
    command: -config.file=/etc/promtail/promtail-config.yml
```

E em `volumes:` no fim do compose, adicione `grafana_data:` e `loki_data:`.

- [ ] **Step 6: Dashboard "RAG Distribuído"**

Criar `infra/grafana/dashboards/rag-distribuido.json` com 4 painéis (queries PromQL/LogQL).

```json
{
  "title": "RAG Distribuído",
  "uid": "rag-distribuido",
  "panels": [
    {
      "title": "Throughput",
      "type": "timeseries",
      "targets": [
        {"expr": "rate(rag_throughput_queries_total[1m])", "legendFormat": "queries/s {{worker_id}}", "refId": "A"},
        {"expr": "rate(rag_throughput_docs_total[1m])", "legendFormat": "docs/s {{worker_id}}", "refId": "B"}
      ],
      "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8}
    },
    {
      "title": "Latência por fase (p95)",
      "type": "timeseries",
      "targets": [
        {"expr": "histogram_quantile(0.95, sum(rate(rag_query_pipeline_duration_seconds_bucket[5m])) by (phase, le))",
         "legendFormat": "{{phase}}", "refId": "A"}
      ],
      "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8}
    },
    {
      "title": "Tokens",
      "type": "timeseries",
      "targets": [
        {"expr": "rate(rag_tokens_total[1m])", "legendFormat": "{{direction}} {{model}}", "refId": "A"}
      ],
      "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8}
    },
    {
      "title": "Saúde",
      "type": "timeseries",
      "targets": [
        {"expr": "rag_ollama_inflight_requests", "legendFormat": "ollama in-flight", "refId": "A"},
        {"expr": "sum(rate(rag_errors_total[1m])) by (service)", "legendFormat": "errors/s {{service}}", "refId": "B"},
        {"expr": "sum(rate(rag_cache_hits_total[1m])) by (cache_layer) / (sum(rate(rag_cache_hits_total[1m])) by (cache_layer) + sum(rate(rag_cache_misses_total[1m])) by (cache_layer))",
         "legendFormat": "hit ratio {{cache_layer}}", "refId": "C"}
      ],
      "gridPos": {"x": 12, "y": 8, "w": 12, "h": 8}
    }
  ],
  "schemaVersion": 39,
  "version": 1,
  "refresh": "10s"
}
```

> Nota: a estrutura JSON de dashboard pode variar entre versões de Grafana. Após subir o stack, abra Grafana (http://localhost:3000, admin/admin), importe esse JSON e ajuste se necessário. Salve a versão final no mesmo arquivo.

- [ ] **Step 7: Habilitar plugin Prometheus no RabbitMQ**

No `docker-compose.yml`, na entry `rabbitmq`, adicione:

```yaml
    environment:
      RABBITMQ_PLUGINS: "rabbitmq_management rabbitmq_prometheus"
    ports:
      - "5672:5672"
      - "15672:15672"
      - "15692:15692"
```

(O plugin já vem incluso na imagem `rabbitmq:3-management`, só não está habilitado por default.)

- [ ] **Step 8: Validar**

Run: `make down && make dev`
Run: abra `http://localhost:3000` (admin/admin), navegue até Dashboards → "RAG Distribuído". Painéis devem ter dados depois de rodar `make smoke` 2-3 vezes.

---

## Task 5: Terraform (provider docker)

**Files:**
- Create: `infra/terraform/main.tf`, `variables.tf`, `outputs.tf`
- Create: `infra/terraform/modules/server/main.tf`
- Create: `infra/terraform/modules/worker/main.tf`
- Create: `infra/terraform/envs/{pc1,pc2,pc3}.tfvars`

> Decisão de escopo: o Terraform aqui é didático e cumpre a letra do PDF. Em paralelo, mantemos o `docker-compose.yml` como fonte alternativa de subir o stack (e que o smoke usa para Modo 1). Não estamos forçando os dois caminhos a convergirem 100%.

- [ ] **Step 1: `infra/terraform/variables.tf`**

```hcl
variable "host_role" {
  type        = string
  description = "Papel do host: server ou worker"
  validation {
    condition     = contains(["server", "worker"], var.host_role)
    error_message = "host_role deve ser 'server' ou 'worker'."
  }
}

variable "tailscale_pc1" {
  type        = string
  description = "Tailscale IP do PC1 (servidor)"
  default     = ""
}

variable "rabbit_url" {
  type    = string
  default = ""
}

variable "ollama_url" {
  type    = string
  default = ""
}

variable "qdrant_url" {
  type    = string
  default = ""
}

variable "redis_url" {
  type    = string
  default = ""
}

variable "rerank_url" {
  type    = string
  default = ""
}

variable "image_tag" {
  type    = string
  default = "latest"
}
```

- [ ] **Step 2: `infra/terraform/main.tf`**

```hcl
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {
  host = "unix:///var/run/docker.sock"
}

resource "docker_network" "rag_net" {
  name   = "rag_net"
  driver = "bridge"
}

module "server" {
  count  = var.host_role == "server" ? 1 : 0
  source = "./modules/server"

  network_name = docker_network.rag_net.name
  image_tag    = var.image_tag
}

module "worker" {
  count  = var.host_role == "worker" ? 1 : 0
  source = "./modules/worker"

  network_name = docker_network.rag_net.name
  rabbit_url   = var.rabbit_url
  ollama_url   = var.ollama_url
  qdrant_url   = var.qdrant_url
  redis_url    = var.redis_url
  rerank_url   = var.rerank_url
  image_tag    = var.image_tag
}
```

- [ ] **Step 3: `infra/terraform/modules/server/main.tf`** (skeleton)

```hcl
variable "network_name" { type = string }
variable "image_tag"    { type = string }

# RabbitMQ
resource "docker_image" "rabbitmq" {
  name = "rabbitmq:3-management"
}

resource "docker_container" "rabbitmq" {
  name  = "rag-rabbitmq"
  image = docker_image.rabbitmq.image_id
  env   = ["RABBITMQ_PLUGINS=rabbitmq_management rabbitmq_prometheus"]
  networks_advanced { name = var.network_name }
  ports {
    internal = 5672
    external = 5672
  }
  ports {
    internal = 15672
    external = 15672
  }
  ports {
    internal = 15692
    external = 15692
  }
  restart = "unless-stopped"
}

# Qdrant, Redis, Ollama, gateway, rerank-service, prometheus, grafana, loki, promtail
# seguem o mesmo padrão. Para concisão, este plano detalha apenas RabbitMQ;
# a equipe replica o padrão para os demais a partir do docker-compose.yml já existente.
# O conteúdo expandido vai diretamente no arquivo durante a Task 5.
```

- [ ] **Step 4: `infra/terraform/modules/worker/main.tf`**

```hcl
variable "network_name" { type = string }
variable "rabbit_url"   { type = string }
variable "ollama_url"   { type = string }
variable "qdrant_url"   { type = string }
variable "redis_url"    { type = string }
variable "rerank_url"   { type = string }
variable "image_tag"    { type = string }

resource "docker_image" "worker" {
  name         = "rag-worker:${var.image_tag}"
  keep_locally = true
  build {
    context    = "${path.root}/../.."
    dockerfile = "infra/docker/worker.Dockerfile"
  }
}

locals {
  worker_envs = [
    "RABBITMQ_URL=${var.rabbit_url}",
    "OLLAMA_URL=${var.ollama_url}",
    "QDRANT_URL=${var.qdrant_url}",
    "REDIS_URL=${var.redis_url}",
    "RERANK_URL=${var.rerank_url}",
    "PYTHONPATH=/app",
  ]
}

resource "docker_container" "ingest_worker_doc" {
  name  = "rag-ingest-worker-doc"
  image = docker_image.worker.image_id
  env   = concat(local.worker_envs, [
    "WORKER_KIND=ingest",
    "INGEST_ROLE=documents",
    "SERVICE_NAME=ingest-worker-doc",
    "METRICS_PORT=9100",
  ])
  networks_advanced { name = var.network_name }
  ports {
    internal = 9100
    external = 9100
  }
  restart = "unless-stopped"
}

resource "docker_container" "ingest_worker_chunk" {
  name  = "rag-ingest-worker-chunk"
  image = docker_image.worker.image_id
  env   = concat(local.worker_envs, [
    "WORKER_KIND=ingest",
    "INGEST_ROLE=chunks",
    "SERVICE_NAME=ingest-worker-chunk",
    "METRICS_PORT=9100",
  ])
  networks_advanced { name = var.network_name }
  ports {
    internal = 9100
    external = 9101
  }
  restart = "unless-stopped"
}

resource "docker_container" "query_worker" {
  name  = "rag-query-worker"
  image = docker_image.worker.image_id
  env   = concat(local.worker_envs, [
    "WORKER_KIND=query",
    "SERVICE_NAME=query-worker",
    "METRICS_PORT=9100",
  ])
  networks_advanced { name = var.network_name }
  ports {
    internal = 9100
    external = 9102
  }
  restart = "unless-stopped"
}
```

- [ ] **Step 5: `tfvars` por host**

`infra/terraform/envs/pc1.tfvars`:
```hcl
host_role = "server"
image_tag = "0.1.0-b3"
```

`infra/terraform/envs/pc2.tfvars` e `pc3.tfvars`:
```hcl
host_role     = "worker"
tailscale_pc1 = "100.x.y.z"
rabbit_url    = "amqp://guest:guest@100.x.y.z:5672/"
ollama_url    = "http://100.x.y.z:11434"
qdrant_url    = "http://100.x.y.z:6333"
redis_url     = "redis://100.x.y.z:6379/0"
rerank_url    = "http://100.x.y.z:8081"
image_tag     = "0.1.0-b3"
```

- [ ] **Step 6: Validar**

No PC1:
```bash
cd infra/terraform
terraform init
terraform plan -var-file=envs/pc1.tfvars
terraform apply -var-file=envs/pc1.tfvars -auto-approve
```

Expected: containers do server criados (mesma stack que o compose).

> **Importante:** Terraform e Docker Compose **gerenciando o mesmo daemon** vão competir. Use Terraform OU Compose por host, nunca os dois ao mesmo tempo. Deploy em produção (Modo 2) usa Terraform; dev local (Modo 1) usa Compose.

---

## Task 6: Ansible (bootstrap + deploy)

**Files:**
- Create: `infra/ansible/inventory.yml`, `ansible.cfg`
- Create: `infra/ansible/playbook-bootstrap.yml`, `playbook-deploy.yml`
- Create: `infra/ansible/roles/{docker,tailscale,nvidia}/tasks/main.yml`

- [ ] **Step 1: `infra/ansible/inventory.yml`**

```yaml
all:
  vars:
    ansible_user: rag
    ansible_python_interpreter: /usr/bin/python3
  hosts:
    pc1:
      ansible_host: 100.x.y.z
      host_role: server
      gpu_enabled: true
    pc2:
      ansible_host: 100.x.y.w
      host_role: worker
      gpu_enabled: false
    pc3:
      ansible_host: 100.x.y.q
      host_role: worker
      gpu_enabled: false
```

> Substituir os IPs Tailscale reais após autenticar `tailscale up` em cada máquina.

- [ ] **Step 2: `infra/ansible/ansible.cfg`**

```ini
[defaults]
inventory = ./inventory.yml
host_key_checking = False
retry_files_enabled = False
stdout_callback = yaml
```

- [ ] **Step 3: `playbook-bootstrap.yml`**

```yaml
---
- name: Bootstrap dos hosts
  hosts: all
  become: true
  roles:
    - docker
    - tailscale
  tasks:
    - name: Garante usuário rag no grupo docker
      user:
        name: rag
        groups: docker
        append: true

- name: NVIDIA toolkit no PC1
  hosts: pc1
  become: true
  roles:
    - nvidia
```

- [ ] **Step 4: `roles/docker/tasks/main.yml`**

```yaml
---
- name: Atualiza apt
  apt:
    update_cache: yes
    cache_valid_time: 3600

- name: Instala dependências
  apt:
    name:
      - apt-transport-https
      - ca-certificates
      - curl
      - software-properties-common
      - gnupg
      - lsb-release
    state: present

- name: Adiciona chave GPG do Docker
  apt_key:
    url: https://download.docker.com/linux/ubuntu/gpg
    state: present

- name: Adiciona repositório Docker
  apt_repository:
    repo: "deb https://download.docker.com/linux/ubuntu {{ ansible_distribution_release }} stable"
    state: present
    filename: docker

- name: Instala Docker e Compose plugin
  apt:
    name:
      - docker-ce
      - docker-ce-cli
      - containerd.io
      - docker-compose-plugin
    state: present
    update_cache: yes

- name: Garante daemon Docker rodando
  service:
    name: docker
    state: started
    enabled: yes
```

- [ ] **Step 5: `roles/tailscale/tasks/main.yml`**

```yaml
---
- name: Adiciona repo Tailscale
  shell: |
    curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/{{ ansible_distribution_release }}.noarmor.gpg | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
    curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/{{ ansible_distribution_release }}.tailscale-keyring.list | tee /etc/apt/sources.list.d/tailscale.list >/dev/null
  args:
    creates: /etc/apt/sources.list.d/tailscale.list

- name: Instala Tailscale
  apt:
    name: tailscale
    state: present
    update_cache: yes

- name: Habilita serviço
  service:
    name: tailscaled
    state: started
    enabled: yes

- name: Imprime aviso para autenticação manual
  debug:
    msg: "Após este playbook, rode 'sudo tailscale up' em cada host e copie o IP retornado para inventory.yml"
```

- [ ] **Step 6: `roles/nvidia/tasks/main.yml`** (só PC1)

```yaml
---
- name: Adiciona repo NVIDIA Container Toolkit
  shell: |
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
      sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
      tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  args:
    creates: /etc/apt/sources.list.d/nvidia-container-toolkit.list

- name: Instala toolkit
  apt:
    name: nvidia-container-toolkit
    state: present
    update_cache: yes

- name: Configura runtime
  command: nvidia-ctk runtime configure --runtime=docker

- name: Reinicia Docker
  service:
    name: docker
    state: restarted
```

- [ ] **Step 7: `playbook-deploy.yml`**

```yaml
---
- name: Deploy do RAG
  hosts: all
  become: false
  tasks:
    - name: Sincroniza repo no host
      ansible.posix.synchronize:
        src: "{{ playbook_dir }}/../.."
        dest: "/home/rag/projeto_harness_engineering"
        rsync_opts:
          - "--exclude=.git"
          - "--exclude=.venv"
          - "--exclude=data"

    - name: Renderiza .env (a partir de template)
      template:
        src: env.j2
        dest: "/home/rag/projeto_harness_engineering/.env"

    - name: Terraform init
      command:
        cmd: terraform init -input=false
        chdir: /home/rag/projeto_harness_engineering/infra/terraform

    - name: Terraform apply
      command:
        cmd: "terraform apply -input=false -auto-approve -var-file=envs/{{ inventory_hostname }}.tfvars"
        chdir: /home/rag/projeto_harness_engineering/infra/terraform

    - name: Healthcheck pós-deploy (apenas no server)
      uri:
        url: "http://localhost:8000/health"
        status_code: 200
      retries: 30
      delay: 5
      when: host_role == "server"
```

- [ ] **Step 8: Template `infra/ansible/env.j2`**

```jinja
RABBITMQ_URL=amqp://guest:guest@{{ hostvars['pc1'].ansible_host }}:5672/
OLLAMA_URL=http://{{ hostvars['pc1'].ansible_host }}:11434
QDRANT_URL=http://{{ hostvars['pc1'].ansible_host }}:6333
REDIS_URL=redis://{{ hostvars['pc1'].ansible_host }}:6379/0
RERANK_URL=http://{{ hostvars['pc1'].ansible_host }}:8081
LOG_LEVEL=INFO
SERVICE_NAME={{ inventory_hostname }}-{{ host_role }}
```

- [ ] **Step 9: `scripts/deploy.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../infra/ansible"

ansible-playbook playbook-bootstrap.yml "$@"
ansible-playbook playbook-deploy.yml "$@"

echo "[deploy] OK. Smoke: curl http://$(grep -A1 pc1: inventory.yml | tail -1 | awk '{print $2}'):8000/health"
```

`chmod +x scripts/deploy.sh`.

> **Pré-requisito manual antes do primeiro deploy:** ter `tailscale up` rodado em cada PC, com IPs preenchidos no `inventory.yml`, e SSH key do PC1 (autor) copiada para `~/.ssh/authorized_keys` dos outros PCs.

---

## Task 7: Corpus seed (`scripts/seed_corpus.py`)

**Files:**
- Create: `scripts/seed_corpus.py`

- [ ] **Step 1: Implementar**

```python
"""
Ingere todos os PDFs/MDs de samples/corpus/ no sistema.

Uso:
  uv run python scripts/seed_corpus.py [--gateway http://localhost:8000] [--corpus samples/corpus]
"""
import argparse
import base64
import sys
import time
from pathlib import Path

import httpx


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gateway", default="http://localhost:8000")
    p.add_argument("--corpus", default="samples/corpus")
    args = p.parse_args()

    corpus = Path(args.corpus)
    if not corpus.exists():
        print(f"Corpus dir não existe: {corpus}", file=sys.stderr)
        return 2

    files = list(corpus.glob("**/*.pdf")) + list(corpus.glob("**/*.md"))
    print(f"[seed] {len(files)} arquivos para indexar")

    submitted = 0
    failures = []
    for f in files:
        try:
            content = base64.b64encode(f.read_bytes()).decode()
            r = httpx.post(
                f"{args.gateway}/ingest",
                json={
                    "filename": f.name,
                    "content_b64": content,
                    "source_type": "pdf" if f.suffix.lower() == ".pdf" else "md",
                },
                timeout=20,
            )
            r.raise_for_status()
            submitted += 1
            if submitted % 10 == 0:
                print(f"[seed] {submitted}/{len(files)}")
        except Exception as exc:
            failures.append((f.name, str(exc)))

    print(f"[seed] enviados={submitted} falhas={len(failures)}")
    if failures:
        for name, err in failures[:5]:
            print(f"  - {name}: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Curar corpus**

Crie `samples/corpus/` e copie ~80 PDFs/MDs sobre engenharia de software. Sugestões de fontes:
- arXiv cs.SE (papers de domínio público).
- "Software Architecture Patterns" (capítulos disponíveis publicamente).
- Documentação técnica em Markdown (FastAPI docs, Twelve-Factor App, microservices.io).

> Estratégia rápida: `git clone` de repositórios docs-only com licença permissiva e copie os `.md` para `samples/corpus/`.

- [ ] **Step 3: Executar**

Run: `uv run python scripts/seed_corpus.py`
Expected: `submitted=N falhas=0` (ou poucas falhas justificáveis). Aguarde ~10–30 min para indexação completar (depende da GPU). Verifique no Qdrant dashboard que `points_count` cresceu.

---

## Task 8: Chaos test e DLQ inspector

**Files:**
- Create: `scripts/chaos_test.sh`
- Create: `scripts/dlq_inspector.py`

- [ ] **Step 1: `scripts/chaos_test.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "[chaos] kill ingest-worker-chunk no meio da indexação"
docker stop rag-ingest-worker-chunk
sleep 2
docker start rag-ingest-worker-chunk
echo "[chaos] worker reiniciado, mensagens devem ser reprocessadas"

echo "[chaos] kill Ollama por 30s"
docker stop rag-ollama
sleep 30
docker start rag-ollama
echo "[chaos] Ollama de volta. Próxima query deve voltar a funcionar (com retry)."

echo "[chaos] sobrecarga: 20 queries em rajada"
for i in $(seq 1 20); do
  curl -s -X POST http://localhost:8000/query \
    -H "Content-Type: application/json" \
    -d '{"question":"O que é arquitetura hexagonal?","top_k":3}' &
done
wait
echo "[chaos] rajada concluída. Confira fila depth no Grafana."
```

`chmod +x scripts/chaos_test.sh`.

- [ ] **Step 2: `scripts/dlq_inspector.py`**

```python
"""
Inspeciona e re-publica mensagens em DLQ.

Uso:
  uv run python scripts/dlq_inspector.py list ingest.documents.dlq
  uv run python scripts/dlq_inspector.py replay ingest.documents.dlq --limit 5
  uv run python scripts/dlq_inspector.py purge ingest.documents.dlq --yes
"""
import argparse
import asyncio
import json
import sys

import aio_pika

from src.shared.config import settings


async def list_dlq(queue_name: str, limit: int = 20):
    conn = await aio_pika.connect_robust(settings.rabbitmq_url)
    try:
        ch = await conn.channel()
        q = await ch.declare_queue(queue_name, durable=True, passive=True)
        print(f"[{queue_name}] message_count={q.declaration_result.message_count}")

        for i in range(min(limit, q.declaration_result.message_count)):
            msg = await q.get(no_ack=False)
            if msg is None:
                break
            payload = json.loads(msg.body)
            print(f"--- msg {i+1} ---")
            print(json.dumps(payload, indent=2)[:500])
            await msg.nack(requeue=True)  # devolve à DLQ
    finally:
        await conn.close()


async def replay(queue_name: str, limit: int):
    target = queue_name.replace(".dlq", "")
    conn = await aio_pika.connect_robust(settings.rabbitmq_url)
    try:
        ch = await conn.channel()
        q = await ch.declare_queue(queue_name, durable=True, passive=True)
        moved = 0
        for _ in range(limit):
            msg = await q.get(no_ack=False)
            if msg is None:
                break
            await ch.default_exchange.publish(
                aio_pika.Message(body=msg.body, headers={}),
                routing_key=target,
            )
            await msg.ack()
            moved += 1
        print(f"[replay] {moved} mensagens movidas {queue_name} → {target}")
    finally:
        await conn.close()


async def purge(queue_name: str):
    conn = await aio_pika.connect_robust(settings.rabbitmq_url)
    try:
        ch = await conn.channel()
        q = await ch.declare_queue(queue_name, durable=True, passive=True)
        n = q.declaration_result.message_count
        await q.purge()
        print(f"[purge] {n} mensagens removidas de {queue_name}")
    finally:
        await conn.close()


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list"); p_list.add_argument("queue"); p_list.add_argument("--limit", type=int, default=20)
    p_replay = sub.add_parser("replay"); p_replay.add_argument("queue"); p_replay.add_argument("--limit", type=int, default=10)
    p_purge = sub.add_parser("purge"); p_purge.add_argument("queue"); p_purge.add_argument("--yes", action="store_true")
    args = p.parse_args()

    if args.cmd == "list":
        asyncio.run(list_dlq(args.queue, args.limit))
    elif args.cmd == "replay":
        asyncio.run(replay(args.queue, args.limit))
    elif args.cmd == "purge":
        if not args.yes:
            print("Use --yes para confirmar."); sys.exit(2)
        asyncio.run(purge(args.queue))


if __name__ == "__main__":
    main()
```

---

## Task 9: Marco luz-verde do B3

- [ ] **Step 1: Critérios de aceite**

- ✅ Modo 2 distribuído sobe via `make deploy` (Ansible) com 3 PCs reais.
- ✅ `curl http://<pc1-tailscale>:8000/health` retorna 200 a partir de outra rede.
- ✅ `make smoke` passa apontando para o PC1 via Tailscale.
- ✅ `bash scripts/chaos_test.sh` passa: workers retomam, Ollama reinicia, fila drena.
- ✅ Mensagens com erro persistente aparecem na DLQ (verificar via `dlq_inspector list`).
- ✅ Grafana mostra os 4 painéis populados após 5 min de atividade.
- ✅ Loki tem logs do gateway com label `correlation_id` indexada.
- ✅ Corpus de ≥80 docs indexado (verificar `points_count` no Qdrant).

- [ ] **Step 2: Capturar evidências**

- Print do Grafana com os 4 painéis.
- Print do RabbitMQ Management mostrando filas + DLQs com tráfego.
- Print do Loki com 1 query reconstituída por `correlation_id`.
- Output do chaos test em `data/b3-chaos.txt`.
- `qdrant info` da collection `se_corpus`.

Quando todos passarem: **B3 concluído**.

---

## Notas de execução paralela (B3)

- **Trilha A:** Tasks 1 (DLX/DLQ), 2 (degraded mode), 4 (observabilidade — Grafana, Prometheus, Loki, Promtail).
- **Trilha B:** Tasks 3 (workers /metrics), 7 (seed_corpus), 8 (chaos + dlq_inspector).
- **Trilha C:** Tasks 5 (Terraform), 6 (Ansible), validação Tailscale + setup físico dos PCs.

Pareamento crítico nas Tasks 5+6 e na primeira validação distribuída end-to-end (provavelmente o ponto mais propenso a engasgo).
