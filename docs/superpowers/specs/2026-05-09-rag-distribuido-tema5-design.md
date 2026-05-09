# Design — Tema 5: Sistema de Q&A com RAG Distribuído (ambiente local)

- **Data:** 2026-05-09
- **Disciplina:** Programação Distribuída e Paralela
- **Tema escolhido:** 5 — Sistema de Q&A sobre base de conhecimento (RAG distribuído)
- **Equipe:** trio
- **Status:** spec aprovado, pronto para plano de implementação

---

## 1. Visão geral e objetivo

Construir um pipeline RAG (Retrieval-Augmented Generation) distribuído real entre três PCs físicos conectados via Tailscale, sem custos de cloud. A indexação de documentos roda em paralelo (paralelismo de dados), o atendimento de consultas roda em paralelo (paralelismo de tarefas), e ambos compartilham um cache distribuído. O domínio do corpus é engenharia de software (arquiteturas de sistemas, paradigmas de desenvolvimento, design patterns).

O design cobre todos os requisitos mínimos da Seção 4 do enunciado, todos os entregáveis da Seção 8 e busca o bônus de +10 pontos da Seção 9 via SLM auto-hospedado e experimento Ollama vs vLLM.

## 2. Decisões consolidadas

| Item | Decisão | Justificativa |
|---|---|---|
| Tema | 5 — RAG distribuído | Escolha do usuário |
| Domínio | Engenharia de software (PT/EN) | Corpus didático e relevante para a turma |
| Hardware | PC1 (autor, com GPU) + PC2/PC3 (colegas, mais fracos) | Hardware disponível |
| Topologia | Distribuída entre 3 PCs via Tailscale/LAN | Demonstra distribuição real entre máquinas físicas |
| Escala | ~50–100 documentos | Suficiente para experimentos significativos |
| Mensageria | RabbitMQ | DLQ first-class, vocabulário próximo de SQS/SNS, padrões clássicos |
| LLM gerador | `qwen2.5:7b-instruct` via Ollama (linha-base) | Forte em PT-BR, 32K contexto, function calling |
| Embeddings | `nomic-embed-text` (768d) via Ollama | Open-source, leve, multilíngue suficiente |
| Re-ranker | `BAAI/bge-reranker-v2-m3` (cross-encoder) | Atende requisito explícito do tema |
| Vector DB | Qdrant | Performance, payload filters, dashboard built-in |
| Cache | Redis | Camadas L1 (embeddings de query) e L2 (resposta inteira) |
| Observabilidade | Prometheus + Grafana + Loki | Stack open-source idiomática |
| IaC | Terraform (provider docker) + Ansible | Cumpre formalmente "Terraform" do PDF, justifica deploy multi-host |
| Inferência avançada | vLLM em experimento comparativo no final | Ataca o bônus "paralelismo da aplicação vs do servidor de inferência" |
| Linguagem | Python 3.12, gerenciado com `uv` | Padrão da equipe e do ecossistema IA |
| Dev loop | Docker Compose com profiles: `all` (single-host) ou `server`/`worker` (distribuído) | Permite cada dev trabalhar localmente sem depender dos colegas |

## 3. Arquitetura macro

