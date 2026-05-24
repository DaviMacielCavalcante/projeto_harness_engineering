# Guia de observabilidade

> Como acessar as métricas, logs e dashboards do sistema. Cobre as 11 métricas Prometheus do `src/shared/metrics.py`, o dashboard Grafana provisionado, e queries PromQL/LogQL prontas pra cada cenário comum.

## 1. Visão geral

Três camadas, ortogonais entre si:

| Camada | O que mede | Stack | Pergunta que responde |
|---|---|---|---|
| **Métricas** | Séries temporais agregadas (contadores, gauges, histogramas) | Prometheus + endpoints `/metrics` em cada serviço | "Como esse fenômeno está se distribuindo no tempo?" |
| **Logs** | Eventos individuais com `correlation_id`, em JSON | Promtail → Loki | "O que aconteceu nesta ocorrência específica?" |
| **Dashboards** | Painéis que combinam as duas | Grafana com datasources `prometheus` e `loki` provisionados | "Qual a saúde do sistema agora?" |

A separação importa: **erro pontual** vai no log (`{correlation_id="q-7af3..."}`), **tendência de erros** vai na métrica (`rate(rag_errors_total[5m])`). Os dois custam quase nada — uma chamada cada — e cobrem perguntas complementares.

## 2. Endpoints

Todos no host onde o Compose subir (`localhost` em Modo 1; `pc1-davi` em Modo 2):

| URL | Para que serve |
|---|---|
| `http://localhost:9090` | Prometheus UI — query browser, `/targets`, `/alerts` |
| `http://localhost:9090/targets` | Confirma quem está sendo scrapado e quem está `UP`/`DOWN` |
| `http://localhost:3000` (admin/admin) | Grafana — dashboards e Explore |
| `http://localhost:3000/d/rag-distribuido` | Dashboard provisionado "RAG Distribuído" |
| `http://localhost:3000/explore` | Explore (Loki ou Prometheus por escolha de datasource) |
| `http://localhost:3100/ready` | Loki health |
| `http://localhost:9080/ready` | Promtail health (se exposto; default não é) |
| `http://localhost:8000/metrics` | `/metrics` do gateway FastAPI |
| `http://localhost:8081/metrics` | `/metrics` do rerank-service |
| `http://localhost:15692/metrics` | `/metrics` do plugin `rabbitmq_prometheus` |
| `http://localhost:15672` (guest/guest) | RabbitMQ Management UI — filas, mensagens, conexões |
| `http://localhost:6333/dashboard` | Qdrant dashboard — collection `se_corpus`, pontos, payloads |
| Workers `:9100/metrics` | **Não respondem** até a Task 3 do B3 entregar `workers_metrics_server.py` (Pablo) |

## 3. Subir e validar

```bash
# Modo 1 (single-host)
make down -v   # -v pra apagar volumes velhos (ex: rabbitmq_data sem o plugin Prometheus)
make dev
sleep 30       # lifespans + healthchecks

# Validação rápida (sem jq)
curl -s http://localhost:9090/api/v1/targets | python -m json.tool | grep -E '"job"|"health"|"lastError"'

# Validar cada peça
curl -s http://localhost:15692/metrics | head -5     # plugin RabbitMQ
curl -s http://localhost:3100/ready                   # Loki
curl -s http://localhost:3000/api/health              # Grafana
curl -s http://localhost:8000/metrics | grep rag_     # gateway

# Gerar tráfego para popular os painéis
uv run python scripts/smoke_test.py
```

O dashboard "RAG Distribuído" aparece em **http://localhost:3000** (admin/admin) → Dashboards. Provisionamento é automático via `infra/grafana/dashboards/dashboards.yml`; o JSON é re-importado a cada 10s, então editar o arquivo no host atualiza o painel em tempo real.

## 4. Catálogo das 11 métricas

Todas registradas em `src/shared/metrics.py` no `CollectorRegistry` único (variável `REGISTRY`). Cada componente importa as métricas deste módulo e expõe via `metrics_response()` no seu `/metrics`.

| Métrica | Tipo | Labels | Quem incrementa | `/metrics` que expõe |
|---|---|---|---|---|
| `rag_request_duration_seconds` | Histogram | `endpoint`, `status` | Middleware `measure_requests` do gateway | gateway `:8000` |
| `rag_errors_total` | Counter | `service`, `error_type` | Gateway (degraded mode: `error_type=query_timeout`) + workers | gateway `:8000` + workers `:9100` |
| `rag_query_pipeline_duration_seconds` | Histogram | `phase`, `worker_id` | `query-worker` em cada fase 1–6 (`with histogram.time():`) | workers `:9100` |
| `rag_ingest_pipeline_duration_seconds` | Histogram | `phase`, `worker_id` | `ingest-worker-{doc,chunk}` em cada fase | workers `:9100` |
| `rag_tokens_total` | Counter | `direction` (`in`/`out`), `model` | `query-worker` após `Ollama.chat`/`.embed` somando `prompt_eval_count`/`eval_count` | workers `:9100` |
| `rag_throughput_docs_total` | Counter | `worker_id` | `ingest-worker-doc` quando publica chunks na fila | workers `:9100` |
| `rag_throughput_queries_total` | Counter | `worker_id`, `status` | `query-worker` no fim do `handle_query` (fase 7) | workers `:9100` |
| `rag_cache_hits_total` | Counter | `cache_layer` (`L1`/`L2`) | `query-worker` no cache.py | workers `:9100` |
| `rag_cache_misses_total` | Counter | `cache_layer` | `query-worker` no cache.py | workers `:9100` |
| `rag_queue_depth` | Gauge | `queue_name` | (não há scraper de fila implementado — uso futuro) | — |
| `rag_ollama_inflight_requests` | Gauge | (nenhum) | Workers + gateway (degraded mode) em torno de chamadas Ollama | workers `:9100` + gateway `:8000` |

