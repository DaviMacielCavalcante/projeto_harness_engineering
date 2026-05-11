# TODO — Tema 5 (RAG Distribuído)

Checklist operacional de progresso. Para detalhes técnicos de cada item, ver os planos em [`docs/superpowers/plans/`](docs/superpowers/plans/).

**Entrega:** 2026-05-25 — **16 dias corridos**.
**Equipe:** trio. Trilhas: **A** = autor (PC1, com GPU), **B** = colega 1 (PC2), **C** = colega 2 (PC3).

---

## Já feito

- [x] Brainstorm e spec consolidado
  → [`docs/superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md`](docs/superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md)
- [x] 5 planos de execução (B1–B5)
  → [`docs/superpowers/plans/`](docs/superpowers/plans/)
- [x] Declaração de uso de IA
  → [`docs/USO_DE_IA.md`](docs/USO_DE_IA.md)
- [x] Scaffolding Python: `pyproject.toml` (3.12), ruff + mypy strict + pytest, estrutura `src/`, `tests/`, `infra/`, `prompts/`, `scripts/`, etc.
- [x] `CLAUDE.md`, `README.md`, `.env.example`, `.env.local`, `.gitignore`
- [x] `uv sync` resolveu, ruff/mypy/pytest passam num scaffold limpo
- [x] **Sessão 2026-05-09:** B1 shared modules `config.py`, `schemas.py`, `logging.py` (17 testes verdes, modo code-partner)
- [x] **Sessão 2026-05-10:** B1 `ollama_client.py` + `messaging.py` + Dockerfiles gateway/worker (21 testes verdes total, mypy strict ok, modo code-partner)

---

## B1 — Setup e pipeline mínimo (10–12/05, 3 dias)

**Marco luz-verde:** `make smoke` ingere 1 PDF e responde 1 query com citação no Modo 1.
**Plano detalhado:** [`b1-setup-e-pipeline-minimo.md`](docs/superpowers/plans/2026-05-09-tema5-b1-setup-e-pipeline-minimo.md)

### Pré-condições (paralelo, dia 1)
- [ ] **[C]** Tailscale instalado e autenticado nos 3 PCs
- [ ] **[C]** Docker e Docker Compose instalados nos 3 PCs
- [ ] **[A]** GPU NVIDIA + nvidia-container-toolkit no PC1
- [ ] **[B]** Repo clonado, `uv sync` rodando em PC2/PC3

### Shared modules (Trilha B, com par com A nos primeiros)
- [x] `src/shared/config.py` (Settings via pydantic-settings) — TDD ✓ 3 testes verdes
- [x] `src/shared/logging.py` (structlog JSON) ✓ smoke manual ok
- [x] `src/shared/schemas.py` (IngestRequest, QueryRequest, ChunkMessage, etc.) — TDD ✓ 14 testes verdes
- [x] `src/shared/ollama_client.py` (httpx + tenacity retry) — TDD ✓ 4 testes verdes
- [x] `src/shared/messaging.py` (aio-pika helpers) ✓ importa limpo, mypy strict ok

### Gateway (Trilha A)
- [ ] `src/gateway/main.py` + `routes.py`: POST /ingest, POST /query, GET /health

### Worker de ingestão (Trilha B)
- [ ] `src/workers/ingest/chunking.py` (recursive, overlap) — TDD
- [ ] `src/workers/ingest/parsing.py` (PDF/MD/HTML)
- [ ] `src/workers/ingest/main.py` (parse → chunk → embed → upsert Qdrant)

### Worker de query (Trilha B)
- [ ] `src/workers/query/prompt_builder.py` (templates + truncamento) — TDD
- [ ] `src/workers/query/main.py` (embed query → retrieval → generate → reply)

### Infra Docker (Trilha A)
- [x] `infra/docker/gateway.Dockerfile`, `worker.Dockerfile`
- [ ] `docker-compose.yml` com profile `all` (Modo 1) ⏳ esqueleto criado com TODOs

### Prompts mínimos (Trilha A)
- [ ] `prompts/system_qa_pt.md`, `prompts/system_qa_en.md`, `prompts/user_qa_template.md`

