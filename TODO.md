# TODO — Tema 5 (RAG Distribuído)

Checklist operacional de progresso. Para detalhes técnicos de cada item, ver os planos em [`docs/superpowers/plans/`](docs/superpowers/plans/).

**Entrega:** 2026-05-25 — **16 dias corridos**.
**Equipe:** trio. **Davi** (autor, host `pc1-davi`, GPU NVIDIA), **João Miguel** (host `pc2-jm`), **Pablo Abdon** (host `abdon-workstation`). **Nota histórica:** Davi implementou sozinho **todo o B1 e todo o B2** — tarefas marcadas `[Pablo Abdon→Davi]` e `[João Miguel→Davi]` eram originalmente escopo dos colegas, adiantadas pelo autor. Em B3+, designações `[Pablo Abdon]`/`[João Miguel]` representam pendências de equipe que ainda dependem dos colegas (ex: Tailscale/Docker nos hosts deles).

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
- [x] **Sessão 2026-05-11/12:** `docker-compose.yml` Modo 1 finalizado + gateway FastAPI mínimo (lifespan + `/health`, smoke de integração), relatório de aprendizagem atualizado
- [x] **Sessão 2026-05-13/15:** B1 `chunking.py` (recursive splitter, 5 testes verdes) + `parsing.py` (pypdf/md/html), modo code-partner
- [x] **Sessão 2026-05-16:** B1 `workers/ingest/main.py` — `handle_document` (parse→idioma→chunk→embed→upsert idempotente) + `main` (closure como DI sobre `consume_forever`), modo code-partner; sem teste unitário (validação no smoke da Task 14)
- [x] **Sessão 2026-05-17:** B1 `workers/query/prompt_builder.py` — `_load` + `build_prompt` (orçamento de chars, truncamento de cauda), TDD ✓ 7 testes verdes, mypy strict ok; criados os 3 prompts versionados (`system_qa_pt/en`, `user_qa_template`); `USO_DE_IA.md` §2.5 + `CLAUDE.md` atualizados (granularidade de TODO por experiência declarada; Claude não executa pytest/ruff/mypy nem commita), modo code-partner. **+ `workers/query/main.py`** — `handle_query` (validar → embed → retrieval Qdrant → build_prompt → generate → publica `QueryResponse` no `reply_to`, RPC sobre AMQP; caminho sem-hits curto-circuita o LLM) + `main` (closure como DI), mypy strict + ruff ok, sem unit (validação no smoke da Task 14). **Task 13 fechada.** **+ Task 14:** `Makefile` completo + `scripts/smoke_test.py` (health → ingest → wait → query → veredito, exit code), ruff/mypy strict verdes; `samples/eap_es_v1.pdf` adicionado. Código do B1 completo — falta só a aceitação (Task 15, contra stack real).
- [x] **Sessão 2026-05-18:** GPU PC1 habilitada (driver + NVIDIA Container Toolkit, Mint 22.3; runbook `docs/setup-gpu-pc1.md`). **Task 15 destravada:** smoke falhava em `Ollama 500 "input exceeds context length"` — chunks > teto do nomic (2048) porque `count_tokens_approx` (chars/4) subestima PT+PDF+WordPiece. Correções, modo code-partner: (a) `chunking.py` ganhou `max_tokens` + dimensionamento `min(target,budget)` convertido a char-space, **8 testes verdes** (3 patológicos); (b) `workers/ingest/main.py` — fronteira de erro por chunk (`except httpx.HTTPStatusError` → skip + `log.warning ingest.chunk.skipped`), upsert incremental por página, contador `indexed_total`. **`make smoke` passa**: resposta fundamentada, 3 citações, 122 chunks indexados; `pytest` 44 verdes. Cancelado o "TODO-2" (varredura no chunker — redundante+cega; backstop real é a fronteira do worker). Pendente: captura `data/b1-smoke.txt` + `ruff`/`mypy` formais.
- [x] **Sessão 2026-05-18/19:** Tailnet **dedicado** do trio criado (owner com identidade pessoal não-CESUPA — pegadinha do domínio de e-mail resolvida); PC1 `pc1-davi` + PC2 `pc2-jm` conectados, ping **direct** (~113ms — piso de latência inter-PC registrado p/ o B4); `abdon-workstation` pendente (Pablo Abdon indisponível na época). Runbooks **`docs/setup-tailscale.md`** e **`docs/setup-gpu-pc1.md`** escritos (este fechava 4 referências penduradas). **B2 iniciado, modo code-partner:** Task 2 `cache.py` (cache-aside L1/L2 Redis, `Protocol` p/ DI) — TDD ✓ **4 testes verdes**, mypy/ruff ok; bugs reais capturados no ciclo vermelho→verde (cache-aside invertido, `str.join` ao contrário, `labelnames` chave×valor). Task 3 `metrics.py` — 10 métricas §7.1 (Counter/Histogram/Gauge), registro único; pegadinhas `registry=REGISTRY` e vírgula-de-tupla. Task 4 `/metrics` no gateway — endpoint ✓; middleware `measure_requests` **fechado** (skip de `/metrics`, `perf_counter` em `try/finally`, `status_code` default `"500"` p/ contar exceções não-tratadas como erro e satisfazer mypy strict; `.observe()` no `Histogram` request_duration com labels `endpoint`/`status` controlados). Docstrings limpas de resíduo de scaffold (`cache.py`, `metrics.py`); `USO_DE_IA.md` §2.4 atualizado (IA passa a autorar documentação operacional). **B1 fechado no escopo do autor** — restam só os passos com `abdon-workstation` do Pablo Abdon (Tailscale, Docker, `uv sync`).
- [x] **Sessão 2026-05-23:** B3 **Task 2 fechada** (Fallback degraded no gateway), modo code-partner. **Marco "Tolerância a falhas (Davi)" do B3 concluído** (Tasks 1 + 2). Lifespan instancia `app.state.qdrant`/`app.state.ollama`; `/query` no `except TimeoutError` faz embed → `qdrant.query_points` (sem rerank) → monta `Citation[]` → devolve `answer="[degraded mode] sem síntese; veja as citações abaixo."` com `usage={tokens_in:0,tokens_out:0}` + `latency_ms` desde `t0=time.perf_counter()`; try interno + `except Exception → raise HTTPException(503) from None`. Métrica `rag_errors_total{service=gateway,error_type=query_timeout}` e log estruturado `query.degraded.*` complementares (trend vs evento). Docstring do handler reescrita pra anunciar caminho feliz vs degraded + 503/504 corretos. **Cluster de bugs do review (vermelho→verde):** typos críticos em labels Prometheus (`gatewway`/`query_tiimeout` — criariam séries órfãs no Grafana sem dar erro de runtime), `/` em vez de `;` no sentinel (smoke faz grep), `nt(...)` em vez de `int(...)` (NameError em runtime); caminho feliz escrito FORA do try → exceções vazariam como 500 cru em vez de 503; docstring desatualizada. **Saga do deploy (aprendizado conceitual):** primeiro smoke do degraded retornou 504 mesmo com `query.timeout` no log — investigação revelou container `rag-gateway` `Up 2 hours` rodando código velho (sem fallback). O caminho feliz funcionava porque não exercita as linhas novas — disfarça regressão. Lição: edição em `src/` neste projeto exige `docker compose build gateway && docker compose up -d --no-deps gateway`; não há volume mount com hot-reload (registrado no §10.1 do relatório). **mypy strict em test_dlq:** `declaration_result.message_count` é `int | None` no aio-pika → narrow com `count is not None and count >= 1` (não `cast` — a mensagem do assert deve mostrar `None` se vier). **Lints ruff em test_dlq:** RUF002 (`3×` → `3x`), SIM105 (`try/except/pass` em `CancelledError` → `contextlib.suppress`). **Validação:** `curl` direto no `/query` com worker parado devolveu degraded em `latency_ms=120066` (120s timeout interno + 66ms embed/qdrant); 2ª execução 54ms (cache quente). **Reatribuição de equipe:** `A→Davi`, `B→Pablo Abdon` (host `abdon-workstation`), `C→João Miguel` (host `pc2-jm`) — TODO + planos B1-B5 atualizados, hostnames corrigidos onde havia inconsistência (PC3 obsoleto). Code-partner.
- [x] **Sessão 2026-05-22:** B3 **Task 1 fechada** (DLX/DLQ + retry contado em `messaging.py`), modo code-partner. `declare_topology(conn, *bases)` substituiu `declare_queues`: DLX `rag.dlx` (DIRECT, durable) + por base, DLQ `f"{base}.dlq"` bindada (`routing_key=base`) + fila principal com `arguments={"x-dead-letter-exchange": "rag.dlx", "x-dead-letter-routing-key": base}`. `consume_forever` reescrito com ack/nack manual: contador `attempts` lido do header `x-attempts` (`cast(int, (msg.headers or {}).get("x-attempts", 0)) + 1`); no except, `>= max_attempts` → `reject(requeue=False)` (cai na DLX via arguments → DLQ), senão republica cópia na MESMA fila com `dict(msg.headers or {})` + `x-attempts` incrementado, e ack do original. Gateway lifespan atualizado pra chamar `declare_topology(conn, settings.queue_ingest_documents, settings.queue_ingest_chunks, settings.queue_query_requests)`. **Bugs reais capturados no review (vermelho→verde, sessão densa):** (a) `attemps = msg.headers["x-attempts"]` FORA do loop — `msg` ainda não existia (`NameError`) + typo no nome; (b) `if msg.headers is None: attempts = (msg.headers or {}).get(...)` — `if` cercando o `or {}` que JÁ era a defesa, deixando `attempts` indefinido em 99% dos casos; (c) mutação de `msg.headers["x-attempts"] = ...` em vez de variável local — TODO 1 era leitura pura; (d) `headers = msg.headers or {}` pegando REFERÊNCIA em vez de cópia (mutação do dict original ao setar a chave) → resolvido com `dict(msg.headers or {})`; (e) `channel.declare_exchange.publish(...)` — confusão de método-corrotina vs atributo `channel.default_exchange`; (f) `await msg.ack()` fora do `if/else` finalizando msg já `reject`-ada (double-finalize); (g) na `declare_topology`, atribuir os `arguments` de dead-letter à DLQ em vez da fila principal (papéis trocados — quem tem `x-dead-letter-*` é a fila ONDE as msgs morrem, não a que recebe); (h) `dlq = f"{base}.dlq"` (string) chamando `.bind` — confusão "nome vs objeto-fila" (o `.bind` é método do objeto retornado por `declare_queue`, não da string). **mypy strict:** `int((msg.headers or {}).get(...))` falhou porque o `FieldValue` union do aio-pika inclui `Decimal | FieldArray | FieldTable | datetime | None` (não-conversíveis pra int) → trocado por `cast(int, ...)` (promessa pura, consistente com `RerankerClient` §8.7). **+ Step 3 (test_dlq.py, IA implementou — fronteira code-partner: teste é contrato executável):** `test_message_lands_in_dlq_after_max_attempts` com topologia de nomes únicos (`test.b3.dlx`/`...dlq.queue`/`...dlq`), handler `always_fails`, consumer em `asyncio.create_task`, polling teto ~15s, cancel limpo com `await consumer_task` + `except CancelledError` (evita warning de teardown), asserts com mensagens diagnóstico — `RUN_INTEGRATION=1 uv run pytest tests/integration/test_dlq.py -v` ✓ 1 passed em 0.59s. **`make smoke` verde sem regressão** (B1 + B2 todos os asserts: query 41.99s, cache L2 8.7s = 20.7%, sessão OK, /metrics OK, rerank healthy). **Função calling segue dormente** (esperado): `cite_source(doc_id=..., page=5, snippet=...)` apareceu DENTRO do `content` da resposta (vazamento textual do §8.12), não como `tool_calls` paralelo — citações reais via fallback estrutural. **Pendente Task 1:** apagar volumes (`make down -v`) antes do 1º deploy "limpo" pra que as filas do B1/B2 sejam recriadas com `arguments` novos (RabbitMQ recusa redeclaração com argumentos diferentes — `PRECONDITION_FAILED`).
- [x] **Sessão 2026-05-21:** B2 **Task 5 fechada** (refatoração da ingestão em duas filas), modo code-partner. `document_handler.py` + `chunk_handler.py` novos; `main.py` reescrito (roteamento por `INGEST_ROLE` com closures como callback/DI); `config.py` +`ingest_role`; compose com dois ingest-workers dedicados. **Decisões de design:** `throughput_docs` passou a contar "doc particionado e enfileirado" (incrementado no doc-handler), não "doc indexado" — `chunk_index` ficou fora do schema `ChunkMessage` (correlation_id propaga só pelo header AMQP, lido via `msg.correlation_id`); chunk_handler sem skip-and-return (erros propagam → DLX no B3, evita trabalho descartável). **Bugs reais capturados no review (vermelho→verde):** polaridade invertida nos dois `if .strip()` (silenciaria 100% do pipeline sem levantar exceção), `point_id` derivado de `correlation_id` em vez de `chunk_id` (sobrescreveria todos os chunks de um doc num só ponto), `hexdigest` sem `()` + falta `int(hex,16)`, labels errados (`work_id`/`directions`/`ingest-orker-doc`), bare `except` no `detect()`, `tasks.append` dentro da closure (explosão de consumers). Lint: B905 no rerank-service (`zip(..., strict=True)`). **Smoke estendido passou:** 123 chunks, 3 citações, elapsed 28.2s — paridade com o B1, duas filas no fluxo. Primeira execução do smoke pegou ECONNRESET (corrida `Started`×`lifespan`) → débito técnico anotado (wait-for-ready no `smoke_test.py`). **+ Task 7 (`RerankerClient`, TDD):** wrapper httpx+tenacity sobre `POST /rerank`, clone do `ollama_client`; 3 testes verdes; `no-any-return` do `resp.json()` resolvido com variável intermediária tipada (sem `type: ignore`); `config.py` +`rerank_url`. **+ Task 8 (function calling cite_source + prompts v0.2.0-b2):** artefatos prontos — function calling **ainda não roda** (integração é Task 10). `prompts/tools/cite_source.json` (tool definition), `system_qa_pt/en` e `user_qa_template` atualizados (abordagem **híbrida**: tool primária + fallback textual `[doc_id:]`), `ContextBlock` +`doc_id`, +1 teste (5 verdes). **Fronteira code-partner exercida:** autor conduziu a redação dos prompts (engenharia de contexto), IA fez o código (`ContextBlock`) e — por delegação explícita "pra eficiência" — espelhou o `system_qa_en.md` a partir do `pt`. **Padrão Pablo Abdon→Davi/João Miguel→Davi aplicado:** revisadas as tasks adiantadas de colegas — cache (T2) e metrics (T3) eram trilha João Miguel → João Miguel→Davi; ingestão 2-filas (T5) e RerankerClient (T7) eram trilha Pablo Abdon → Pablo Abdon→Davi. **+ Task 9 (`shared/session.py`, TDD):** `SessionStore` com histórico (janela `max_turns`) + resumo acumulado em Redis, e **summarizer injetável** (Strategy/DI — evoluiu o plano que tinha concat hardcoded; B3 pluga o LLM sem mexer na classe); 6 testes verdes. Sessão densa de bugs num módulo pequeno, todos capturados no review: `.strip` sem `()`, `+= +` (unário em str), ternário C/JS vs Python, `setex(chave,ttl,valor)` com chave×valor trocados e `KEY_HIST`×`KEY_SUM` cruzados, `await` esquecido, `setex` do histórico preso no `if`, `self.KEY_SUM =` sobrescrevendo a constante, `or ""` retirado da linha que precisava. **+ Task 10 (query-worker integrado):** `handle_query` em 7 fases (cache L1/L2 + rerank c/ recuperação de metadata por id + fallback + preâmbulo de sessão + métricas por fase); smoke validou o caminho principal (rerank, 3 citações, 37s). Cluster denso de bugs (gauge zerada por `inc()` no try errado, loop iterando lista vazia, corpos feliz×fallback trocados, `history` list concatenado como str, `usage` como set, `block[index]` em elemento). mypy: subscrito vs `.get` (`Any` vs `Any|None`) + guard de `None`; `redis_client: Any` na fronteira do Protocol. **Candura:** L2-hit/sessão escritos mas não exercitados pelo smoke atual (Task 11); function-calling segue dormente (citações via caminho estrutural). **+ wait-for-ready no `smoke_test.py`** (poll resiliente no `/health`, liquida o débito do §8.6). Code-partner. **+ Task 11 (smoke estendido, IA implementou por cronograma):** asserções B2 (cache L2 35.0s→8.7s = 24.9%, sessão 2 turnos no Redis real, `/metrics`, rerank health); smoke verde do zero. **Marco B2 quase fechado** — faltam: function calling cabeado (req 4.3) e evidências do doc técnico. (`/metrics` nos workers é escopo do B3, não do B2.)

