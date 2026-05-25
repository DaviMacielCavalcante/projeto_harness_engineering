# Tema 5 — RAG Distribuído

Sistema de Q&A com **Retrieval-Augmented Generation** distribuído entre 3 PCs físicos via Tailscale, sem custos de cloud. O corpus é em PT-BR sobre engenharia de software (arquiteturas, paradigmas, design patterns). O sistema demonstra paralelismo em duas dimensões — dados na ingestão (uma fila de docs alimenta N consumidores de chunks) e tarefas no atendimento (query-workers replicados consumindo de uma fila comum) — com observabilidade completa (Prometheus + Grafana + Loki) e tolerância a falhas em quatro camadas (retry, DLX/DLQ, degraded mode, fallback estrutural de citação).

- **Disciplina:** Engenharia de Contexto e Harness Engineering aplicada à Programação Distribuída e Paralela — CESUPA, 2.º bim 2026
- **Entrega:** 2026-05-25
- **Equipe:** Davi Cavalcante (autor, PC1+GPU), Pablo Abdon (PC2), João Miguel (PC3)

## Onde está cada coisa

| Tema | Documento |
|---|---|
| **Documento técnico** (entregável 8.2) | [`docs/arquitetura.md`](docs/arquitetura.md) — 9 seções + 3 diagramas + apêndices |
| **Diagramas** (componentes, sequência ingestão, sequência query) | [`docs/diagrams/`](docs/diagrams/) — sources `.mmd` + PNGs renderizados |
| **Guia de observabilidade** (métricas, dashboards, queries) | [`docs/observabilidade.md`](docs/observabilidade.md) — catálogo das 11 métricas + PromQL/LogQL prontos |
| **Decisões e prompts** | [`docs/decisoes.md`](docs/decisoes.md), [`docs/prompts.md`](docs/prompts.md) |
| **Slides e checklist final** | [`docs/slides/slides.md`](docs/slides/slides.md), [`ENTREGA.md`](ENTREGA.md) |
| **Declaração de uso de IA** (Extra) | [`docs/USO_DE_IA.md`](docs/USO_DE_IA.md) — política, fronteiras, entradas datadas |
| **Relatórios de aprendizagem** (entregável 8.4) | [`docs/relatorios_aprendizagem/`](docs/relatorios_aprendizagem/) — um arquivo por integrante |
| **Runbooks operacionais** | [`docs/setup-tailscale.md`](docs/setup-tailscale.md), [`docs/setup-gpu-pc1.md`](docs/setup-gpu-pc1.md) |
| **Spec original e planos de bloco** | [`docs/superpowers/specs/`](docs/superpowers/specs/), [`docs/superpowers/plans/`](docs/superpowers/plans/) |
| **Convenções para o Claude Code** | [`CLAUDE.md`](CLAUDE.md) |
| **Progresso operacional** | [`TODO.md`](TODO.md), [`PENDENCIAS_FINAIS.md`](PENDENCIAS_FINAIS.md) (snapshot a 24h da entrega) |

## Estado atual

| Bloco | Status |
|---|---|
| **B1 — Setup e pipeline mínimo** | ✓ fechado (smoke: 122 chunks indexados, query ~2.1s, 3 citações) |
| **B2 — Pipeline completo** | ✓ fechado (smoke estendido: cache L2, sessão, /metrics, rerank — `data/b2-smoke.txt`); function calling cabeado com ressalva documentada (§8.1 do doc técnico) |
| **B3 — Tolerância a falhas + IaC + Modo 2** | ✓ Tasks 1, 2, 3, 4, 5, 6 fechadas (DLX/DLQ, degraded mode, workers `/metrics`, observabilidade, Terraform, Ansible). Pendente: Modo 2 distribuído completo (depende de `abdon-workstation` no Tailscale) |
| **B4 — Experimentos + doc técnico** | Doc técnico redigido; experimentos Exp 1/2/4 pendentes (corpus + Modo 2). Exp 3 (vLLM) cortado por cronograma |
| **B5 — Finalização** | PDF do doc técnico, slides, ensaio — 24h restantes |

Detalhes ativos em [`PENDENCIAS_FINAIS.md`](PENDENCIAS_FINAIS.md).

## Stack

