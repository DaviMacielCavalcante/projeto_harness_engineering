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
| **Checklist final** | [`ENTREGA.md`](ENTREGA.md) — slides da apresentação entregues via link no Google Classroom (fora do repo) |
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
- [`uv`](https://github.com/astral-sh/uv) instalado:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh   # Linux/macOS
  # ou: pip install uv
  ```
- (Opcional) GPU NVIDIA com `nvidia-container-toolkit` — runbook em [`docs/setup-gpu-pc1.md`](docs/setup-gpu-pc1.md). **Sem GPU NVIDIA**, ver "Rodar sem GPU" abaixo.
- (Modo 2) Tailscale — runbook em [`docs/setup-tailscale.md`](docs/setup-tailscale.md)

## Como rodar — Modo 1 (single-host)

```bash
# Instala dependências no .venv
uv sync

# (Opcional) Em Modo 1 os defaults do docker-compose já funcionam.
# Se quiser customizar variáveis, copie o exemplo:
cp .env.example .env.local

# Sobe tudo (gateway + workers + Qdrant + RabbitMQ + Redis + Ollama + rerank + observabilidade)
make dev
make pull-models       # baixa qwen2.5:7b + nomic-embed-text + bge-reranker

# Roda o smoke ponta-a-ponta (ingest 1 PDF → query → citações)
make smoke

# Outros atalhos do Makefile:
make down              # derruba a stack
make logs              # tail -f de todos os containers
make clean             # down -v + remove .venv/.pytest_cache/.ruff_cache
make test              # uv run pytest tests/unit -v
make lint              # uv run ruff check src tests
```

> UIs (Grafana, Prometheus, RabbitMQ, Qdrant): ver **[Painéis e GUIs](#painéis-e-guis-observabilidade-e-infraestrutura)** abaixo.

### Rodar sem GPU (CPU / AMD / WSL)

O `docker-compose.yml` reserva uma GPU NVIDIA para o serviço `ollama`. Em máquinas sem NVIDIA, crie um override local (ignorado pelo Git) que remove essa reserva e baixe um modelo leve:

```bash
cat > docker-compose.override.yml <<'EOF'
services:
  ollama:
    deploy:
      resources:
        reservations:
          devices: []
EOF

make dev
make pull-models MODEL=llama3.2:1b   # gerador leve que roda em CPU
make smoke
```

A inferência fica mais lenta, mas o pipeline completo funciona.

## Como rodar — Modo 2 (3 PCs via Tailscale)

```bash
# 1) Copie o exemplo e preencha com os IPs Tailscale do PC1 (100.x.y.z)
cp .env.example .env.distributed
$EDITOR .env.distributed

# 2) Ajuste o inventário Ansible com os hosts da tailnet
cp infra/ansible/inventory.yml.example infra/ansible/inventory.yml
$EDITOR infra/ansible/inventory.yml

# 3) A partir do PC1, com os 3 hosts no inventário
cd infra/ansible
ansible-playbook -i inventory.yml playbook-bootstrap.yml   # instala Docker + Tailscale + NVIDIA Toolkit (só PC1)
ansible-playbook -i inventory.yml playbook-deploy.yml      # sincroniza repo, gera .env.local, terraform apply em cada host

# Atalho
bash scripts/deploy.sh
```

Como alternativa ao deploy.sh, é possível subir os containers de cada host via Terraform manualmente:

```bash
make tf-init
make tf-apply HOST=pc1   # ou pc2, pc3 — usa infra/terraform/envs/<host>.tfvars
make tf-destroy HOST=pc1
```

Detalhes em [`docs/arquitetura.md`](docs/arquitetura.md) §6.

## Painéis e GUIs (observabilidade e infraestrutura)

Com a stack de pé (`make dev` no Modo 1, ou `make tf-apply HOST=pc1` no Modo 2), os GUIs ficam nas portas abaixo. Em **Modo 1** use `localhost`; em **Modo 2** troque por **o IP Tailscale do PC1** (`100.x.y.z`) — toda a observabilidade vive no PC1.

| Recurso | URL (Modo 1) | Credenciais | Para quê |
|---|---|---|---|
| **Grafana** | http://localhost:3000 | `admin` / `admin` | Dashboard **"RAG Distribuído"** — 5 painéis: throughput, latência p95 por fase, tokens, saúde (Ollama in-flight + erros), cache hit ratio |
| **Grafana → Explore (Loki)** | http://localhost:3000/explore | `admin` / `admin` | Logs JSON estruturados; filtrar por `{service="gateway"}` ou `{correlation_id="q-…"}` para reconstituir um fluxo |
| **Prometheus** | http://localhost:9090 | — | `/targets` (saúde do scrape dos 5 jobs), `/graph` (PromQL ad-hoc nas métricas `rag_*`) |
| **RabbitMQ Management** | http://localhost:15672 | `guest` / `guest` | Filas, taxas de publish/consume, profundidade, DLQs (`*.dlq`), conexões |
| **Qdrant dashboard** | http://localhost:6333/dashboard | — | Collection `se_corpus`, `points_count`, busca exploratória |
| **Gateway** | http://localhost:8000 | — | `/health` e `/metrics` (exposição Prometheus em texto) |

> **Loki não tem GUI próprio** — é consultado via Grafana → Explore (datasource Loki já provisionado). A API responde em `http://localhost:3100/ready` apenas para healthcheck.

Catálogo das 11 métricas + queries PromQL/LogQL prontas em [`docs/observabilidade.md`](docs/observabilidade.md).

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