```
                        ┌──────────────────────────────────────────────────────┐
                        │  PC1 — "servidor" (com GPU)                          │
                        │                                                      │
   usuário ──HTTP──►   │  ┌──────────┐    ┌──────────┐    ┌─────────────────┐ │
   (Streamlit ou       │  │ FastAPI  │───►│ RabbitMQ │    │ Ollama (GPU)    │ │
    Postman)           │  │ gateway  │    │  broker  │    │  - qwen2.5:7b   │ │
                        │  └──────────┘    │  +mgmt   │    │  - nomic-embed  │ │
                        │       │          └──────────┘    └─────────────────┘ │
                        │       ▼                ▲ ▲                ▲          │
                        │  ┌──────────┐          │ │                │          │
                        │  │  Qdrant  │◄─────────┼─┼────────────────┘          │
                        │  │ (vector) │          │ │                           │
                        │  └──────────┘          │ │   ┌──────────────────┐    │
                        │  ┌──────────┐          │ │   │ Prometheus       │    │
                        │  │  Redis   │◄─────────┼─┼───┤  + Grafana       │    │
                        │  │ (cache)  │          │ │   │  + Loki (logs)   │    │
                        │  └──────────┘          │ │   └──────────────────┘    │
                        │  ┌─────────────────┐   │ │                           │
                        │  │ rerank-service  │◄──┘ │                           │
                        │  │ bge-reranker-m3 │     │                           │
                        │  └─────────────────┘     │                           │
                        └──────────────────────────┼───────────────────────────┘
                                                   │           Tailscale mesh
              ┌────────────────────────────────────┘
              ▼                                                        ▼
   ┌──────────────────────────────────┐              ┌──────────────────────────────────┐
   │  PC2 — "worker A"                │              │  PC3 — "worker B"                │
   │                                  │              │                                  │
   │  ┌────────────────────────────┐  │              │  ┌────────────────────────────┐  │
   │  │ ingest-worker              │  │              │  │ ingest-worker              │  │
   │  │  consume → chunk → embed   │  │              │  │                            │  │
   │  └────────────────────────────┘  │              │  └────────────────────────────┘  │
   │  ┌────────────────────────────┐  │              │  ┌────────────────────────────┐  │
   │  │ query-worker               │  │              │  │ query-worker               │  │
   │  │  retrieve → rerank → gen   │  │              │  │                            │  │
   │  └────────────────────────────┘  │              │  └────────────────────────────┘  │
   │                                  │              │                                  │
   │  prometheus-node-exporter        │              │  prometheus-node-exporter        │
   │  promtail (logs → Loki)          │              │  promtail (logs → Loki)          │
   └──────────────────────────────────┘              └──────────────────────────────────┘
```

**Princípios:**
- PC1 concentra recursos pesados (GPU, vector DB, broker, observabilidade) e expõe a API.
- PC2/PC3 rodam workers que consomem das filas e chamam Ollama via Tailscale.
- Cada PC roda dois tipos de worker (ingestão e query); pool total ≥ 4 workers.
- Paralelismo demonstrado em duas dimensões: (1) dados na ingestão; (2) tarefas no atendimento.

## 4. Componentes detalhados

| Componente | Onde | Tech | Responsabilidades |
|---|---|---|---|
| API Gateway | PC1 | FastAPI + Uvicorn | `POST /ingest`, `POST /query`, `GET /health`, `GET /metrics`. Publica em filas, espera resposta via fila temporária correlacionada por `correlation_id`. |
| RabbitMQ | PC1 | `rabbitmq:3-management` | Filas: `ingest.documents`, `ingest.chunks`, `query.requests`, `query.responses` + DLX para `*.dlq`. Management UI em `:15672`. |
| Ollama | PC1 | `ollama/ollama` (CUDA) | Serve `qwen2.5:7b-instruct` + `nomic-embed-text`. Porta `11434` exposta via Tailscale. |
| Qdrant | PC1 | `qdrant/qdrant` | Collection `se_corpus`, vetores 768d, payload `{doc_id, chunk_id, source, page, text, lang, sha}`. |
| Redis | PC1 | `redis:7-alpine` | L1 (`emb:{sha(query)}`), L2 (`resp:{sha(query+ids)}`), set `seen_doc_hashes` para deduplicação. |
| Prometheus | PC1 | `prom/prometheus` | Scrape de `/metrics` a cada 5s. |
| Grafana | PC1 | `grafana/grafana` | Dashboard "RAG Distribuído" com 4 painéis. |
| Loki + Promtail | PC1 + workers | `grafana/loki`, `grafana/promtail` | Logs JSON estruturados, indexados por `service`, `host`, `correlation_id`. |
| ingest-worker | PC1/PC2/PC3 | Python 3.12 + `aio-pika` + `httpx` | Parsing → chunking → embedding → upsert no Qdrant. |
| query-worker | PC1/PC2/PC3 | Python 3.12 + `aio-pika` + `httpx` | Embedding query → retrieval → rerank → montagem de contexto → generate → resposta. |
| rerank-service | PC1 | FastAPI + `sentence-transformers` | Cross-encoder centralizado (evita carregar 568MB em cada worker). |
| Streamlit demo | PC1 | `streamlit` | UI da apresentação ao vivo: query, resposta com citações, painel de métricas. |