---

## B1 — Setup e pipeline mínimo (10–12/05, 3 dias)

**Marco luz-verde:** `make smoke` ingere 1 PDF e responde 1 query com citação no Modo 1.
**Plano detalhado:** [`b1-setup-e-pipeline-minimo.md`](docs/superpowers/plans/2026-05-09-tema5-b1-setup-e-pipeline-minimo.md)

### Pré-condições (paralelo, dia 1)
- [ ] **[Pablo Abdon]** Tailscale nos 3 hosts — **parcial** (tailnet dedicado; `pc1-davi` + `pc2-jm` direct ✓; `abdon-workstation` pendente). Runbook `docs/setup-tailscale.md`
- [ ] **[Pablo Abdon]** Docker e Docker Compose instalados em `abdon-workstation`
- [x] **[Davi]** GPU NVIDIA + nvidia-container-toolkit no PC1 ✓ driver + toolkit no PC1 (Mint 22.3); runbook `docs/setup-gpu-pc1.md`
- [ ] Repo clonado, `uv sync` rodando em **`pc2-jm`** (**[João Miguel]**) e **`abdon-workstation`** (**[Pablo Abdon]**)

### Shared modules (Pablo Abdon → Davi)
- [x] `src/shared/config.py` (Settings via pydantic-settings) — TDD ✓ 3 testes verdes
- [x] `src/shared/logging.py` (structlog JSON) ✓ smoke manual ok
- [x] `src/shared/schemas.py` (IngestRequest, QueryRequest, ChunkMessage, etc.) — TDD ✓ 14 testes verdes
- [x] `src/shared/ollama_client.py` (httpx + tenacity retry) — TDD ✓ 4 testes verdes
- [x] `src/shared/messaging.py` (aio-pika helpers) ✓ importa limpo, mypy strict ok