- **Linguagem:** Python 3.12, gerenciada com [`uv`](https://github.com/astral-sh/uv)
- **Gateway / rerank-service:** FastAPI + Uvicorn
- **Mensageria:** RabbitMQ 3-management (com plugin `rabbitmq_prometheus`)
- **Vector store:** Qdrant 1.12.4 (768d, cosine)
- **Cache / sessão:** Redis 7-alpine
- **LLM serving:** Ollama 0.23.2 — `qwen2.5:7b-instruct` (gerador) + `nomic-embed-text` (embeddings 768d)
- **Re-ranker:** `BAAI/bge-reranker-v2-m3` (cross-encoder, max 512 tokens)
- **Observabilidade:** Prometheus v2.55.1, Grafana 11.4.0, Loki 3.2.0, Promtail 3.2.0
- **IaC:** Terraform (provider `kreuzwerker/docker`) + Ansible
- **Rede privada (Modo 2):** Tailscale

## Pré-requisitos

- Docker e Docker Compose
- Python 3.12 (`uv` resolve automaticamente)
- (Opcional) GPU NVIDIA com `nvidia-container-toolkit` — runbook em [`docs/setup-gpu-pc1.md`](docs/setup-gpu-pc1.md)
- (Modo 2) Tailscale — runbook em [`docs/setup-tailscale.md`](docs/setup-tailscale.md)

## Como rodar — Modo 1 (single-host)

```bash
# Instala dependências no .venv
uv sync

# Sobe tudo (gateway + workers + Qdrant + RabbitMQ + Redis + Ollama + rerank + observabilidade)
make dev
make pull-models       # baixa qwen2.5:7b + nomic-embed-text + bge-reranker

# Roda o smoke ponta-a-ponta (ingest 1 PDF → query → citações)
make smoke

# Acessar UIs:
#   http://localhost:8000/health        gateway
#   http://localhost:3000               Grafana (admin/admin) — dashboard "RAG Distribuído"
#   http://localhost:9090/targets       Prometheus
#   http://localhost:3000/explore       Loki (datasource Loki)
#   http://localhost:15672              RabbitMQ Management (guest/guest)
#   http://localhost:6333/dashboard     Qdrant
```

Para validar a stack de métricas e dashboards, ver [`docs/observabilidade.md`](docs/observabilidade.md) seção 3.

## Como rodar — Modo 2 (3 PCs via Tailscale)

```bash
# A partir do PC1, com os 3 hosts no inventário Ansible
cd infra/ansible
ansible-playbook -i inventory.yml playbook-bootstrap.yml   # instala Docker + Tailscale + NVIDIA Toolkit (só PC1)
ansible-playbook -i inventory.yml playbook-deploy.yml      # sincroniza repo, gera .env.local, terraform apply em cada host

# Atalho
bash scripts/deploy.sh
```

Detalhes em [`docs/arquitetura.md`](docs/arquitetura.md) §6.

## Comandos de desenvolvimento

```bash
uv run pytest                          # testes (unit + integration marcadas)
RUN_INTEGRATION=1 uv run pytest        # inclui integration tests (precisam de stack subida)
uv run ruff check --fix .              # lint + auto-fix
uv run ruff format .                   # format
uv run mypy .                          # type-check strict
```

Scripts operacionais:

```bash
uv run python scripts/seed_corpus.py --corpus samples/corpus
uv run python scripts/dlq_inspector.py list ingest.chunks.dlq
bash scripts/chaos_test.sh
```

## Estrutura

```
.
├── src/
│   ├── gateway/             # FastAPI: /ingest, /query, /health, /metrics
│   ├── shared/              # config, logging, schemas, messaging, cache, metrics, session, clients
│   ├── workers/
│   │   ├── ingest/          # parsing, chunking (recursive splitter), embed → upsert
│   │   └── query/           # cache L1 → retrieve → rerank → cache L2 → generate → cite
│   └── rerank_service/      # FastAPI standalone com bge-reranker-v2-m3
├── prompts/                 # prompts versionados (frontmatter YAML) + tools/cite_source.json
├── infra/
│   ├── docker/              # Dockerfiles (gateway, worker, rerank)
│   ├── terraform/           # provider docker, modules/server, modules/worker, tfvars por host
│   ├── ansible/             # bootstrap + deploy, roles docker/tailscale/nvidia
│   ├── prometheus/          # prometheus.yml com 5 jobs de scrape
│   ├── grafana/             # datasources + dashboard "RAG Distribuído" (5 painéis)
│   ├── loki/                # loki-config.yml minimal single-node
│   └── promtail/            # promtail-config.yml com Docker SD + JSON pipeline
├── scripts/                 # smoke_test, seed_corpus, deploy.sh
├── tests/{unit,integration}/
├── samples/                 # PDFs/MDs de teste (corpus do B4 fica em samples/corpus/)
├── data/                    # b1-smoke.txt, b2-smoke.txt, b2-metrics.txt, b2-filas.png, experimentos B4
└── docs/                    # doc técnico, diagramas, observabilidade, relatórios, runbooks, USO_DE_IA
```

## Atendimento aos requisitos do enunciado

| Req | Como | Onde foi atendido |
|---|---|---|
| 4.1 Paralelismo de dados | `ingest-worker-chunk` replicado consumindo `ingest.chunks` | `src/workers/ingest/`, `docs/arquitetura.md` §3.1 |
| 4.1 Paralelismo de tarefas | `query-worker` replicado consumindo `query.requests` | `src/workers/query/`, `docs/arquitetura.md` §3.2 |
| 4.2 Mensageria com DLQ | RabbitMQ + DLX `rag.dlx` + filas `*.dlq` | `src/shared/messaging.py`, `docs/arquitetura.md` §5.2 |
| 4.3 Engenharia de contexto | Chunking recursivo, retrieval+rerank, prompts versionados, function calling (com ressalva), sessão | `prompts/`, `src/workers/`, `docs/arquitetura.md` §4 |
| 4.4 Observabilidade | 11 métricas Prometheus + dashboard Grafana + logs JSON via Loki | `src/shared/metrics.py`, `infra/grafana/`, `docs/observabilidade.md` |
| 4.5 Tolerância a falhas | Retry tenacity, DLX/DLQ, degraded mode, fronteira de erro por chunk, fallback estrutural | `src/shared/`, `src/gateway/routes.py`, `docs/arquitetura.md` §5 |
| 4.6 IaC | Terraform (provider `kreuzwerker/docker`) + Ansible | `infra/terraform/`, `infra/ansible/` |

## Entregáveis (Seção 8 do enunciado)

| Entregável | Onde |
|---|---|
| 8.1 Repositório Git | este repo |
| 8.2 Documento técnico (8–15 pp.) | [`docs/arquitetura.md`](docs/arquitetura.md) → gerar PDF com `pandoc` |
| 8.3 Apresentação + demo ao vivo | (a entregar em 25/05) |
| 8.4 Relatórios individuais | [`docs/relatorios_aprendizagem/`](docs/relatorios_aprendizagem/) |
| **Extra** Declaração de uso de IA | [`docs/USO_DE_IA.md`](docs/USO_DE_IA.md) |

## Licença

MIT — ver [`LICENSE`](LICENSE).