**Convenções transversais:**
- Todo serviço expõe `/metrics` (formato Prometheus via `prometheus_client`).
- Logs JSON via `structlog`, campos obrigatórios: `ts`, `level`, `service`, `host`, `correlation_id`, `event`, `latency_ms`, `tokens_in`, `tokens_out`.
- Chamadas externas usam `tenacity` para retry com backoff exponencial (3 tentativas, jitter, max 8s).
- Cada consumer registra-se com `consumer_tag = "{service}-{hostname}-{pid}"` para rastreabilidade.

## 5. Fluxos de dados

### 5.1 Ingestão (paralelismo de dados)

1. `POST /ingest` recebe doc (PDF, MD, HTML ou URL); FastAPI publica 1 mensagem em `ingest.documents`.
2. Workers consomem com `prefetch=2` (parsing é CPU-bound):
   - parse: PDF→texto via `pypdf`; HTML→`trafilatura`; MD→raw.
   - clean + detect language com `langdetect`.
   - chunk recursivo: target 800 tokens, overlap 120, fronteiras semânticas (`\n\n` → `\n` → `. ` → espaço).
   - publica 1 mensagem por chunk em `ingest.chunks`.
3. Workers consomem `ingest.chunks` com `prefetch=8` (embedding é IO+GPU bound):
   - hash do chunk; checa Redis `seen_doc_hashes` para dedupe.
   - chama `POST http://pc1:11434/api/embeddings` (batch de até 8 quando possível).
   - upsert no Qdrant com payload completo.
   - ack na fila; em caso de erro 3x, mensagem vai para `ingest.chunks.dlq`.

**Por que duas filas?** Separa CPU-bound de IO+GPU-bound; permite afinar prefetch e número de workers de forma independente; demonstra pipeline paralelo; DLQ por etapa facilita diagnóstico.

**Idempotência:**
- `doc_id = sha256(filename + size + first_1k_bytes)`.
- `chunk_id = f"{doc_id}:{chunk_index}"` — upsert sobrescreve.

### 5.2 Atendimento de query (paralelismo de tarefas)

1. `POST /query {"q": "...", "top_k": 5, "session_id": "..."}` no gateway.
2. Gateway gera `correlation_id`, cria fila exclusiva temporária `query.responses.{cid}`, publica em `query.requests` com `reply_to`.
3. Worker consome com `prefetch=1` (cada query usa GPU intensamente):
   - cache L1: `emb:{sha(query)}` no Redis. Hit → reutiliza embedding.
   - retrieval: Qdrant `search` com `top_k=20` e filtro de idioma quando aplicável.
   - re-rank: chama `POST http://pc1:8081/rerank` com 20 candidatos, recebe top-5.
   - montagem do contexto:
     - escolhe template de prompt PT/EN com base no idioma da query.
     - injeta system prompt versionado (`prompts/system_qa_{lang}.md`).
     - cap de tokens: orçamento `num_ctx=8192` no Qwen 2.5; reserva ~1500 para system+user+resposta; sobra ~6500 para chunks. Trunca chunks de cauda se necessário.
     - inclui metadados (`source`, `page`) nos blocos de contexto para o LLM citar.
   - cache L2: `resp:{sha(query+ids)}`. Hit → devolve direto.
   - gera: `POST http://pc1:11434/api/generate` com `temperature=0.2`, `num_ctx=8192`, function calling habilitado para `cite_source(doc_id, page, snippet)`.
   - parse + valida JSON da resposta com Pydantic; publica em `query.responses.{cid}` com `{answer, citations, usage, latency_ms}`.
4. Gateway recebe, devolve ao usuário, deleta a fila temp.

**Memória de sessão (cobre "gestão de histórico" do req 4.3):**
- `session_id` opcional. Histórico (até 3 trocas) em Redis: `session:{id}:history`.
- Quando passa de 3 turnos, prompt `prompts/session_summarizer.md` compacta para um resumo.

## 6. Engenharia de contexto explícita

Cobre integralmente o requisito 4.3.

### 6.1 Prompts versionados