### Gateway (Davi)
- [x] `src/gateway/main.py` + `routes.py`: POST /ingest, POST /query, GET /health ✓ `main.py` (lifespan declara as filas), `routes.py` com `/health`, `/ingest` (fire-and-forget, doc_id content-addressable) e `/query` (RPC sobre AMQP, reply queue exclusiva, timeout 504); mypy strict + ruff ok, validação real no smoke (Task 14/15)

### Worker de ingestão (Pablo Abdon → Davi)
- [x] `src/workers/ingest/chunking.py` (recursive, overlap) — TDD ✓ 8 testes verdes (teto duro: param `max_tokens`, `min(target,budget)` em char-space, 3 inputs patológicos)
- [x] `src/workers/ingest/parsing.py` (PDF/MD/HTML) ✓ pypdf por página, md/html como texto bruto
- [x] `src/workers/ingest/main.py` (parse → chunk → embed → upsert Qdrant) ✓ robustez: fronteira de erro por chunk (`except httpx.HTTPStatusError` → skip + `log.warning`), upsert incremental por página, contador `indexed_total`; validado no smoke da Task 15 (122 chunks, 3 citações)

### Worker de query (Pablo Abdon → Davi)
- [x] `src/workers/query/prompt_builder.py` (templates + truncamento) — TDD ✓ 7 testes verdes, mypy strict ok
- [x] `src/workers/query/main.py` (embed query → retrieval → generate → reply) ✓ RPC sobre AMQP, mypy strict + ruff ok; validação real no smoke (Task 14)

