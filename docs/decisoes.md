# Decisões Arquiteturais

Registro curto das decisões que moldam o projeto RAG distribuído.

## ADR-001: Stack local em vez de cloud

**Decisão:** usar RabbitMQ, Qdrant, Redis, Ollama, Prometheus, Grafana e Loki em
containers locais.

**Motivo:** custo zero, compatibilidade com a disciplina e demonstração real em
três PCs físicos via Tailscale.

**Consequência:** a equipe assume operação local, configuração de rede privada e
limitações de hardware; em troca, mantém controle completo da topologia.

## ADR-002: Mensageria como fronteira entre gateway e workers

**Decisão:** o gateway publica documentos e queries no RabbitMQ; workers
consomem filas e respondem por RPC sobre AMQP quando necessário.

**Motivo:** desacoplar HTTP de processamento pesado e permitir paralelismo por
replicação de consumidores.

**Consequência:** o sistema precisa lidar com correlação, reply queues, DLQ e
timeouts, mas ganha elasticidade operacional.

## ADR-003: Ingestão em duas filas

**Decisão:** separar `ingest.documents` de `ingest.chunks`.

**Motivo:** parse/chunking e embed/upsert têm custos diferentes. Duas filas
permitem escalar chunk-workers sem replicar parse desnecessariamente.

**Consequência:** mais moving parts, porém melhor controle de paralelismo de
dados.

## ADR-004: Retrieval em dois estágios

**Decisão:** buscar top-20 no Qdrant por embedding e re-ranquear top-k via
cross-encoder.

**Motivo:** bi-encoder é barato e amplo; cross-encoder é mais preciso, mas caro.

**Consequência:** melhora relevância dos blocos, com latência adicional visível
na métrica `rag_query_pipeline_duration_seconds{phase="rerank"}`.

## ADR-005: Function calling com fallback estrutural

**Decisão:** tentar `cite_source` via tool calling e montar citações estruturais
a partir dos chunks injetados quando o modelo não chama a ferramenta.

**Motivo:** o requisito de engenharia de contexto pede citações estruturadas,
mas o `qwen2.5:7b-instruct` não adere de forma consistente sob contexto RAG
denso.

**Consequência:** o sistema preserva citações corretas mesmo quando a tool fica
dormente.

## ADR-006: Observabilidade com Prometheus, Grafana e Loki

**Decisão:** expor `/metrics` em gateway, rerank-service e workers; coletar logs
JSON via Promtail/Loki; provisionar dashboard Grafana.

**Motivo:** demonstrar throughput, latência por fase, tokens, erros, cache hit
ratio e correlação por logs.

**Consequência:** o Compose ganha serviços adicionais, mas a demo fica
inspecionável e defensável.

## ADR-007: IaC dividido entre Ansible e Terraform

**Decisão:** usar Ansible para bootstrap/deploy e Terraform para estado dos
containers.

**Motivo:** Ansible configura hosts; Terraform descreve recursos Docker.

**Consequência:** há duas ferramentas, mas com fronteiras claras e documentadas.
