# projeto_harness_engineering

Sistema RAG (Retrieval-Augmented Generation) distribuído entre 3 PCs físicos via Tailscale, sem custos de cloud. Trabalho do Tema 5 da disciplina de Programação Distribuída e Paralela (CESUPA, 2º bim 2026), com entrega em **2026-05-25**.

## Antes de tudo: leia o spec e o plano vigente

Este projeto tem documentação densa que precede o código. Quando você (Claude) entrar numa sessão para mexer aqui, **primeiro leia**:

1. `docs/superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md` — arquitetura completa, decisões, riscos.
2. O plano de bloco em execução, em `docs/superpowers/plans/2026-05-09-tema5-bN-*.md` (B1 → B5, em ordem).
3. `docs/USO_DE_IA.md` — declaração pública do uso de IA, base para a seção equivalente no doc técnico.

Não improvise arquitetura. Se algo no spec parecer errado, levante e converse antes de divergir.

## Project layout

App distribuído com múltiplos serviços. Layout `src/` (não-flat) porque há vários componentes que compartilham módulos:

- `src/gateway/` — FastAPI: endpoints `/ingest`, `/query`, `/health`, `/metrics`.
- `src/shared/` — código transversal (config, logging, schemas, messaging, ollama_client, cache, metrics, session).
- `src/workers/ingest/` — consumer do pipeline de ingestão (parse → chunk → embed → upsert Qdrant).
- `src/workers/query/` — consumer do pipeline de query (embed → retrieve → rerank → generate → reply).
- `src/rerank_service/` — FastAPI dedicado ao cross-encoder bge-reranker-v2-m3 (entra em B2).
- `prompts/` — prompts versionados (separado do código por exigência do enunciado, req 4.3).
- `infra/` — Dockerfiles, Terraform, Ansible, configs Prometheus/Grafana/Loki.
- `scripts/` — smoke, seed, experimentos, plots.
- `tests/{unit,integration}/`.
- `samples/` — PDFs/MDs de teste.
- `data/` — saídas dos experimentos (CSVs e PNGs).

`pyproject.toml` tem `[tool.uv] package = false` — o projeto é uma app, não um pacote distribuível. `tests/conftest.py` adiciona a raiz ao `sys.path` para que `import src.*` funcione.

## Tooling

Este projeto usa **uv** como package manager. Sempre use uv para operações de dependência — nunca edite `pyproject.toml` à mão para adicionar deps, e nunca invoque `pip` direto.

Comandos comuns:

- `uv sync` — instala/atualiza tudo a partir do lockfile
- `uv add <pkg>` — adiciona dep de runtime
- `uv add --dev <pkg>` — adiciona dep de dev
- `uv remove <pkg>` — remove dep
- `uv run <cmd>` — roda comando dentro do venv
- `uv run pytest` — roda testes
- `uv run ruff check .` — lint
- `uv run ruff format .` — format
- `uv run mypy .` — type-check

Para subir/derrubar a stack completa (containers), use `make dev` / `make down` (Makefile chega em B1, Task 14).

## Stack e principais dependências runtime

- **fastapi + uvicorn** — gateway HTTP e rerank-service.
- **aio-pika** — cliente RabbitMQ assíncrono (mensageria entre componentes).
- **qdrant-client** — vector database (collection `se_corpus`, vetores 768d nomic).
- **redis (aredis)** — cache distribuído L1/L2 + sessão.
- **httpx** — chamadas HTTP a Ollama, vLLM, rerank-service.
- **pydantic + pydantic-settings** — schemas e configuração tipada via env.
- **structlog** — logs JSON estruturados com `correlation_id`.
- **tenacity** — retry com backoff exponencial em chamadas externas.
- **prometheus-client** — métricas em todos os componentes.
- **pypdf, langdetect, jinja2** — parsing de docs, detecção de idioma, templates de prompt.

Stack externa em containers (não Python): RabbitMQ, Qdrant, Redis, Ollama, Prometheus, Grafana, Loki, Promtail.

## Convenções de código