### Infra Docker (Davi)
- [x] `infra/docker/gateway.Dockerfile`, `worker.Dockerfile`
- [x] `docker-compose.yml` com profile `all` (Modo 1)

### Prompts mínimos (Davi)
- [x] `prompts/system_qa_pt.md`, `prompts/system_qa_en.md`, `prompts/user_qa_template.md` ✓ frontmatter YAML versionado (v0.1.0-b1)

### Validação (João Miguel → Davi)
- [x] `scripts/smoke_test.py` + `Makefile` ✓ ruff/mypy strict verdes (validação real só na Task 15)
- [x] `samples/README.md` instruindo cada pessoa a pôr um PDF curto como `samples/exemplo.pdf` (PDFs são docs de terceiros — gitignored, não versionados)
- [x] **`make dev` + `make pull-models` + `make smoke` passam** ✓ 2026-05-18: resposta fundamentada, 3 citações, 122 chunks; `pytest` 44 verdes
- [x] Captura `data/b1-smoke.txt` (saída + logs estruturados) para o doc técnico ✓ 2026-05-18: health OK, ingest `i-b548baf2`, query elapsed 2.1s, resposta fundamentada com 3 citações (`ap_es_v1.pdf` pp. 51/107/10)

---

## B2 — Pipeline completo (13–16/05, 4 dias)