Diretório `prompts/` separado do código. Arquivos:
- `prompts/system_qa_pt.md` — system PT-BR.
- `prompts/system_qa_en.md` — system EN.
- `prompts/user_qa_template.md` — Jinja2 com `{question}`, `{context_blocks}`.
- `prompts/session_summarizer.md`.
- `prompts/tools/cite_source.json` — schema da tool.

Cada arquivo tem frontmatter YAML: `version`, `model_target`, `last_changed`, `notes`. Versionamento real via git.

Em runtime: `prompt_registry.load("system_qa_pt", version="latest")`. Suporta `version=specific` para reproduzir experimentos.

### 6.2 Estratégia de chunking

- Recursive character splitter com fronteiras semânticas.
- Target 800 tokens, overlap 120.
- Detecção de idioma armazenada no payload do Qdrant.
- Para PDFs estruturados, metadados `section`/`subsection` opcionais.

### 6.3 Re-ranking em duas etapas

- Recall amplo: top-20 vetorial pelo Qdrant (rápido).
- Precisão: top-5 cross-encoder (mais caro, mais preciso).
- Cross-encoder em service dedicado (não compete pela GPU do Ollama).

### 6.4 Montagem do contexto dentro do limite de tokens

- Orçamento explícito: `num_ctx=8192`.
- Truncamento por chunk priorizando os melhor pontuados (não dropa chunks; trunca caudas).
- Bloco de contexto inclui `[source: {file} | page: {n}]` para o LLM citar.

### 6.5 Function calling

- Tool `cite_source(doc_id, page, snippet)` exposta ao Qwen 2.5 (formato OpenAI-compatible).
- Garante citações estruturadas em JSON validável.

### 6.6 Memória entre chamadas

- Conforme Seção 5.2: histórico em Redis com sumarização adaptativa.

## 7. Métricas e observabilidade (cobre req 4.4)

### 7.1 Métricas Prometheus

| Métrica | Tipo | Labels | Onde |
|---|---|---|---|
| `rag_request_duration_seconds` | Histogram | `endpoint`, `status` | API gateway |
| `rag_query_pipeline_duration_seconds` | Histogram | `phase`, `worker_id` | query-worker |
| `rag_ingest_pipeline_duration_seconds` | Histogram | `phase`, `worker_id` | ingest-worker |
| `rag_tokens_total` | Counter | `direction`, `model` | workers |
| `rag_throughput_docs_total` | Counter | `worker_id` | ingest-worker |
| `rag_throughput_queries_total` | Counter | `worker_id`, `status` | query-worker |
| `rag_errors_total` | Counter | `service`, `error_type` | todos |
| `rag_cache_hits_total` / `rag_cache_misses_total` | Counter | `cache_layer` | workers |
| `rag_queue_depth` | Gauge | `queue_name` | RabbitMQ exporter |
| `rag_ollama_inflight_requests` | Gauge | — | API gateway |

### 7.2 Dashboard Grafana "RAG Distribuído"

1. **Throughput** — docs/s indexados, queries/s atendidas, agregado e por worker.
2. **Latência** — p50/p95/p99, decomposta por fase (`embed`, `retrieve`, `rerank`, `generate`).
3. **Tokens** — entrada/saída por minuto, total acumulado.
4. **Saúde** — fila depth, taxa de erro, cache hit ratio, requests in-flight no Ollama.

### 7.3 Logs estruturados

JSON via `structlog`, campos obrigatórios já especificados. Indexação via Loki com label `correlation_id`. Queries `LogQL` reconstituem o fluxo end-to-end de uma query passando por gateway → worker → rerank → Ollama.

## 8. Tolerância a falhas (cobre req 4.5)

### 8.1 Retry com backoff

`tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=8))` em todos os clients HTTP externos (Ollama, Qdrant, rerank-service). Cada retry incrementa `rag_errors_total{error_type="retry"}`.

### 8.2 Dead Letter Queue

RabbitMQ com `x-dead-letter-exchange` em todas as filas principais. Política: 3 nacks → DLQ.

Filas DLQ:
- `ingest.documents.dlq` (parsing falhou).
- `ingest.chunks.dlq` (embedding falhou).
- `query.requests.dlq` (geração falhou de forma irrecuperável).

Script CLI `scripts/dlq_inspector.py` para listar, inspecionar e re-publicar mensagens depois de fix manual.