- **Python 3.12** (pinado em `requires-python = ">=3.12,<3.13"`).
- **Type hints obrigatórios** em todas as assinaturas. `mypy --strict` deve passar; evitar `# type: ignore` (já tem overrides para libs sem stubs em `pyproject.toml`).
- **Docstrings estilo NumPy** — só onde o significado não é óbvio pelo nome (módulos não-triviais, funções públicas com lógica relevante). Em testes, scripts e `__init__.py`, o ruff já dispensa docstrings.
- **Linha 100** chars (configurado no ruff).
- **Imports ordenados pelo ruff** (isort-compatible). Não reordene à mão; rode `uv run ruff check --fix .`.
- **Logs sempre via `structlog`**, com `bind_correlation_id`/`clear_correlation_id` envolvendo o handler de cada mensagem para que o `correlation_id` apareça em todas as linhas do fluxo.
- **Async-first** — todos os módulos de IO usam `async`/`await`. Não misture com código síncrono bloqueante dentro de coroutines (ex: nada de `requests.get` dentro de async).
- **Schemas Pydantic** para qualquer mensagem trocada entre serviços (RabbitMQ, HTTP). Definir em `src/shared/schemas.py` e importar em todos os lados — fonte única da verdade.
- **Nomes**: `snake_case` para funções/variáveis, `PascalCase` para classes, `UPPER_SNAKE` para constantes.

### Exemplo de docstring (NumPy)

```python
def chunk_text(text: str, target_tokens: int, overlap_tokens: int) -> list[str]:
    """Divide texto em chunks recursivamente respeitando fronteiras semânticas.

    Parameters
    ----------
    text : str
        Texto a ser dividido.
    target_tokens : int
        Tamanho alvo de cada chunk (em tokens aproximados).
    overlap_tokens : int
        Tokens repetidos entre chunks adjacentes para preservar contexto.

    Returns
    -------
    list of str
        Chunks na ordem original do texto, sem perda de conteúdo.
    """
```

## Testes

- Unit em `tests/unit/`, integration em `tests/integration/`.
- Testes de integração marcados com `@pytest.mark.integration` ou via env var (`RUN_INTEGRATION=1`) — requerem stack subida (RabbitMQ, Qdrant, Ollama).
- Preferir `@pytest.mark.parametrize` a loops, fixtures a setup/teardown, `respx` para mockar HTTP, `pytest-asyncio` (já em modo `auto`) para async.
- Não mockar coisas baratas de rodar de verdade. RabbitMQ e Redis dão para subir em integration; Ollama você mocka via `respx` em unit.

## TDD onde dá valor real

O projeto **não é** TDD purista para tudo. A regra prática:

- **TDD canônico** para módulos isolados com lógica não-trivial: `chunking.py`, `cache.py`, `session.py`, `prompt_builder.py`, `reranker_client.py`, schemas.
- **Smoke test ponta-a-ponta** valida integrações (gateway → fila → worker → Ollama → Qdrant). Não tente unit-testar isso.
- **Chaos test** valida tolerância a falhas (kill worker, kill Ollama, sobrecarga). Roda como experimento, não como pytest.

Os planos de bloco (B1–B5) explicitam onde cada coisa cai.

## Pareamento (code-partner): granularidade dos TODOs

Boa parte das sessões roda no modo parceiro (skill `code-partner`, descrito em `docs/USO_DE_IA.md` §2.5): a IA entrega estrutura + a suíte de testes (o contrato executável); o integrante escreve o miolo das funções de produção.

A granularidade do scaffolding (TODOs comentados) **se adapta à experiência declarada pelo integrante**:

- **Se o integrante disser que não tem experiência** com aquela parte (ex: "não tenho experiência com isso", "é terreno novo pra mim"): os TODOs vêm no formato **detalhado e beginner-first** — cada passo diz *o que* fazer, *por quê*, *qual ferramenta/API* usar (`.read_text`, `.find`, `Template.render`, etc.) e marca explicitamente as **armadilhas** (ex: `str.find` devolvendo `-1`, mutação acidental de objeto compartilhado). Modelo de referência: os TODOs expandidos em `src/workers/query/prompt_builder.py`.
- **Caso contrário** (terreno familiar): TODOs concisos, um a duas linhas por passo, sem explicar APIs básicas.

Independente da granularidade, a fronteira do `code-partner` não muda: pseudocódigo/sinalização de API em comentário é permitido; escrever as expressões Python que *resolvem* o problema (o miolo) não é. Detalhar mais ≠ entregar a solução.

## Engenharia de contexto