**Marco luz-verde:** smoke estendido valida 2 filas, rerank, cache L1/L2, citações, /metrics.
**Plano:** [`b2-pipeline-completo.md`](docs/superpowers/plans/2026-05-09-tema5-b2-pipeline-completo.md)

- [x] **[Davi]** `/metrics` no gateway (Prometheus) + middleware de medição ✓ endpoint serializa `REGISTRY` único; middleware `measure_requests` cronometra em `try/finally` (cobre exceção não-tratada como `status="500"`), pula auto-medição em `/metrics`
- [x] **[Pablo Abdon→Davi]** Refatorar ingestão em duas filas (`document_handler` + `chunk_handler`) ✓ 2026-05-21: autor adiantou. `handle_document` (parse→chunk→publish em `ingest.chunks`, sem tocar Ollama/Qdrant); `handle_chunk` (embed→upsert, `point_id` determinístico por `chunk_id`, sem try/except — erros propagam pro DLX que entra no B3); `main.py` roteia por `INGEST_ROLE` ∈ {documents,chunks,both} via closures-callback como DI sobre `consume_forever`; `config.py` +`ingest_role` Literal; compose `ingest-worker` → `ingest-worker-doc` + `ingest-worker-chunk`. Smoke estendido: 123 chunks, 3 citações, elapsed 28.2s; duas filas confirmadas no fluxo. Code-partner
- [x] **[Davi]** Rerank service (`src/rerank_service/`) com cross-encoder bge-m3 + Dockerfile ✓ FastAPI standalone (porta 8081): `lifespan` carrega `CrossEncoder(MODEL_NAME, max_length=512)` uma vez em `app.state.model`; `POST /rerank` monta pares (query, candidate.text) → `predict` → `sorted(zip(...), key=score, reverse=True)[:top_k]` → items com `id` via fallback `or`-chain (sentinela `"?"`); `latency_ms` int via `int((perf_counter()-started)*1000)`; `/health` + `/metrics`. Smoke local validado: discriminação ~14.500× entre relevante (score 0.235) e ruído (0.000016), `latency_ms=135` em CPU. Smoke containerizado validado (rag-rerank container): mesmos scores, `latency_ms=69-157`. **Cache do modelo resolvido em 3 iterações:** (a) `TRANSFORMERS_CACHE` é env legada → não funcionou; (b) `cache_folder=` no `CrossEncoder` é ignorado quando modelo não tem `modules.json` (caso do bge-reranker) → não funcionou; (c) `HF_HOME=/models` (env oficial do huggingface_hub) + pré-download no build + `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` em runtime → **cold start 0.9s, zero HTTP requests** (vs 56s na 1ª tentativa, ~90× mais rápido). `MODEL_NAME` parametrizado via `ARG`/`ENV` no Dockerfile (single source of truth — trocar de modelo é `--build-arg MODEL_NAME=outro/repo`). `.dockerignore` criado (gap descoberto durante a Task — gateway/worker buildavam com .venv/.git/data/ no contexto a todo build). Compose service `rerank-service` adicionado ao profile `all|server`. **Task 6 do plano B2 fechada (Steps 1-4).**
- [x] **[Pablo Abdon→Davi]** `RerankerClient` no query-worker — TDD ✓ 2026-05-21: autor adiantou. Wrapper httpx sobre `POST /rerank` com retry tenacity (3 tentativas, jitter), espelha o `ollama_client`; serviço já ordena/trunca, o client só repassa `items`. `config.py` +`rerank_url`. 3 testes verdes (ordem do serviço, payload enviado, retry no 500); `no-any-return` do `resp.json()["items"]` resolvido com variável intermediária tipada (sem `type: ignore`). Code-partner
- [x] **[João Miguel→Davi]** `src/shared/cache.py` (Redis L1 e L2) — TDD ✓ 4 testes verdes, mypy/ruff ok (code-partner; autor adiantou trilha João Miguel)
- [x] **[João Miguel→Davi]** `src/shared/metrics.py` (counters, histograms, gauges) ✓ 10 métricas §7.1, registro único (code-partner; autor adiantou trilha João Miguel)
- [x] **[Pablo Abdon]** `src/shared/session.py` (histórico + sumarização adaptativa) — TDD ✓ 2026-05-21: `SessionStore` (janela recente em `KEY_HIST` + resumo acumulado em `KEY_SUM`, ambos `setex` TTL 6h) com **summarizer injetável** (Strategy/DI — evolução do plano, que tinha concat hardcoded): default `concat_summarizer` (sem LLM) no B2, B3 troca por um que chama o LLM sem tocar na classe. `Protocol _RedisLike` (get/setex) p/ DI, igual `cache.py`. 6 testes verdes (cap em max_turns, overflow→resumo, sessão vazia, summarizer-espião confirma que a estratégia injetada é a chamada, concat default). Code-partner. **Bugs reais capturados no review (vermelho→verde):** `.strip` sem `()` (referência ao método, sempre truthy → função sempre caía no return errado); `+= +` (mais unário em `str` → TypeError); ternário em sintaxe C/JS (`cond ? a : b`) em vez de Python (`a if cond else b`); `setex(chave, ttl, valor)` com valor onde ia a chave, e o par chave×valor trocado entre as duas gravações; `KEY_HIST`×`KEY_SUM` cruzados; `await` esquecido nas chamadas Redis; `setex` do histórico preso dentro do `if` (gravaria só no overflow, nunca na 1ª pergunta); `self.KEY_SUM = setex(...)` sobrescrevendo a constante-template da classe; `or ""` removido da linha que precisava (fallback de `None` p/ satisfazer o `str` do summarizer). **Task 9 do plano B2 fechada.**
- [x] **[Davi]** Function calling `cite_source` (`prompts/tools/cite_source.json`) + prompts v0.2.0-b2 ✓ 2026-05-21: **artefatos prontos — function calling ainda NÃO roda** (integração `/api/chat`+`tools` e processamento de `tool_calls` é a Task 10). `cite_source.json` (tool definition formato Ollama/OpenAI: `doc_id`+`snippet` required, `page` integer|null); `system_qa_pt/en.md` v0.2.0-b2 (regra de chamar a tool + fallback textual `[doc_id:, page:]` — abordagem **híbrida**); `user_qa_template.md` com `doc_id` no header de cada bloco; `ContextBlock` +`doc_id` (default `""`) e propagação no truncamento do `build_prompt`. TDD: +1 teste (`doc_id` no prompt), 5 verdes. Autor conduziu os prompts; IA fez o código e espelhou o `en`. Code-partner
- [x] **[Pablo Abdon]** Query-worker integrado: cache L1 → retrieval → rerank → cache L2 → generate ✓ 2026-05-21: `handle_query` reescrito em 7 fases (kwargs explícitos p/ as 7 deps, code-partner). Cache L1 cache-aside no embed (`ollama_inflight` cercado em try/finally); retrieval top-20 (`retrieval_top_k_initial`); **rerank top-N→top-k com recuperação de metadata por id** (índice `{id: candidato}` antes do rerank, porque o rerank-service só devolve `{id,score,text}` e descarta `doc_id/source/page`) + fallback degradado (reranker down → top-k brutos do Qdrant); cache L2 (hit publica e `return`, pulando a geração); preâmbulo de sessão (resumo + histórico formatado, prefixado só se houver conteúdo); generation instrumentada; citações dos blocks reranqueados + grava L2/sessão + publica + `throughput_queries`. **Smoke validou o caminho principal**: ingest→query→rerank (3 citações, resposta fundamentada, 37s). **Candura de escopo:** (1) hit do cache L2 e preâmbulo de sessão estão escritos e type-checked, mas o smoke atual (1 query, sem `session_id`) NÃO os exercita em runtime — prova fica na Task 11; (2) **function calling segue dormente** — citações vêm do caminho estrutural (lado "fallback textual" do híbrido da Task 8); `/api/chat`+`tools`+`tool_calls` continua não-cabeado (ver pendência abaixo). **Bugs capturados no review (vermelho→verde):** `inflight.inc()` dentro do try (em vez do embed) zerando a gauge; `for cit in citations` iterando lista vazia; `item["id"]` no `doc_id` em vez do `doc_id` recuperado; corpos dos loops feliz×fallback trocados (`hit` vs `item` vazados de escopo); `history` (list) concatenado como str + `.get` em list; `usage` como set `{a,b}` em vez de dict; `block[index]` num elemento que já era o block. **mypy strict (16 erros):** raiz 1 = `.get()` devolve `Any|None` (vs `[...]`→`Any`) + guard de `None` faltando no fallback → subscrito + guard; raiz 2 = `redis.asyncio.Redis` não satisfaz o Protocol `_RedisLike` (param `name`≠`k`, retorno `Awaitable[Any]|Any`) → `redis_client: Any` na fronteira (débito: consolidar `_RedisLike` duplicado entre cache/session). Code-partner
- [x] **[Davi]** Smoke estendido valida cache L2, /metrics, rerank healthy ✓ 2026-05-22 (IA implementou — glue de script, autorizado por cronograma). `wait_for_ready` (poll resiliente no `/health`, débito do §8.6 liquidado) + asserções B2 no fim do `main()`: cache L2 (query repetida em **24.9%** do tempo, 35.0s→8.7s), **sessão** (dois turnos no mesmo `session_id`, exercita `get_history`/`append` no Redis real — cobertura além do plano, fecha lacuna de runtime do preâmbulo da Task 10), `/metrics` com `rag_*`, rerank `/health`. Smoke verde do zero. **Observação:** L2 fica pós-rerank → hit pula geração (~26s) mas paga rerank (~8s, o residual). **Task 11 do plano B2 fechada.**

