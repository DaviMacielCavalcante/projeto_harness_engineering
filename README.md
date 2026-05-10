# Tema 5 — RAG Distribuído

Sistema RAG (Retrieval-Augmented Generation) distribuído entre 3 PCs via Tailscale, sem custos de cloud. Domínio: engenharia de software (arquiteturas, paradigmas, design patterns).

**Disciplina:** Programação Distribuída e Paralela — CESUPA, 2º bimestre 2026
**Tema:** 5 — Sistema de Q&A sobre base de conhecimento (RAG distribuído)
**Entrega:** 2026-05-25

## Documentação

| O que | Onde |
|---|---|
| Spec do design (arquitetura, decisões, riscos) | [`docs/superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md`](docs/superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md) |
| Planos de execução por bloco do cronograma | [`docs/superpowers/plans/`](docs/superpowers/plans/) |
| Declaração de uso de IA | [`docs/USO_DE_IA.md`](docs/USO_DE_IA.md) |
| Convenções para Claude Code | [`CLAUDE.md`](CLAUDE.md) |

## Estado atual

Scaffolding inicial. Esqueleto Python + dependências resolvidas. A implementação propriamente dita segue o plano [B1 — Setup e Pipeline Mínimo](docs/superpowers/plans/2026-05-09-tema5-b1-setup-e-pipeline-minimo.md).

## Pré-requisitos

- Docker e Docker Compose
- Python 3.12 (uv baixa automaticamente se não tiver)
- [`uv`](https://github.com/astral-sh/uv) — package manager
- (Opcional) GPU NVIDIA com `nvidia-container-toolkit` para Ollama acelerado

## Modo 1 — Dev local (single-host)

Sobe tudo no mesmo PC. Use para desenvolvimento e testes rápidos.

```bash
# Instala deps no .venv
uv sync

# Roda testes
uv run pytest

# Lint e type-check
uv run ruff check .
uv run mypy .

# (A partir de B1) sobe stack e roda smoke
make dev
make pull-models
make smoke
```

## Modo 2 — Distribuído (3 PCs via Tailscale)

Configurado em B3. Para B1/B2, use só Modo 1.

## Estrutura

```
.
├── src/
│   ├── gateway/      # FastAPI: /ingest, /query, /health, /metrics
│   ├── shared/       # config, logging, schemas, messaging, ollama_client
│   ├── workers/
│   │   ├── ingest/   # parsing, chunking, embedding, upsert
│   │   └── query/    # retrieval, rerank, generation, citations
│   └── rerank_service/  # cross-encoder bge-reranker-v2-m3 (B2)
├── prompts/          # prompts versionados (req 4.3 do enunciado)
├── infra/
│   ├── docker/       # Dockerfiles
│   ├── terraform/    # provider docker (B3)
│   ├── ansible/      # provisionamento dos 3 PCs (B3)
│   ├── prometheus/   # config (B3)
│   ├── grafana/      # datasources + dashboards (B3)
│   ├── loki/         # config (B3)
│   └── promtail/     # config (B3)
├── scripts/          # smoke, seed, experimentos, plots
├── tests/{unit,integration}/
├── samples/          # PDFs/MDs de teste
├── data/             # saídas dos experimentos (B4)
└── docs/             # spec, planos, doc técnico, slides, relatórios individuais
```

## Atendimento aos requisitos do enunciado

| Requisito | Como |
|---|---|
| 4.1 — Paralelismo real (≥2 nós) | 3 PCs reais via Tailscale; mensageria RabbitMQ |
| 4.2 — Integração com LLM | Ollama (`qwen2.5:7b-instruct`) + nomic-embed-text |
| 4.3 — Engenharia de contexto | `prompts/` versionados, chunking, re-rank, function calling, sessão |
| 4.4 — Métricas | Prometheus em todos os componentes; Grafana com 4 painéis |
| 4.5 — Tolerância a falhas | Retry+backoff, DLX/DLQ, fallback degraded mode |

## Licença

MIT (ver [`LICENSE`](LICENSE)).