**Regras de cardinalidade.** Labels têm que ter conjunto pequeno e fechado. Aqui: `status` ∈ {`200`, `4xx`, `5xx`, `500`}; `phase` ∈ {`embed`, `retrieval`, `rerank`, `generate`, `total`}; `cache_layer` ∈ {`L1`, `L2`}; `worker_id` é o hostname/container (poucos). **Nunca** use `correlation_id`, `query` ou `doc_id` como label — isso explode a memória do Prometheus. Esses campos vão pro log estruturado (Loki), que é indexado pra cardinalidade alta.

**Hierarquia da exposição.** Cada componente expõe **suas próprias** séries no `/metrics` dele. O gateway expõe `rag_request_duration_seconds` e `rag_errors_total{service="gateway"}`; os workers expõem todo o resto. Como o Prometheus scrapeia todos os endpoints, no servidor de queries as séries de todos os componentes coexistem.

## 5. Dashboard "RAG Distribuído" — os 5 painéis

JSON em `infra/grafana/dashboards/rag-distribuido.json`. Cada painel tem `description` com a TODO original e está documentado abaixo com a query PromQL final.

### Painel 1 — Throughput

Duas séries no mesmo gráfico:

```promql
# Queries/s por worker e status (sucesso/erro)
sum(rate(rag_throughput_queries_total[1m])) by (worker_id, status)

# Docs/s por worker (documentos particionados pelo ingest-worker-doc)
sum(rate(rag_throughput_docs_total[1m])) by (worker_id)
```

Unidade: `ops` (operações por segundo). `rate(...[1m])` dá vazão média da janela de 1 min.

### Painel 2 — Latência por fase (p95)

```promql
histogram_quantile(0.95,
  sum(rate(rag_query_pipeline_duration_seconds_bucket[5m])) by (phase, le))
```

Unidade: `s` (segundos). Cada série é uma fase do `handle_query` (embed, retrieval, rerank, generate, total). Útil pra identificar o gargalo de qualquer query em tempo real. Se quiser dissecar por worker, troque `by (phase, le)` por `by (phase, worker_id, le)`.

### Painel 3 — Tokens

```promql
sum(rate(rag_tokens_total[1m])) by (direction, model)
```

Unidade: `ops`. Cruzar com a fase `generate` do painel 2 ajuda a detectar respostas anormalmente longas (tokens/s alto + latência alta).

### Painel 4 — Saúde (Ollama in-flight + erros)

```promql
# Gauge instantâneo de requests Ollama em voo
rag_ollama_inflight_requests

# Errors/s agregado por serviço
sum(rate(rag_errors_total[1m])) by (service)
```

`rag_ollama_inflight_requests` é gauge sem rate — quer ver o **valor atual**, não a derivada. Se sobe e fica alto, Ollama está saturando.

### Painel 5 — Cache hit ratio

```promql
sum(rate(rag_cache_hits_total[5m])) by (cache_layer)
/ clamp_min(
    sum(rate(rag_cache_hits_total[5m])) by (cache_layer)
    + sum(rate(rag_cache_misses_total[5m])) by (cache_layer),
    0.0001)
```

Unidade: `percentunit` (proporção 0–1, renderizada como 0%–100%). O `clamp_min(..., 0.0001)` no denominador evita `NaN` quando não há tráfego — devolve 0 em vez. Painel separado porque a unidade não combina com count/s.

## 6. Queries PromQL úteis (além do dashboard)

### Latência p50 / p95 / p99 da rota HTTP do gateway
```promql
histogram_quantile(0.50, sum(rate(rag_request_duration_seconds_bucket[5m])) by (endpoint, le))
histogram_quantile(0.95, sum(rate(rag_request_duration_seconds_bucket[5m])) by (endpoint, le))
histogram_quantile(0.99, sum(rate(rag_request_duration_seconds_bucket[5m])) by (endpoint, le))
```

### Taxa de erro do gateway (todos endpoints juntos)
```promql
sum(rate(rag_request_duration_seconds_count{status=~"5.."}[5m]))
/ sum(rate(rag_request_duration_seconds_count[5m]))
```

### Tempo médio gasto em cada fase do pipeline (não é p95)
```promql
sum(rate(rag_query_pipeline_duration_seconds_sum[5m])) by (phase)
/ sum(rate(rag_query_pipeline_duration_seconds_count[5m])) by (phase)
```