**Pendências abertas (B2 — antes de declarar o bloco concluído):**
- ✅ **Function calling — req 4.3 RESOLVIDO COM RESSALVA (2026-05-22).** Cabeado: `OllamaClient.chat` (`/api/chat`+`tools`, 2 testes), query-worker (FASE 6/7) processa `tool_calls` em `Citation` recuperando `chunk_id`/`source` por `(doc_id, page)`, com fallback estrutural; **`build_messages()` (system/user separados) integrado na FASE 5/6** (`_render` extraído de `build_prompt`; preâmbulo de sessão prepende ao `user`, mantendo o `system` isolado; 2 testes novos, incl. invariante de equivalência com `build_prompt`). **Quatro alavancas de prompt testadas, todas `via=structural`:** imperativo (v0.2.1) → system isolado (build_messages, alavanca 2) → remoção do escape textual (v0.2.2) → exemplo few-shot (v0.2.3). **Diagnóstico isolado decisivo:** `/api/chat` mínimo fora do pipeline RAG → o `qwen2.5:7b` **CHAMA** a tool com argumentos perfeitos (`doc_id`/`page`/`snippet`). Logo: **modelo capaz + fiação correta; o contexto RAG denso é que suprime** a chamada. Ollama **não** suporta `tool_choice` (não dá pra forçar). **Decisão: aceitar e documentar** — 4.3 fica *"implementado, cabeado, capacidade comprovada; adesão do modelo sensível à densidade do contexto; fallback estrutural garante citações corretas"*. Achado caracterizado p/ o doc técnico (relatório §8.12). Prompts v0.2.3 autorados por IA via delegação declarada (registrado no rodapé do `USO_DE_IA.md`, 2026-05-22 — qualifica a afirmação anterior de "sem geração de prompt original pela IA").
- **Evidências do doc técnico (Task 12 Step 2):** `data/b2-metrics.txt` ✓ (70 linhas `rag_*`) + `data/b2-smoke.txt` ✓ (validações B2 verdes) capturados 2026-05-22. **Falta só** o screenshot das 2 filas (`ingest.documents`/`ingest.chunks`) no RabbitMQ Management UI.
- **Débito `_RedisLike` duplicado:** Protocol repetido em `cache.py` e `session.py`; consolidar num só em `shared/` e dar `cast` no wiring (hoje `redis_client: Any`).
- **Smoke não-idempotente no cache L2:** rodar `make smoke` 2× seguidas mascara o L2 — a 1ª query da 2ª rodada já é hit da rodada anterior (mesma pergunta+ids → mesma chave), então o AVISO de timing dispara à toa e as FASES de geração/citação nem rodam. Workaround: `redis-cli FLUSHALL` antes. Fix opcional: flush no início do smoke (acopla o teste ao Redis — talvez não valha o acoplamento).