- Prompts versionados em `prompts/` com frontmatter YAML (`version`, `model_target`, `last_changed`, `notes`). Não é código — é configuração que muda independente do código.
- Carregue prompts via `prompt_registry.load("system_qa_pt", version="latest")` (a criar em B1, Task 13). Suporta `version=specific` para reproduzir experimentos.
- Estratégia de chunking: recursive character splitter com fronteiras `\n\n` → `\n` → `. ` → espaço; target 800 tokens, overlap 120.
- Re-rank: top-20 vetorial → top-5 cross-encoder.
- Orçamento de tokens explícito no `build_prompt`: `num_ctx=8192` no Qwen, ~1500 reservados para system+resposta, ~6500 para chunks. Trunca caudas se ultrapassar.

## Observabilidade

- Métricas Prometheus em **todos** os componentes (`/metrics` no gateway/rerank-service via FastAPI; `aiohttp` standalone nos workers — `src/shared/workers_metrics_server.py` em B3).
- Logs JSON com campos obrigatórios: `ts`, `level`, `service`, `host`, `correlation_id`, `event`, `latency_ms`, `tokens_in`, `tokens_out`.
- Loki indexa por `service`, `host`, `correlation_id`. Para reconstituir um fluxo: `LogQL: {correlation_id="q-7af3..."}`.

## Tolerância a falhas

- Retry com `tenacity`: 3 tentativas, backoff exponencial com jitter, max 8s — em todo client HTTP externo.
- DLX RabbitMQ (`rag.dlx`) + filas `*.dlq`. 3 nacks → DLQ. Inspect/replay via `scripts/dlq_inspector.py`.
- Fallback no gateway: se workers travarem, retorna chunks brutos com `[degraded mode]` em vez de 504 vazio.

## Como adicionar uma nova dependência

1. `uv add <pkg>` (runtime) ou `uv add --dev <pkg>` (dev/test).
2. Mencione no commit/PR o que é e por que entrou.
3. Atualize a seção "Stack e principais dependências runtime" deste arquivo se for relevante.

## O que evitar

- Não introduza black, flake8, pylint, isort, autoflake — ruff cobre tudo.
- Não pin versões exatas em `pyproject.toml`; o `uv.lock` cuida da reprodutibilidade.
- Não commite `.venv/`, caches, `data/*.csv`, `.env*` (exceto `.env.example`), volumes Docker, `terraform.tfstate*` — todos no `.gitignore`.
- Não escreva em estado de módulo no import time. Prefira funções puras, ou classes que possuam o próprio estado.
- Não execute commits no projeto — o usuário (Davi) commita manualmente. Veja `~/.claude/projects/.../memory/feedback_no_commits.md`.
- Não execute comandos de teste, lint ou type-check (`uv run pytest`, `uv run ruff check/format`, `uv run mypy`) — quem roda é o desenvolvedor (Davi). Você **sugere o comando exato**; execução, leitura da saída e correção são dele. Inclui rodar "só pra confirmar". Mesma lógica do "não commitar". Veja `~/.claude/projects/.../memory/feedback_no_command_execution.md`.
- Não use AWS — o projeto é deliberadamente local. Mapeamentos: SQS→RabbitMQ, S3→volumes, DynamoDB→Redis/Qdrant, CloudWatch→Prometheus+Grafana+Loki.
- Em code review, **não aponte ajustes cosméticos** (whitespace sobrando, vírgula final faltando, ordem de imports, linha em branco extra, etc.) — o ruff cobre tudo isso quando Davi rodar `uv run ruff check --fix .` / `uv run ruff format .`. Foque em bugs reais, problemas de design, conexões com conceitos, e violações de convenção que o ruff/mypy não pegam.

## Notas específicas do projeto

- **Topologia distribuída em 3 PCs via Tailscale** — não é uma simulação. Os workers em PC2/PC3 falam com gateway/Qdrant/RabbitMQ/Ollama no PC1 via IPs Tailscale (100.x.y.z). Em dev/teste, Modo 1 (Compose) sobe tudo num só host com DNS interno do compose.
- **GPU é só do PC1** (autor). PC2/PC3 não rodam Ollama de fato; chamam o do PC1. Para dev local nesses PCs, use `llama3.2:1b` em CPU ou um stub HTTP determinístico.
- **Bônus +10 pts**: experimento Ollama vs vLLM no final (B4, Exp 3). Condicional ao cronograma — primeiro item da lista de cortes do spec.
- **Prazo apertado**: 16 dias corridos (09/05 → 25/05). Se atrasar, cortar nesta ordem: Exp 3 (vLLM) → Loki → Streamlit demo → memória de sessão → Terraform.
