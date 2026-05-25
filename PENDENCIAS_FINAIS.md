# Pendências finais — fechamento do projeto

> Snapshot da sessão de **2026-05-24**. Entrega: **25/05**. A maioria depende do
> Pablo Abdon terminar a trilha externa dele (este PC no Tailscale como worker
> real) antes que o Modo 2 distribuído suba. A `abdon-workstation` fica apenas
> como teste simples de Tailscale. A Task 3 do B3 e o corpus mínimo local foram
> destravados em 2026-05-25.

---

## 1. Bloqueado por Pablo Abdon (não consigo destravar sozinho)

### 1.1 Task 3 do B3 — `/metrics` em workers
- [x] `src/shared/workers_metrics_server.py` (aiohttp standalone) entregue.
- [x] Workers (`ingest-worker-doc`, `ingest-worker-chunk`, `query-worker`) expondo `/metrics` na porta 9100.
- **Validação:** o job `workers` em `infra/prometheus/prometheus.yml` saiu de `DOWN`; `ingest-worker-doc`, `ingest-worker-chunk` e `query-worker` aparecem `UP` no `/targets`.

### 1.2 Este PC no Tailscale como worker real
- [x] Este PC conectado à tailnet do trio.
- [x] Tailscale instalado e conectado neste PC; máquinas visíveis na tailnet.
- [x] Docker + Docker Compose instalados.
- [x] `uv sync` rodando.
- [ ] Acesso ao PC1 via Tailscale validado.
- [ ] Aguardar Davi estar disponível para testar portas do PC1.
- **Consequência sem isso:** Modo 2 fica sem o worker externo do Pablo. Os experimentos do B4 que variam N workers (Exp 1, Exp 2) perdem um ponto da curva.

### 1.3 Corpus seedado
- [x] `scripts/seed_corpus.py` entregue.
- [ ] `samples/corpus/` curado com ~80 PDFs.
- **Consequência sem isso:** experimentos B4 sem corpus de escala suficiente; o smoke continua rodando com 1 PDF do B1.

### 1.4 Chaos test + DLQ inspector
- [x] `scripts/chaos_test.sh` (kill workers, kill Ollama, sobrecarga).
- [x] `scripts/dlq_inspector.py` (list / replay / purge).
- **Consequência sem isso:** Exp 4 (chaos test) não rodável; gestão das DLQs fica manual via `rabbitmqctl`.

---

## 2. Bloqueado pela trilha do João Miguel (B4 — experimentos)

### 2.1 Dataset de avaliação
- [x] `data/eval_queries.jsonl` com ≥30 queries PT/EN curadas.