> Nota: `/metrics` nos workers (ingest/query) **não** é pendência do B2 — é o `workers_metrics_server.py`, planejado para o **B3** (`CLAUDE.md`). Gateway e rerank-service já expõem.

---

## B3 — Tolerância a falhas + IaC + Modo 2 (17–20/05, 4 dias)

**Marco luz-verde:** sistema rodando distribuído nos 3 PCs; chaos test passa; corpus de ~80 docs indexado.
**Plano:** [`b3-tolerancia-iac-modo2.md`](docs/superpowers/plans/2026-05-09-tema5-b3-tolerancia-iac-modo2.md)

### Tolerância a falhas (Davi)
- [x] DLX `rag.dlx` + filas `*.dlq` em `messaging.py` (`declare_topology`) ✓ 2026-05-22: DIRECT durable + por base, DLQ bindada com `routing_key=base` + fila principal com `arguments` x-dead-letter-*; gateway lifespan atualizado. Test_dlq integração verde (1 passed, 0.59s); smoke sem regressão. Code-partner
- [x] `consume_forever` com max_attempts e nack-sem-requeue ✓ 2026-05-22: ack/nack manual, contador em `x-attempts` (`cast(int, ...)` pelo union do aio-pika), republicação com header incrementado em mensagem nova (cópia rasa do dict), `reject(requeue=False)` no esgotamento. Code-partner
- [x] Fallback "degraded mode" no gateway (chunks brutos quando workers/gerador falham) ✓ 2026-05-23: lifespan +`app.state.qdrant`/`app.state.ollama` (clients compartilhados); `/query` no `except TimeoutError` agora incrementa `errors{service=gateway,error_type=query_timeout}`, emite `log.warning("query.degraded.*")`, faz embed + `qdrant.query_points` direto (sem rerank — `req.top_k`), monta `Citation` por hit, e devolve `answer="[degraded mode] sem síntese; veja as citações abaixo."` com `usage={tokens_in:0,tokens_out:0}` + `latency_ms` medido com `t0` monotônico desde o início do handler. Try interno envolve o caminho feliz; `except Exception` → `raise HTTPException(503) from None` (Ollama/Qdrant fora → cliente recebe 503 explícito, não 500 cru). **Bugs reais capturados no review (vermelho→verde):** (a) typos críticos — `gatewway`/`query_tiimeout` em labels Prometheus (criariam séries paralelas órfãs no Grafana sem dar erro de runtime), `/` em vez de `;` na string sentinel (smoke faz grep), `nt(...)` em vez de `int(...)` (NameError); (b) caminho feliz do fallback escrito FORA de try → exceções Ollama/Qdrant vazariam como 500 cru em vez de 503; (c) docstring desatualizada (ainda anunciava só 504 nos Raises). **Saga do deploy:** primeiro `make smoke` do degraded retornou 504 inesperado mesmo com `query.timeout` no log do gateway — investigação dos logs revelou que o container `rag-gateway` estava `Up 2 hours`, anterior às edições do código, rodando a versão ANTIGA (sem o caminho degraded); o caminho feliz funcionava porque não exercita as linhas novas. Lição registrada no relatório §10.1: edição em `src/` exige `docker compose build gateway && docker compose up -d --no-deps gateway` — não há volume mount com hot-reload no compose deste projeto. **mypy strict no test_dlq:** `dlq_inspect.declaration_result.message_count` é `int | None` no aio-pika → type-narrowing com `count is not None and count >= 1` (não usei `cast` aqui porque a mensagem do assert deve mostrar `None` se vier — mais honesto que assumir int). **Validação:** `curl` direto no `/query` com `docker stop rag-query-worker` → resposta degraded em `latency_ms=120066` (120s do timeout interno + 66ms embed/qdrant); 2ª execução 54ms (Ollama/Qdrant cache quente); métrica `rag_errors_total{error_type="query_timeout",service="gateway"}=2.0`; log do gateway com `query.timeout → query.degraded.starting → query.degraded.responded n_citations=3` em 2 correlation_ids. Code-partner.