### 8.3 Estratégia de fallback

| Falha | Fallback |
|---|---|
| Ollama down (gerador) | API devolve 503 + `top_k` chunks brutos (degraded mode) |
| Ollama down (embeddings) | Worker faz `nack(requeue=True)` por até 30s; depois DLQ |
| Qdrant down | Cache L2 ainda atende queries vistas; novas queries → 503 |
| Re-ranker down | Skip rerank, usa top-5 vetorial direto. Loga `rerank.skipped_fallback` |
| RabbitMQ down | Gateway → 503; circuit breaker no client (3 falhas → backoff 10s) |
| Worker travado sem ack | RabbitMQ `consumer_timeout=300s` → mensagem volta à fila |

### 8.4 Healthchecks

Todo container tem `HEALTHCHECK`. API expõe `/health` que verifica RabbitMQ, Qdrant, Redis e Ollama. Se algum estiver down, status `degraded` (não down).

## 9. IaC e deploy

### 9.1 Modos de execução

**Modo 1 — All-in-one local (dev loop diário):**
- `docker compose --profile all up` no PC do desenvolvedor.
- Sobe tudo numa única máquina (RabbitMQ, Qdrant, Redis, Ollama, gateway, workers, rerank, observabilidade).
- URLs internas via DNS do compose (`amqp://rabbitmq:5672`, `http://ollama:11434`).
- Para devs sem GPU (PC2/PC3): substituir Ollama por modelo pequeno (`llama3.2:1b`) ou stub HTTP determinístico.

**Modo 2 — Distribuído real (integração + demo final):**
- PC1: `docker compose --profile server up` (rabbitmq, qdrant, redis, ollama, gateway, rerank, observabilidade).
- PC2/PC3: `docker compose --profile worker up` (ingest-worker, query-worker, node-exporter, promtail).
- URLs apontam para Tailscale IPs do PC1.

A mesma base de código suporta os dois modos via `.env`:
```
# .env.local (Modo 1, defaults do compose)
# (vazio — usa defaults)

# .env.distributed (Modo 2)
RABBITMQ_URL=amqp://guest:guest@100.x.y.z:5672/
OLLAMA_URL=http://100.x.y.z:11434
QDRANT_URL=http://100.x.y.z:6333
REDIS_URL=redis://100.x.y.z:6379
RERANK_URL=http://100.x.y.z:8081
```

### 9.2 Cadência de teste

| Frequência | Atividade | Modo |
|---|---|---|
| A cada commit | Unit tests + integration tests | Modo 1 |
| Antes de cada push | `make smoke` (1 doc, 3 queries) | Modo 1 |
| 2x/semana | Smoke distribuído | Modo 2 |
| Marco semanal | Experimentos 1–4 | Modo 2 |
| Final | Demo + apresentação | Modo 2 |

### 9.3 Terraform (provider docker)

Provider `kreuzwerker/docker` v3.x. Estrutura:
- `infra/terraform/main.tf` — networks, volumes, vars.
- `infra/terraform/modules/server/` — containers do PC1.
- `infra/terraform/modules/worker/` — containers de worker, parametrizados por host.
- State files locais por host: `infra/terraform/state/{pc1,pc2,pc3}.tfstate`.
- Variável `host_role ∈ {"server", "worker"}` controla quais módulos sobem.

### 9.4 Ansible

- `infra/ansible/inventory.yml` — hosts via Tailscale IPs.
- `playbook-bootstrap.yml` (roda 1x): instala Docker, NVIDIA toolkit (PC1), Tailscale; cria usuário `rag`; configura firewall.
- `playbook-deploy.yml` (a cada deploy): `git pull`, render `.env`, `terraform apply`, healthcheck pós-deploy.
- Segredos via Ansible vault.

### 9.5 Scripts e Makefile

`Makefile` com targets: `make bootstrap`, `make deploy`, `make smoke`, `make experiment N=X`, `make teardown`, `make dev` (Modo 1), `make logs`, `make dlq-inspect`.

### 9.6 Justificativa para o doc técnico

Seção dedicada explica a substituição de AWS Academy por equivalentes locais:

| AWS | Equivalente local |
|---|---|
| SQS | Filas RabbitMQ |
| SNS (fan-out) | Exchanges RabbitMQ topic/fanout |
| S3 | Volumes Docker bind-mount |
| DynamoDB | Redis (chaves+payload) ou payload do Qdrant |
| CloudWatch Metrics | Prometheus |
| CloudWatch Logs | Loki |
| Bedrock | Ollama (linha-base) e vLLM (experimento) |

O PDF aceita explicitamente "Plano B Final: Execução Local" e SLM auto-hospedado.

## 10. Plano experimental

Cada experimento gera CSV em `data/exp{N}/` + script de plot em `scripts/plot_exp{N}.py`. Reproduzível via `make experiment N={1..4}`.

### 10.1 Experimento 1 — Speedup da indexação

- Variável: N workers de ingestão ∈ {1, 2, 4, 6, 8}.
- Carga fixa: 80 PDFs (~3000 chunks).
- Métricas: tempo total, throughput (chunks/s), eficiência (`speedup/N`).
- Hipótese: speedup quase-linear até saturar Ollama (gargalo de embedding).

### 10.2 Experimento 2 — Throughput de queries vs concorrência

- Variável: C queries concorrentes ∈ {1, 2, 4, 8, 16, 32}.
- Pool fixo: 6 query-workers (2 por PC).
- Carga: 200 queries pré-definidas, mix PT/EN.
- Métricas: p50/p95/p99 de latência, throughput (q/s), taxa de erro.
- Hipótese: latência sobe linearmente até a fila começar a empilhar (backpressure).

### 10.3 Experimento 3 — Bônus: Ollama vs vLLM

- Sobe vLLM em paralelo (porta 8000) com `qwen2.5-7b-instruct-awq`.
- Repete Experimento 2 apontando o gerador para vLLM.
- Métricas adicionais: tokens/s agregado, GPU utilization, KV cache reuse.
- Tese para o doc: "*continuous batching do vLLM faz o paralelismo da aplicação escalar além do ponto onde Ollama satura*".
- Importante: durante Exp 3, Ollama do gerador é parado para liberar VRAM (Ollama de embeddings continua, em modelo pequeno).

### 10.4 Experimento 4 — Tolerância a falhas

Cenários:
- Mata `ingest-worker` no PC2 no meio de uma indexação. Mostra mensagens em DLQ + outro worker assumindo via `consumer_timeout`.
- Mata Ollama por 30s. Mostra retry+backoff nos logs e fallback "degraded mode" servindo chunks brutos.
- Sobrecarga deliberada: 100 queries em rajada. Mostra fila enchendo no Grafana e drenagem após.

## 11. Divisão de trabalho

| Trilha | Dono principal | Hosts | Áreas |
|---|---|---|---|
| **A — Servidor central** | Autor (PC1) | PC1 | API gateway, FastAPI, RabbitMQ setup, Qdrant, rerank-service, Ollama, Streamlit demo, IaC do server |
| **B — Workers e mensageria** | Colega 1 (PC2) | PC2 + integração | ingest-worker, query-worker, DLQ, retry, schemas Pydantic, dlq_inspector |
| **C — Observabilidade, eval, IaC distribuída** | Colega 2 (PC3) | PC3 + integração | Prometheus, Grafana, Loki, dashboards, Ansible, datasets de eval, experimentos 1–4, gráficos |

Cada trilha é diretório isolado (evita conflitos de merge). Pair review obrigatório via PR.

## 12. Cronograma (16 dias — entrega 2026-05-25)

Prazo apertado: 16 dias corridos a partir de 2026-05-09. Cronograma agressivo, com paralelismo máximo entre as 3 trilhas e cortes pré-definidos caso atrase.