### 2.2 Experimentos
- [ ] **Exp 1** — speedup indexação × N chunk-workers → `data/exp1/exp1.png`
- [ ] **Exp 2** — throughput × concorrência (C ∈ {1..32}) → `data/exp2/exp2.png`
- [ ] **Exp 4** — chaos test automatizado → `data/exp4/exp4.png`
- [ ] **Exp 3 (vLLM)** — **cortado** em 2026-05-24 (corte #1 da lista)

### 2.3 Seções do doc técnico (B4)
- [ ] §7 Resultados experimentais — preencher com os gráficos acima
- [ ] §8 Discussão — análise dos números dos experimentos

---

## 3. Posso destravar sozinho (não bloqueado)

### 3.1 Rebuild + validar a observabilidade que entreguei hoje ✓ 2026-05-24
- [x] `make down -v && make dev && sleep 30`
- [x] `http://localhost:9090/targets` — gateway, prometheus, rabbitmq, rerank-service e 3 targets do job `workers` `UP`
- [x] `http://localhost:15692/metrics` — plugin RabbitMQ ativo (confirmado indiretamente: target `rabbitmq` UP no Prometheus)
- [x] `http://localhost:3000` (admin/admin) — Dashboards → "RAG Distribuído" disponível
- [x] (opcional) Rodar `uv run python scripts/smoke_test.py` 2-3 vezes pra gerar tráfego suficiente nos painéis que dependem do gateway (`rag_request_duration_seconds`, `rag_errors_total{service="gateway"}`)
- [ ] (opcional) `http://localhost:3100/ready` — Loki ready (confirmar)
- [ ] (opcional) `http://localhost:3000/explore` com datasource Loki → `{service="gateway"}` devolve logs do gateway em JSON

### 3.2 Capturar evidência de observabilidade pro doc técnico
- [ ] Screenshot do dashboard Grafana populado → `data/grafana-rag-distribuido.png`
- [ ] Screenshot do `/targets` do Prometheus → `data/prometheus-targets.png`
- [ ] (Opcional) Screenshot do Explore do Loki filtrado por `correlation_id` → `data/loki-correlation.png`

### 3.3 Revisar e editar antes de submeter
- [ ] `docs/arquitetura.md` — leitura crítica seção por seção; ajustar voz; corrigir o que não me convencer; **assumir autoria** antes do PDF
- [ ] `docs/relatorios_aprendizagem/davi_cavalcante.md` — §11 (sessão de hoje): revisar com a mesma régua dos §6–§10; podar/expandir conforme o que ressoa; **assumir autoria**
- [ ] `docs/USO_DE_IA.md` — confirmar que a entrada de 2026-05-24 está como eu quero apresentar na arguição

### 3.4 Atualizar `TODO.md`
- [ ] Marcar Task 4 do B3 (Observabilidade) como concluída no meu lado (configs + dashboard JSON entregues; queries PromQL escritas)
- [ ] Marcar Task 5 (Terraform) e Task 6 (Ansible) do B3 como concluídas pelo João Miguel (commit `bba2fa8` ainda não refletido no TODO)
- [ ] Atualizar pendências do "Já feito" com a sessão de 2026-05-24

### 3.5 Geração do PDF (B5)
- [ ] Instalar dependências: `pandoc`, `xelatex`, `mermaid-filter` ou `@mermaid-js/mermaid-cli`
- [ ] Opção A (filter): `pandoc docs/arquitetura.md -o docs/arquitetura.pdf --pdf-engine=xelatex --filter mermaid-filter`
- [ ] Opção B (manual): exportar cada bloco `mermaid` com `mmdc -i diagram.mmd -o diagram.png`, substituir os blocos no `.md` por `![](diagram.png)`, rodar `pandoc` sem filter
- [ ] Validar paginação (8–15 pp), correção dos diagramas renderizados, encoding UTF-8

### 3.6 Slides + apresentação (B5)
- [x] `docs/slides/slides.md` em formato Marp
- [x] Render para PDF: `marp docs/slides/slides.md -o docs/slides/slides.pdf`
- [ ] Ensaio (15-20 min) com demo ao vivo (`make smoke` no Modo 1 ou Modo 2)

### 3.7 Misc (B5)
- [ ] `README.md` final — atualizar se necessário
- [x] `ENTREGA.md` — checklist final dos 4 entregáveis (8.1, 8.2, 8.3, 8.4 + Extra)
- [x] Pablo Abdon: relatório individual `docs/relatorios_aprendizagem/pablo_abdon.md` (entregável 8.4 dele)

---

## 4. Ordem sugerida quando o Pablo destravar

1. **Pablo valida este PC** no Tailscale como worker real; a `abdon-workstation` fica apenas como teste simples de Tailscale.
2. **Eu valido o dashboard** com workers populando as métricas (3.1) no host distribuído.
3. **Capturo as evidências** de observabilidade (3.2) — só fazem sentido com tráfego real dos workers.
4. **João Miguel roda os experimentos** Exp 1/2/4 contra Modo 2 completo (depende do 1.2 + 1.3).
5. **João Miguel preenche §7 e §8** do doc técnico com os gráficos.
6. **Eu reviso e edito** os documentos (3.3) já com os números experimentais dentro.
7. **Atualizo TODO** (3.4) com tudo refletido.
8. **Gero o PDF** (3.5).
9. **Faço os slides** (3.6) — mais rápido com o doc técnico estável.
10. **Misc final** (3.7) — `ENTREGA.md` + ensaio.

---

## 5. Plano B se o Pablo não destravar a tempo

Cortes em ordem (lista pré-definida do `TODO.md`):

1. ~~Exp 3 (vLLM)~~ — **já cortado** 2026-05-24
2. **Loki** — fica só `docker logs`; dashboards já não dependem (Promtail/Loki são extra). Cortar removendo os 2 serviços do compose e o painel/explore de logs do doc técnico
3. **Streamlit demo** — sempre foi opcional, substituída por curl + Grafana ao vivo
4. **Memória de sessão** — desativar via `session_id=None` em todas as queries; smoke continua passando
5. **Terraform** — fica só Compose + Ansible (mas já está pronto, não precisaria cortar)

Se faltar Pablo + tempo, o doc técnico vai pra entrega com **§7 e §8 mantendo o protocolo descrito mas declarando explicitamente que os dados não foram coletados** — postura honesta documentada já no §7.3 da versão atual. Pior cenário aceitável; arguição cobra a postura, não os números.

---

**Sobre o TODO.md atual:** entradas após 2026-05-23 não estão refletidas (Task 5/6 do B3 do João Miguel + Task 4 do B3 minha + decisões desta sessão). Item 3.4 acima cobre isso quando eu retomar.