### Profundidade de fila do RabbitMQ (via plugin)
```promql
# Mensagens prontas em cada fila
rabbitmq_queue_messages_ready

# Mensagens não-ack (em processamento)
rabbitmq_queue_messages_unacknowledged

# Mensagens publicadas/s
rate(rabbitmq_queue_messages_published_total[1m])
```

### Saúde geral em uma única série
```promql
# 1 se todos os 4 jobs principais estão UP, 0 caso contrário
up{job=~"gateway|rerank-service|rabbitmq|workers"}
```

## 7. Queries LogQL úteis (Loki via Grafana Explore)

Datasource: **Loki**. Acessar em http://localhost:3000/explore.

### Tudo do gateway
```logql
{service="gateway"}
```

### Reconstituir o caminho de uma query específica
```logql
{correlation_id="q-7af3a2b1"}
```
Mostra todas as linhas de todos os serviços (gateway → query-worker → Ollama) para aquela correlation_id, em ordem cronológica. **Único caminho prático pra debugar um request distribuído.**

### Só erros em todo o sistema
```logql
{level="error"}
```

### Eventos específicos do degraded mode
```logql
{service="gateway"} |= "query.degraded"
```

### Pipeline JSON para extrair campos como labels temporárias
```logql
{service=~"ingest-worker-.+"} | json | event="ingest.chunk.skipped"
```
Filtra apenas o evento de chunk pulado pela fronteira de erro do `ingest-worker-chunk`.

### Contar erros por service ao longo do tempo
```logql
sum by (service) (count_over_time({level="error"}[5m]))
```

## 8. Troubleshooting comum

### "O dashboard só mostra dados do Ollama" / painéis vazios

Esperado se os workers ainda não têm `/metrics` ativo (Task 3 do B3 do Pablo Abdon — `src/shared/workers_metrics_server.py` aiohttp standalone). Verificar:

```bash
curl -s http://localhost:9090/api/v1/targets | python -m json.tool | grep -E '"job"|"health"|"lastError"'
```

Se os 3 targets do job `workers` retornam `dial tcp :9100: connect: connection refused`, é exatamente isso. Painéis 1, 2, 3, 5 (e parte do 4) só populam após a Task 3.

### "Plugin `rabbitmq_prometheus` não habilita"

A imagem `rabbitmq:3-management` inclui o plugin, mas o `RABBITMQ_PLUGINS` no env do compose só tem efeito em volume novo. Se já tinha rodado antes sem o plugin:

```bash
make down -v   # -v apaga volumes (rabbitmq_data velho)
make dev
```

### "Promtail não está coletando logs"

Promtail descobre containers via `/var/run/docker.sock`. Conferir que o socket está montado:

```bash
docker exec rag-promtail ls -la /var/run/docker.sock
docker logs rag-promtail | tail -20
```

Se não há erro mas mesmo assim o Loki não tem dados, conferir que os containers da aplicação estão escrevendo JSON no stdout (não stderr, não arquivo). `docker logs rag-gateway | head` deve mostrar linhas com `{"event": "...", "service": "gateway", ...}`.

### "Grafana mostra `No data points` em todos os painéis"

Provavelmente nada foi cobrado ainda. Gerar tráfego:

```bash
uv run python scripts/smoke_test.py  # ingest + query → popula gateway + (com workers UP) o resto
```

Espere ~30s pro Prometheus terminar o próximo ciclo de scrape (interval 5s × algumas amostras).

### "Targets `UP` mas as séries não aparecem no `/metrics`"

Conferir que o registro Prometheus foi importado **antes** do código que incrementa. Se um worker incrementa `rag_throughput_queries_total` mas a métrica não foi importada do `src/shared/metrics.py` no main do worker, o counter existe num registro paralelo que não é serializado em `/metrics`. Síntoma: target `UP`, séries `rag_*` ausentes do output. Solução: importar `from src.shared.metrics import *` (ou o nome específico) no entrypoint do worker.

### "Cardinalidade explodiu — Prometheus consumindo muita RAM"

Procurar séries com `correlation_id`, query crua, ou `doc_id` como label:

```bash
curl -s http://localhost:9090/api/v1/label/__name__/values | python -m json.tool | grep rag_
```

Para cada métrica `rag_*`, conferir os labels permitidos. Cardinalidade total = produto cartesiano dos valores possíveis de cada label, então uma label com `correlation_id` (1 valor único por request) multiplica a série inteira por 1000–10000 por dia.

## 9. Referências internas

- Código das métricas — [`src/shared/metrics.py`](../src/shared/metrics.py)
- Logging estruturado — [`src/shared/logging.py`](../src/shared/logging.py)
- Configs Prometheus / Loki / Promtail — [`infra/prometheus/`](../infra/prometheus/), [`infra/loki/`](../infra/loki/), [`infra/promtail/`](../infra/promtail/)
- Datasources Grafana e dashboard — [`infra/grafana/`](../infra/grafana/)
- Doc técnico (§5 tolerância a falhas + §7 resultados) — [`arquitetura.md`](arquitetura.md)