| Bloco | Datas | Dias | Marco |
|---|---|---|---|
| **B1 — Setup e esqueleto** | 10-12/05 (dom-ter) | 3 | Tailscale entre 3 PCs ok. Repo com estrutura completa. Docker compose Modo 1 sobe rabbitmq+qdrant+redis+ollama+gateway+1 worker. **Marco luz-verde:** 1 doc ingerido + 1 query devolve resposta com citação no Modo 1 |
| **B2 — Pipeline completo** | 13-16/05 (qua-sáb) | 4 | Chunking robusto, re-rank cross-encoder, cache L1/L2, prompts versionados, function calling, métricas Prometheus, logs estruturados. Smoke test ponta-a-ponta passa no Modo 1 |
| **B3 — Tolerância a falhas + IaC + Modo 2** | 17-20/05 (dom-qua) | 4 | DLQ, retry/backoff, fallback degraded mode. Terraform+Ansible. Modo 2 distribuído validado nos 3 PCs. Grafana com 4 painéis. Corpus ~80 PDFs ingerido. Loki coletando logs |
| **B4 — Experimentos + doc técnico** | 21-23/05 (qui-sáb) | 3 | Exp 1, 2 e 4 rodam, geram CSV e gráficos. **Exp 3 (vLLM) só se cronograma estiver verde no início do dia 21**. Doc técnico (rascunho) em paralelo desde dia 21 |
| **B5 — Doc final + apresentação + buffer** | 24/05 (dom) | 1 | Doc técnico finalizado. Slides. Ensaio de demo. Relatórios individuais |
| **Entrega** | 25/05 (seg) | — | Repositório + doc técnico + slides + relatórios individuais |

**Paralelismo entre trilhas (essencial neste prazo):**
- B1: Trilha A monta gateway+rabbitmq, Trilha B monta esqueleto dos workers em mock, Trilha C monta Tailscale+Docker+observabilidade vazia.
- B2: A foca em rerank-service+prompts; B em chunking+embedding+retrieval; C em métricas+dashboards Grafana.
- B3: A faz fallbacks no gateway; B faz DLQ+retry nos workers; C faz Ansible+Terraform.
- B4: A escreve o doc técnico (arquitetura+contexto); B prepara cenários de Exp 4 (chaos); C roda Exp 1 e 2 e gera gráficos.

**Cortes pré-definidos caso atrase (em ordem de prioridade decrescente para cortar):**
1. **Exp 3 (vLLM)** — perde 10 pontos do bônus mas o sistema continua íntegro.
2. **Loki** (manter `docker logs` direto) — perde elegância, não perde requisito (logs estruturados continuam em JSON no stdout).
3. **Streamlit demo** — substituída por `curl`/Postman + dashboard Grafana ao vivo.
4. **Memória de sessão** — torna queries stateless (req 4.3 fala "quando o tema exigir"; RAG não exige).
5. **Terraform** — fica só Docker Compose + Ansible (PDF aceita "versão simplificada").

## 13. Mapeamento direto dos entregáveis (Seção 8 do PDF)

| Entregável | Onde |
|---|---|
| 8.1 Código completo | `src/`, `tests/` |
| 8.1 IaC | `infra/terraform/`, `infra/ansible/` |
| 8.1 Scripts deploy/teste | `scripts/`, `Makefile` |
| 8.1 README | `README.md` (será reescrito) |
| 8.1 Prompts versionados | `prompts/` |
| 8.2 Doc técnico (8–15 pgs) | `docs/arquitetura.md` |
| 8.2 Diagrama | Seção 3 do doc técnico |
| 8.2 Justificativa de paralelismo | Seção dedicada citando Exp 1 e 2 |
| 8.2 Engenharia de contexto + apêndice | Seção dedicada + `docs/prompts.md` |
| 8.2 Análise de resultados | Seção "Resultados" com Exp 1–4 |
| 8.2 Tolerância a falhas + cenários | Seção dedicada citando Exp 4 |
| 8.2 Limitações e melhorias | Última seção |
| 8.3 Apresentação 15–20 min + demo | `slides/` (Marp ou Slidev), Streamlit |
| 8.4 Relatório individual | `docs/individual/{nome}.md` |

## 14. Mapeamento dos critérios de avaliação (Seção 9)

| Critério | Peso | Cobertura |
|---|---|---|
| Corretude e funcionamento | 25% | Smoke tests, integration tests, demo ao vivo |
| Conceitos de PDP | 25% | RabbitMQ, DLQ, paralelismo de dados (Exp 1), de tarefas (Exp 2), backpressure visível, retry+backoff |
| Engenharia de contexto | 20% | `prompts/` versionado, chunking, re-rank cross-encoder, cap de tokens, function calling, sessão |
| Análise experimental | 15% | Exp 1–4 com CSV + gráficos + discussão |
| Documentação e apresentação | 10% | Doc técnico, ADRs, slides, demo |
| Inovação | 5% + bônus 10 | Topologia distribuída real (3 PCs), Exp 3 (Ollama vs vLLM), SLM auto-hospedado |

