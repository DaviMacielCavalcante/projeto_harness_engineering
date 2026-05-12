# Relatório de aprendizagem — Davi Maciel Cavalcante

> **Status:** rascunho gerado a partir de evidências objetivas (commits, código escrito, conversas registradas com a IA assistente). Davi precisa revisar, ajustar a voz, podar o que não se aplica e adicionar o que ficou de fora antes da entrega.

- **Disciplina:** Engenharia de Contexto e Harness Engineering aplicada à Programação Distribuída e Paralela
- **Tema:** 5 — Sistema RAG distribuído em 3 PCs físicos via Tailscale
- **Período relatado:** 2026-05-09 a 2026-05-12 (Bloco B1 — setup e pipeline mínimo)
- **Instituição:** CESUPA, 2º bimestre de 2026

---

## 1. O que eu contribuí até este ponto

Durante o Bloco B1, fui responsável pela base do projeto — toda a fundação que os blocos seguintes (B2 a B5) vão consumir. Concretamente, escrevi:

- **Scaffold do projeto Python** com `uv` (Python 3.12), `ruff` em modo strict e `mypy --strict` configurados em `pyproject.toml`.
- **`src/shared/config.py`** — configuração tipada via `pydantic-settings`, lendo env vars de `.env.local`.
- **`src/shared/logging.py`** — logging estruturado em JSON com `structlog`, com `bind_correlation_id`/`clear_correlation_id` para rastrear fluxos entre serviços.
- **`src/shared/schemas.py`** — schemas Pydantic compartilhados entre gateway e workers (`IngestRequest`, `QueryRequest`, mensagens de fila).
- **`src/shared/ollama_client.py`** — cliente HTTP assíncrono para o Ollama, usando `httpx.AsyncClient` e retry exponencial via `tenacity`.
- **`src/shared/messaging.py`** — helpers `aio-pika` para conectar ao RabbitMQ, declarar exchanges/filas, publicar e consumir mensagens.
- **Testes unitários** em `tests/unit/` para `config`, `schemas` e `ollama_client` (com `respx` mockando HTTP).
- **Dockerfiles** para `gateway` e `worker` em `infra/docker/`.
- **`docker-compose.yml`** com profiles (`all`, `server`, `worker`) preparando a transição do Modo 1 (single-host) para o Modo 2 (3 PCs reais).
- **`TODO.md`** organizando as tarefas dos blocos B1–B5.

Além disso, contribuí com revisões iterativas: endurecer `mypy strict` em todo `shared/` (eliminar `no-any-return`), ajustar o compose após discussão sobre a sintaxe mais enxuta de `networks:`, e pinar versões das imagens Docker em vez de usar `latest`.

---

## 2. Aprendizados técnicos

### 2.1 Tooling Python moderno (`uv` + `ruff` + `mypy strict`)

Foi minha primeira vez usando `uv` como gerenciador de dependências. Antes, eu vinha de `pip` + `venv` puro. O que mudou na minha cabeça:

- O lockfile (`uv.lock`) substitui o ritual manual de `pip freeze > requirements.txt`. Reprodutibilidade vira default, não esforço extra.
- Comandos `uv add <pkg>` / `uv remove <pkg>` mantêm `pyproject.toml` e o lockfile em sincronia automaticamente — eu não edito o `pyproject.toml` à mão pra deps.
- `uv run <cmd>` resolve o ambiente virtual sem precisar `activate`.

`ruff` cobrindo lint **e** format consolidou o que antes seriam 3-4 ferramentas (black, isort, flake8, autoflake). Aprendi na prática que essa centralização reduz fricção real.

`mypy --strict` foi o mais educativo. No commit `66dcdf1` ("harden mypy strict"), tive que voltar e tipar coisas que tinham passado batido — em especial retornos de funções que o mypy inferia como `Any` (regra `no-any-return`). Aprendi que **type hint não é decoração**: ele força a explicitar o contrato de cada função, e os bugs aparecem antes do runtime.

### 2.2 Configuração tipada com `pydantic-settings`

Vinha do mundo onde config era um dicionário lido de um YAML, sem validação. Mudar pra `BaseSettings` me forçou a perceber que:

- Cada variável de ambiente vira um campo tipado, com default e validação no momento do carregamento. Se a env var está malformada, a aplicação **não sobe** — em vez de quebrar 10 minutos depois com um `KeyError` enigmático.
- Separar `.env.example` (versionado, sem segredos) de `.env.local` (gitignored, com segredos) é uma prática simples que evita commits acidentais de credenciais.

### 2.3 Logging estruturado e correlation ID

Antes, meus logs eram strings concatenadas com `f""`. Implementar `structlog` me mostrou outro paradigma:

- Logs são **eventos estruturados** (JSON), não texto. Cada linha tem campos consistentes (`ts`, `level`, `service`, `correlation_id`, etc.) que o Loki vai indexar depois.
- O `correlation_id` propagado via `contextvars` permite reconstituir o caminho de uma requisição que atravessou gateway → fila → worker → Ollama. Sem isso, debugar um sistema distribuído é tentar montar um quebra-cabeça com peças anônimas.

### 2.4 Cliente HTTP assíncrono resiliente (`httpx` + `tenacity`)

Implementar `ollama_client.py` consolidou três conceitos que eu sabia separadamente, mas nunca tinha juntado:

- **Async-first**: usar `httpx.AsyncClient` em vez de `requests` porque dentro de uma coroutine não pode ter chamada bloqueante. Misturar quebra o event loop.
- **Retry com backoff exponencial**: o decorator `@retry` do `tenacity` evita escrever loops manuais com `time.sleep` ou `asyncio.sleep`. Configurei 3 tentativas com jitter e teto de 8 segundos — o suficiente pra absorver soluços de rede sem prender uma requisição por minutos.
- **Mockar HTTP em teste**: `respx` interceptando as chamadas do `httpx` permitiu testar o cliente **sem subir o Ollama de verdade**, validando inclusive o comportamento de retry (resposta 500 nas 2 primeiras chamadas, 200 na terceira).