### Validação (Trilha C)
- [ ] `scripts/smoke_test.py` + `Makefile`
- [ ] `samples/exemplo.pdf` (1 PDF curto sobre engenharia de software)
- [ ] **`make dev` + `make pull-models` + `make smoke` passam**
- [ ] Captura `data/b1-smoke.txt` (saída + logs estruturados) para o doc técnico

---

## B2 — Pipeline completo (13–16/05, 4 dias)

**Marco luz-verde:** smoke estendido valida 2 filas, rerank, cache L1/L2, citações, /metrics.
**Plano:** [`b2-pipeline-completo.md`](docs/superpowers/plans/2026-05-09-tema5-b2-pipeline-completo.md)

- [ ] **[A]** `/metrics` no gateway (Prometheus) + middleware de medição
- [ ] **[B]** Refatorar ingestão em duas filas (`document_handler` + `chunk_handler`)
- [ ] **[A]** Rerank service (`src/rerank_service/`) com cross-encoder bge-m3 + Dockerfile
- [ ] **[B]** `RerankerClient` no query-worker — TDD
- [ ] **[C]** `src/shared/cache.py` (Redis L1 e L2) — TDD
- [ ] **[C]** `src/shared/metrics.py` (counters, histograms, gauges)
- [ ] **[B]** `src/shared/session.py` (histórico + sumarização adaptativa) — TDD
- [ ] **[A]** Function calling `cite_source` (`prompts/tools/cite_source.json`) + prompts v0.2.0-b2
- [ ] **[B]** Query-worker integrado: cache L1 → retrieval → rerank → cache L2 → generate
- [ ] **[A]** Smoke estendido valida cache L2, /metrics, rerank healthy

---

## B3 — Tolerância a falhas + IaC + Modo 2 (17–20/05, 4 dias)

**Marco luz-verde:** sistema rodando distribuído nos 3 PCs; chaos test passa; corpus de ~80 docs indexado.
**Plano:** [`b3-tolerancia-iac-modo2.md`](docs/superpowers/plans/2026-05-09-tema5-b3-tolerancia-iac-modo2.md)

### Tolerância a falhas (Trilha A)
- [ ] DLX `rag.dlx` + filas `*.dlq` em `messaging.py` (`declare_topology`)
- [ ] `consume_forever` com max_attempts e nack-sem-requeue
- [ ] Fallback "degraded mode" no gateway (chunks brutos quando workers/gerador falham)

### Métricas em workers (Trilha B)
- [ ] `src/shared/workers_metrics_server.py` (aiohttp standalone)
- [ ] Workers expondo /metrics nas portas 9100/9101/9102

### Observabilidade (Trilha A)
- [ ] `infra/prometheus/prometheus.yml` (scrape gateway + workers + rerank + rabbitmq)
- [ ] `infra/loki/loki-config.yml`, `infra/promtail/promtail-config.yml`
- [ ] `infra/grafana/datasources/datasources.yml` (Prometheus + Loki)
- [ ] `infra/grafana/dashboards/rag-distribuido.json` (4 painéis)
- [ ] Plugin `rabbitmq_prometheus` habilitado no compose

### IaC (Trilha C)
- [ ] `infra/terraform/{main.tf, variables.tf, modules/server, modules/worker}`
- [ ] `infra/terraform/envs/{pc1,pc2,pc3}.tfvars`
- [ ] `infra/ansible/{inventory.yml, ansible.cfg, playbook-bootstrap.yml, playbook-deploy.yml}`
- [ ] Roles Ansible: `docker`, `tailscale`, `nvidia` (só PC1)
- [ ] `scripts/deploy.sh`

### Operação (Trilha B)
- [ ] `scripts/seed_corpus.py` + curadoria de ~80 PDFs em `samples/corpus/`
- [ ] `scripts/dlq_inspector.py` (list / replay / purge)
- [ ] `scripts/chaos_test.sh` (kill workers, kill Ollama, sobrecarga)
- [ ] `tests/integration/test_dlq.py` passa

### Validação distribuída
- [ ] `make deploy` (Ansible) sobe 3 PCs
- [ ] `make smoke` apontando para PC1 via Tailscale passa
- [ ] Dashboard Grafana populado após 5 min de tráfego
- [ ] DLQ recebe mensagens em cenário de falha persistente

---

## B4 — Experimentos + doc técnico (21–23/05, 3 dias)

