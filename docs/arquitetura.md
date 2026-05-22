# Sistema RAG Distribuído — Documento Técnico (Tema 5)

> **STATUS: RASCUNHO/ESQUELETO** (gerado 2026-05-22 como referência de escopo — "não esquecer nada"). Não é o entregável final. Estrutura baseada no plano B4 e no spec. Cada seção marca: [✅ feito] / [🔶 parcial] / [⬜ B3/B4 pendente]. O conteúdo em prosa de cada seção é trabalho da equipe (divisão de trilhas abaixo); aqui ficam os pontos a cobrir e os números já apurados.

- **Disciplina:** Engenharia de Contexto e Harness Engineering aplicada a Programação Distribuída e Paralela
- **Tema 5:** Sistema RAG distribuído em 3 PCs físicos via Tailscale, sem cloud
- **Instituição/período:** CESUPA, 2º bim 2026 — entrega **2026-05-25**
- **Equipe (trilhas):** A = autor/PC1+GPU · B = colega 1/PC2 · C = colega 2/PC3
- **Meta de páginas:** 8–15 (req 8.2)
- **Divisão de autoria (plano B4):** §2/§6 → A · §3/§4/§5 → B · §7/§8 → C · todos no esqueleto e revisão

---

## Resumo executivo  [⬜ escrever por último]

- 1 parágrafo: o que é o sistema, os 3 PCs, o objetivo (RAG sobre corpus de eng. de software), o resultado principal.
- Destacar: distribuição real (não simulada), sem custos de cloud, observável e tolerante a falhas.

## 1. Introdução  [🔶]

- **Problema:** Q&A fundamentado sobre um corpus, com citações rastreáveis, distribuído e local.
- **Objetivos e escopo:** pipeline ingest + query distribuído; observabilidade; tolerância a falhas; experimentos quantitativos.
- **Mapa de requisitos do enunciado → onde foi atendido** (tabela). Incluir o **req 4.3 (function calling)** com a ressalva — ver §4 e §8.
- **Decisão de não usar cloud / mapeamentos** (SQS→RabbitMQ, S3→volumes, DynamoDB→Redis/Qdrant, CloudWatch→Prometheus+Grafana+Loki).

## 2. Arquitetura  [✅ B1/B2 feito · ⬜ diagrama final]  — Trilha A

- **Componentes:** gateway (FastAPI), ingest-worker (doc + chunk), query-worker, rerank-service (FastAPI + cross-encoder), Redis, Qdrant, RabbitMQ, Ollama, stack de observabilidade.
- **Topologia 3 PCs via Tailscale:** PC1 (gateway + infra + GPU/Ollama + Qdrant + RabbitMQ + Redis + rerank), PC2/PC3 (workers que falam com PC1 via IPs `100.x`). GPU só no PC1.
- **Modo 1 (Compose, single-host, dev/teste) vs Modo 2 (3 PCs reais).** Mesmo `docker-compose.yml` com profiles (`all`/`server`/`worker`).
- **Piso de latência inter-PC:** `tailscale ping` direct **~113ms** PC1↔PC2 (registrado para o B4).
- [ ] **DIAGRAMA de componentes** (caixas + filas + protocolos). Inserir aqui.
- **Stack/versões:** Python 3.12, Qdrant (vetores 768d, distância cosine, collection `se_corpus`), Ollama (`nomic-embed-text` 768d / `qwen2.5:7b-instruct`), `bge-reranker-v2-m3`.

## 3. Fluxos  [✅ B1/B2 feito · ⬜ sequence diagrams]  — Trilha B

- **Ingestão em 2 filas (pipeline parallelism):** `ingest.documents` (parse + chunk) → `ingest.chunks` (embed + upsert). Por quê: parsing é CPU-leve, embed é GPU/rede-caro — escalam diferente (1 doc-worker + N chunk-workers). `INGEST_ROLE` ∈ {documents,chunks,both}.
- **`point_id` determinístico** (`sha256(chunk_id)`) → upsert idempotente (replay/retry sobrescreve, não duplica).
- **Query pipeline (7 fases):** embed (cache L1) → retrieval top-20 → rerank top-5 → cache L2 → montagem de mensagens (+ preâmbulo de sessão) → geração (`/api/chat` + tools) → citações + grava L2/sessão + publica.
- **RPC sobre AMQP:** gateway abre reply-queue exclusiva, publica com `reply_to`, aguarda com timeout 120s; worker responde na reply-queue. Isolamento por channel.
- [ ] **SEQUENCE DIAGRAM** ingest e query.
- **Números do smoke (Modo 1):** 122–123 chunks indexados, 3 citações, query ~28–37s (cold), resposta fundamentada.

## 4. Engenharia de contexto  [✅ feito · achado a redigir]  — Trilha B