### 2.5 Mensageria com `aio-pika` (RabbitMQ)

Foi minha primeira vez escrevendo código de mensageria. Aprendi a separar mentalmente:

- **Conexão** vs **canal** vs **exchange** vs **fila** — cada um tem ciclo de vida e propósito diferente.
- **`durable=True`** nas filas e **`delivery_mode=PERSISTENT`** nas mensagens garantem que tudo sobrevive a reinício do RabbitMQ — mas custa I/O. Decisão consciente, não default cego.
- Padrão `connect → declare → publish/consume` se repete entre gateway e workers, então virou helper único em `messaging.py` em vez de duplicar.
- O conceito de **DLX** (dead letter exchange) como rede de segurança pra mensagens que falham N vezes — ainda vou implementar de verdade no B3, mas o helper já está preparado pra apontar pra `rag.dlx`.

### 2.6 Docker e Docker Compose em profundidade

A Task 7 (Docker Compose Modo 1) foi onde mais aprendi conceitos novos numa sessão única:

- **YAML anchors (`x-worker-base: &worker-base` + `<<: *worker-base`)** pra eliminar duplicação entre `ingest-worker` e `query-worker`. Antes, eu copiaria o bloco inteiro duas vezes.
- **Profiles** (`all`, `server`, `worker`) preparando o mesmo `docker-compose.yml` pra rodar em modos diferentes — single-host em dev, distribuído entre 3 PCs em produção.
- **`depends_on` com `condition: service_healthy`** vs `service_started` — entender que "container subiu" e "serviço pronto pra receber tráfego" são coisas diferentes. RabbitMQ tem healthcheck (`rabbitmq-diagnostics ping`) por isso; Qdrant não precisa porque sobe rápido.

---

## 3. Aprendizados de processo e metodologia

### 3.1 Spec antes de código

A disciplina insiste em **engenharia de contexto** e isso ficou concreto: antes de escrever uma linha de Python, passamos por brainstorming socrático que produziu uma spec densa (`docs/superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md`) e planos de bloco detalhados. Quando comecei a codar, eu sabia exatamente onde cada arquivo entrava no sistema maior. Em projetos anteriores, eu pulava direto pro código e descobria a arquitetura "no susto".

### 3.2 TDD onde dá valor real (não dogmático)

`tests/unit/test_ollama_client.py` cobre o cliente HTTP **antes** de eu integrar com o Ollama de verdade — é onde TDD brilha porque a lógica de retry/timeout é testável isoladamente com `respx`. Em contrapartida, não escrevi unit test pro `worker/main.py` (vai ser validado no smoke test ponta-a-ponta). Aprendi que TDD não é regra cega: é ferramenta que se aplica onde o custo de teste é menor que o custo de bug em produção.

### 3.3 Trabalhar com IA como parceiro, não como gerador

A skill `code-partner` foi adotada em parte das sessões justamente pra eu não terceirizar o aprendizado. A IA escreve estrutura (imports, assinaturas, esqueletos comentados); eu escrevo o miolo. Em momentos de pressa, eu *quis* só receber o código pronto — e a IA me lembrou (corretamente) que esse era exatamente o cenário que a skill existia pra evitar. A lição que fica: **mesmo IAs sofisticadas precisam de revisão crítica humana**. Confiança não pode virar automatismo.

### 3.4 Convenções como infraestrutura silenciosa

NumPy docstrings, type hints em todas as assinaturas, linha 100, `snake_case`, async-first sem mistura com I/O síncrono — escrever isso no `CLAUDE.md` desde o início significa que cada arquivo novo nasce no padrão. Aprendi que **convenção documentada vale mais que disciplina individual**: ninguém precisa lembrar das regras se elas estão escritas e o linter as enforce.

---

## 4. O que ainda quero aprender (em aberto pros próximos blocos)

- **B1 finalização**: Tasks 8–14 (gateway FastAPI, chunking recursivo, parsing PDF, workers fim-a-fim, prompts versionados, smoke test, Makefile).
- **B2**: cache distribuído (L1 in-memory, L2 Redis), reranker com cross-encoder bge-reranker-v2-m3, observabilidade Prometheus + Grafana.
- **B3**: o pulo do gato deste projeto — passar de Modo 1 (Compose num host) pra Modo 2 (3 PCs reais via Tailscale). Aqui vou aprender de verdade sobre rede entre hosts, IaC com Terraform/Ansible, e tolerância a falhas em ambiente distribuído real (não simulado).
- **B4**: experimentos quantitativos (latência, throughput, tolerância a falhas) e — se o cronograma permitir — comparação Ollama vs vLLM (bônus +10).
- **B5**: documento técnico final, slides, apresentação.

---

## 5. Conclusão

Em 4 dias trabalhando no Bloco B1, saí de "sei o que é um sistema RAG no abstrato" pra ter os tijolos da fundação no código, com tooling Python moderno, observabilidade desenhada desde o início e infraestrutura Docker preparada pra escalar pra 3 hosts. Mais importante que os artefatos individuais foi internalizar uma forma de trabalhar: **spec antes de código, convenção antes de disciplina, IA como parceiro crítico em vez de gerador opaco**.

Os próximos blocos vão me forçar a sair da zona de conforto do "tudo num host" pra lidar com rede física, particionamento de carga e falhas reais — que é onde a disciplina de Programação Distribuída e Paralela realmente vai cobrar o que eu aprendi.