**Marco luz-verde:** Exp 1, 2, 4 com gráficos; doc técnico em rascunho avançado.
**Plano:** [`b4-experimentos-doc.md`](docs/superpowers/plans/2026-05-09-tema5-b4-experimentos-doc.md)

### Dataset de avaliação (Trilha B)
- [ ] `data/eval_queries.jsonl` com ≥30 queries PT/EN curadas

### Experimentos (Trilha C)
- [ ] **Exp 1** — speedup indexação variando N workers — `data/exp1/exp1.png`
- [ ] **Exp 2** — throughput vs concorrência (C ∈ {1..32}) — `data/exp2/exp2.png`
- [ ] **Exp 4** — chaos test automatizado — `data/exp4/exp4.png`
- [ ] **Exp 3 (CONDICIONAL)** — Ollama vs vLLM — `data/exp3/exp3.png`
  - Só se cronograma estiver verde no início do dia 21
  - Inclui `src/shared/vllm_client.py` + override do compose

### Doc técnico (todas as trilhas, em paralelo)
- [ ] `docs/arquitetura.md` esqueleto (8–15 páginas)
- [ ] **[A]** §2 Arquitetura, §6 IaC e topologia
- [ ] **[B]** §3 Fluxos, §4 Engenharia de contexto, §5 Tolerância a falhas
- [ ] **[C]** §7 Resultados experimentais, §8 Discussão e limitações
- [ ] `docs/decisoes.md` (ADRs)
- [ ] `docs/prompts.md` (apêndice com prompts versionados)

---

## B5 — Finalização (24/05, 1 dia)

**Marco luz-verde:** todos os entregáveis prontos para submissão em 25/05.
**Plano:** [`b5-final.md`](docs/superpowers/plans/2026-05-09-tema5-b5-final.md)

- [ ] **[A]** `docs/arquitetura.pdf` gerado (pandoc + xelatex)
- [ ] **[A]** `docs/slides/slides.md` em Marp + render para PDF
- [ ] **[B]** Smoke a partir de clone limpo passa
- [ ] **[C]** Lint final zerado (`uv run ruff check . && uv run mypy .`)
- [ ] Cada integrante: `docs/individual/<nome>.md` (1–2 páginas)
- [ ] `README.md` final completo
- [ ] `ENTREGA.md` com todos os itens marcados
- [ ] Ensaio da apresentação (15–20 min) com demo ao vivo

---

## Entregáveis finais (Seção 8 do PDF)

- [ ] **8.1** Repositório Git: código + IaC + scripts + README + prompts versionados
- [ ] **8.2** Documento técnico 8–15 páginas (`docs/arquitetura.pdf`)
- [ ] **8.3** Apresentação 15–20 min + demo ao vivo
- [ ] **8.4** Relatório individual de cada aluno (1–2 páginas)
- [ ] **Extra:** `docs/USO_DE_IA.md` (declaração de uso de IA)

---

## Cortes pré-definidos (em ordem, se atrasar)

1. **Exp 3 (vLLM)** — perde 10 pts do bônus; sistema continua íntegro.
2. **Loki** — fica só `docker logs`; logs estruturados em JSON continuam no stdout.
3. **Streamlit demo** — substituída por `curl`/Postman + dashboard Grafana ao vivo.
4. **Memória de sessão** — torna queries stateless.
5. **Terraform** — fica só Docker Compose + Ansible.

Avaliar status verde/amarelo/vermelho ao **início de cada bloco** (B1–B5).

---

## Cadência operacional sugerida

- **Daily texto rápido** (Discord/WhatsApp) ao final de cada dia: o que fechei, o que travou, o que faço amanhã.
- **Pareamento obrigatório** nos pontos de integração: B1 Tasks 5+10 (workers integrados), B3 Tasks 5+6 (Terraform+Ansible), B4 (validação distribuída end-to-end).
- **Smoke distribuído (Modo 2)** 2x/semana em B2/B3; toda execução de experimento em B4 já é Modo 2.
- **Commits frequentes**, branches por trilha (`trilha/A-gateway`, `trilha/B-workers`, `trilha/C-infra-obs`), PRs com review cruzado.

---

_Atualize este arquivo conforme avançar — marque caixas, mova itens entre seções, adicione "(adiada)" / "(cortada)" quando necessário. Os planos em `docs/superpowers/plans/` permanecem como referência detalhada por bloco._