- **Chunking:** recursive character splitter (`\n\n`→`\n`→`. `→` `), target 800 / overlap 120 tokens; teto `max_tokens` (nomic 2048). Heurística chars/4 (limitação — ver §8).
- **Retrieval + rerank:** bi-encoder (top-20 vetorial, barato, pré-computado) → cross-encoder bge-m3 (top-5, caro, atenção cruzada). Por isso o rerank é serviço isolado.
- **Prompts versionados** (`prompts/`, frontmatter YAML): `system_qa_pt/en`, `user_qa_template`, `tools/cite_source.json`. Carregados via registry; `version=` reproduz experimentos.
- **Orçamento de tokens no `build_prompt`:** `num_ctx=8192`, trunca cauda (menos relevante) se estourar.
- **Cache L1 (embedding de query, TTL 7d) / L2 (resposta inteira, TTL 1h).** L2 chaveado por `(query, retrieved_ids)`, fica pós-rerank → hit pula geração (~26s) mas paga rerank (~8s): 2ª query repetida em **24.9%** do tempo (35.0s→8.7s).
- **Sessão:** janela de turnos + resumo acumulado em Redis, summarizer injetável (Strategy/DI; concat no B2, LLM no B3).
- **★ Function calling (`cite_source`) — req 4.3, COM RESSALVA (escrever como achado, não como falha):**
  - Implementado e cabeado: `/api/chat`+`tools`, processamento de `tool_calls`→`Citation`, `build_messages` (system/user separados), fallback estrutural.
  - **Capacidade comprovada:** diagnóstico isolado (`/api/chat` mínimo) → o 7B chama a tool com argumentos perfeitos.
  - **Não-adesão sob contexto RAG denso:** 4 alavancas de prompt (imperativo → system isolado → remoção do escape → few-shot) → todas `via=structural`.
  - **Restrição:** Ollama não suporta `tool_choice` (não dá pra forçar).
  - **Conclusão:** fallback estrutural produz citações corretas; 4.3 "implementado, com ressalva de adesão do modelo". Cross-ref §8.

## 5. Tolerância a falhas  [⬜ B3 — em grande parte ainda não implementado]  — Trilha B

- **Já existe (B1/B2):** retry tenacity (3×, backoff+jitter, máx 8s) em todo client HTTP externo; fronteira de erro por chunk (skip vs propaga); `wait_for_ready` no smoke; cadeia `or`+sentinela no rerank.
- **B3 (pendente):** DLX `rag.dlx` + filas `*.dlq` (3 nacks→DLQ); `consume_forever` com max_attempts; **degraded mode** no gateway (chunks brutos quando workers/gerador falham); `dlq_inspector.py`; `chaos_test.sh`.
- Cross-ref filosofia "degradar > quebrar" (relatório §7.4/§8.4).

## 6. IaC e topologia  [⬜ B3 — pendente]  — Trilha A

- **Tailscale:** tailnet dedicado (pegadinha do domínio `@aluno.cesupa.br` resolvida); runbook `docs/setup-tailscale.md`. Superfície de exposição (Redis/Qdrant/Ollama sem auth → tailnet privado).
- **GPU PC1:** driver NVIDIA + Container Toolkit; runbook `docs/setup-gpu-pc1.md`.
- **B3 (pendente):** Terraform (`modules/server`, `modules/worker`, `envs/{pc1,pc2,pc3}.tfvars`), Ansible (roles docker/tailscale/nvidia, playbooks bootstrap/deploy), `deploy.sh`.

## 7. Resultados experimentais  [⬜ B4 — dados ainda não coletados]  — Trilha C

- **Dataset de avaliação:** `data/eval_queries.jsonl` (≥30 queries PT/EN) — a curar.
- **Exp 1 — speedup de indexação** variando N chunk-workers → `data/exp1/exp1.png`.
- **Exp 2 — throughput vs concorrência** (C ∈ {1..32}) → `data/exp2/exp2.png`.
- **Exp 4 — chaos test** (kill worker / kill Ollama / sobrecarga) → `data/exp4/exp4.png`.
- **Exp 3 (CONDICIONAL, bônus +10) — Ollama vs vLLM** → `data/exp3/exp3.png`. Primeiro corte se atrasar.
- Cada experimento: hipótese, setup (Modo 2!), gráfico, leitura. Lembrar do floor de ~113ms (§2).

## 8. Discussão e limitações  [🔶 — function calling já dá pra escrever]  — Trilha C

- **★ Function calling sob contexto RAG denso (o achado):**
  - Definir "contexto RAG denso" (razão conteúdo/instrução alta; top-5 chunks vs instrução pequena).
  - Hipótese da não-adesão: diluição da instrução + viés de instruct-tuning p/ prosa + competição de formato.
  - **Modelo maior resolveria?** Provavelmente ajuda, não garante; esbarra na GPU única do PC1 e no modelo pinado pelo spec. Alavancas melhores que tamanho: **passada dupla** (2ª chamada LLM dedicada só a citar, contexto enxuto) e **decodificação restrita** (`format: json`). Trabalho futuro.
- **Heurística chars/4 do token-count:** subestima PT/PDF/WordPiece; backstop real é a fronteira de erro do worker (não o chunker).
- **Cache L2 pós-rerank:** economiza geração, não o rerank (trade-off latência × correção da chave).
- **Débitos:** `_RedisLike` duplicado (cache/session); smoke não-idempotente no L2 (precisa FLUSHALL); idempotência por posição (não conteúdo) até o B3.
- **Limites de escopo:** sessão stateless se cortada (lista de cortes do spec); Modo 2 ainda parcial (PC3 pendente).

## 9. Conclusão  [⬜ escrever por último]

- O que foi entregue vs objetivos; o que os experimentos mostraram; o que a equipe aprendeu sobre distribuído real.

---

## Apêndices

- **A. Prompts versionados** → `docs/prompts.md` (apêndice gerado dos `prompts/`, com changelog de versões).
- **B. ADRs (decisões de arquitetura)** → `docs/decisoes.md`.
- **C. Declaração de uso de IA** → `docs/USO_DE_IA.md`.
- **D. Runbooks** → `docs/setup-tailscale.md`, `docs/setup-gpu-pc1.md`.
- **E. Evidências** → `data/b1-smoke.txt`, `data/b2-smoke.txt` (⬜), `data/b2-metrics.txt` (⬜), screenshot 2 filas (⬜).

## Pré-requisitos de evidência ainda a capturar (Task 12 Step 2)

- [ ] `data/b2-metrics.txt` (`/metrics` head -100)
- [ ] `data/b2-smoke.txt` (smoke estendido completo)
- [ ] Screenshot RabbitMQ Management UI com `ingest.documents` + `ingest.chunks`
- [ ] (B4) gráficos dos experimentos