## 15. Estrutura do repositório

```
projeto_harness_engineering/
├── README.md
├── docs/
│   ├── arquitetura.md
│   ├── decisões.md          (ADRs)
│   ├── prompts.md           (apêndice)
│   ├── individual/{nome}.md (×3)
│   └── superpowers/specs/
├── prompts/
│   ├── system_qa_pt.md
│   ├── system_qa_en.md
│   ├── user_qa_template.md
│   ├── session_summarizer.md
│   └── tools/cite_source.json
├── src/
│   ├── gateway/
│   ├── workers/{ingest,query}/
│   ├── rerank_service/
│   ├── shared/
│   └── eval/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── load/
├── infra/
│   ├── terraform/{main.tf, modules/{server,worker}/, state/}
│   ├── ansible/{inventory.yml, playbook-*.yml, roles/}
│   ├── docker/{gateway,worker,rerank}.Dockerfile
│   └── grafana/{dashboards,datasources}/
├── scripts/
│   ├── seed_corpus.py
│   ├── run_experiment.py
│   ├── plot_exp{1..4}.py
│   ├── dlq_inspector.py
│   └── deploy.sh, teardown.sh, smoke_test.sh
├── data/eval_queries.jsonl
├── docker-compose.yml
├── .env.local
├── .env.distributed
├── pyproject.toml
└── Makefile
```

## 16. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| GPU do PC1 não comporta Ollama + vLLM simultâneos | vLLM sobe só durante Exp 3; Ollama do gerador é parado |
| Tailscale flaky na rede dos colegas | Plano B: `ssh -R` túneis reversos; pior caso, demo simulada com containers no PC1 (ainda atende req 4.1) |
| Re-ranker travando workers | Service separado com timeout agressivo + fallback "skip rerank" |
| `qwen2.5:7b` não cabe na VRAM | Cai para `qwen2.5:7b-instruct-q4_K_M` (4-bit) |
| Prazo de 16 dias é apertado | Cortes pré-definidos na Seção 12 (vLLM → Loki → Streamlit → memória de sessão → Terraform), nesta ordem. Status verde/amarelo/vermelho avaliado ao início de cada bloco (B1–B5) |
| B1 atrasa (Tailscale ou Docker GPU) | Plano B já no dia 1: trabalhar em Modo 1 local em paralelo com a investigação de rede; B3 já reservado para validar Modo 2 |
| Conflito de horário entre os 3 integrantes | Trilhas isoladas em diretórios disjuntos minimizam dependência síncrona; daily de 15min via texto/Discord ao final de cada bloco |
| Dataset de eval pobre | Trilha C cura ~50 queries de eval na Sem 2, não na Sem 4 |
| Membros sem GPU bloqueados em dev | Modo 1 com `llama3.2:1b` em CPU ou stub HTTP determinístico |

## 17. Limitações conhecidas e melhorias futuras

- **Sem hybrid search:** apenas vetorial + cross-encoder; BM25 daria recall maior mas adiciona complexidade. Mencionar como melhoria.
- **Sem index incremental sofisticado:** atualizações de doc forçam reingestão total (idempotência cobre, mas é caro). Versionamento de chunks por hash seria evolução.
- **Avaliação de qualidade limitada:** ~50 queries curadas manualmente; sem RAGAS/faithfulness automático. Mencionar.
- **Sem multi-tenancy:** uma collection única no Qdrant.
- **Sem autenticação na API:** acessível na rede Tailscale, ok para demo, não para produção.

## 18. Justificativa do uso de IA na construção do projeto

O PDF exige que toda ferramenta ou IA utilizada seja justificada (Seção "Instruções"). A equipe usa Claude Code com a skill de brainstorming para construir este spec, plano de implementação e revisões. O documento técnico final terá uma seção declarando explicitamente o uso, conforme o requisito.

---

**Status:** spec aprovado pelo usuário em sessão de brainstorming guiada. Próximo passo: invocar a skill `superpowers:writing-plans` para gerar plano de implementação detalhado.