### Métricas em workers (Pablo Abdon)
- [ ] `src/shared/workers_metrics_server.py` (aiohttp standalone)
- [ ] Workers expondo /metrics nas portas 9100/9101/9102

### Observabilidade (Davi)
- [ ] `infra/prometheus/prometheus.yml` (scrape gateway + workers + rerank + rabbitmq)
- [ ] `infra/loki/loki-config.yml`, `infra/promtail/promtail-config.yml`
- [ ] `infra/grafana/datasources/datasources.yml` (Prometheus + Loki)
- [ ] `infra/grafana/dashboards/rag-distribuido.json` (4 painéis)
- [ ] Plugin `rabbitmq_prometheus` habilitado no compose

### IaC (João Miguel)
- [ ] `infra/terraform/{main.tf, variables.tf, modules/server, modules/worker}`
- [ ] `infra/terraform/envs/{pc1,pc2,pc3}.tfvars`
- [ ] `infra/ansible/{inventory.yml, ansible.cfg, playbook-bootstrap.yml, playbook-deploy.yml}`
- [ ] Roles Ansible: `docker`, `tailscale`, `nvidia` (só PC1)
- [ ] `scripts/deploy.sh`

### Operação (Pablo Abdon)
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

### Dataset de avaliação (Pablo Abdon)
- [ ] `data/eval_queries.jsonl` com ≥30 queries PT/EN curadas

### Experimentos (João Miguel)
- [ ] **Exp 1** — speedup indexação variando N workers — `data/exp1/exp1.png`
- [ ] **Exp 2** — throughput vs concorrência (C ∈ {1..32}) — `data/exp2/exp2.png`
- [ ] **Exp 4** — chaos test automatizado — `data/exp4/exp4.png`
- [ ] **Exp 3 (CONDICIONAL)** — Ollama vs vLLM — `data/exp3/exp3.png`
  - Só se cronograma estiver verde no início do dia 21
  - Inclui `src/shared/vllm_client.py` + override do compose

### Doc técnico (todas as trilhas, em paralelo)
- [x] `docs/arquitetura.md` esqueleto (8–15 páginas) ✓ 2026-05-22: scaffold de referência (status por seção, divisão de trilhas, números B1/B2 apurados, achado do function calling em §4/§8); conteúdo em prosa é trabalho B4 da equipe
- [ ] **[Davi]** §2 Arquitetura, §6 IaC e topologia
- [ ] **[Pablo Abdon]** §3 Fluxos, §4 Engenharia de contexto, §5 Tolerância a falhas
- [ ] **[João Miguel]** §7 Resultados experimentais, §8 Discussão e limitações
- [ ] `docs/decisoes.md` (ADRs)
- [ ] `docs/prompts.md` (apêndice com prompts versionados)

---

## B5 — Finalização (24/05, 1 dia)

**Marco luz-verde:** todos os entregáveis prontos para submissão em 25/05.
**Plano:** [`b5-final.md`](docs/superpowers/plans/2026-05-09-tema5-b5-final.md)

- [ ] **[Davi]** `docs/arquitetura.pdf` gerado (pandoc + xelatex)
- [ ] **[Davi]** `docs/slides/slides.md` em Marp + render para PDF
- [ ] **[Pablo Abdon]** Smoke a partir de clone limpo passa
- [ ] **[João Miguel]** Lint final zerado (`uv run ruff check . && uv run mypy .`)
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

## Débito técnico (não-bloqueante)

- [ ] `scripts/smoke_test.py`: trocar o `httpx.get("/health", timeout=5)` único por um **wait-for-ready** (retry com backoff, ~15–20s de teto) antes de seguir pro ingest/query. Motivo: `make dev` retorna quando os containers estão `Started`, mas o gateway ainda roda o `lifespan` (conecta RabbitMQ + declara filas) antes de servir — rodar o smoke logo após o `dev` pega `Connection reset by peer` (ECONNRESET) numa corrida de boot. Mais crítico no Modo 2 (latência Tailscale alarga a janela de inicialização). Descoberto em 2026-05-21.

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
- **Commits frequentes**, branches por trilha (`trilha/davi-gateway`, `trilha/pablo-workers`, `trilha/joao-infra-obs`), PRs com review cruzado.

---

_Atualize este arquivo conforme avançar — marque caixas, mova itens entre seções, adicione "(adiada)" / "(cortada)" quando necessário. Os planos em `docs/superpowers/plans/` permanecem como referência detalhada por bloco._
