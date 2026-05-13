# Relatório de aprendizagem — Davi Maciel Cavalcante

> **Status:** rascunho gerado a partir de evidências objetivas (commits, código escrito, conversas registradas com a IA assistente). Davi precisa revisar, ajustar a voz, podar o que não se aplica e adicionar o que ficou de fora antes da entrega.

- **Disciplina:** Engenharia de Contexto e Harness Engineering aplicada à Programação Distribuída e Paralela
- **Tema:** 5 — Sistema RAG distribuído em 3 PCs físicos via Tailscale
- **Período relatado:** 2026-05-09 a 2026-05-13 (Bloco B1 — setup e pipeline mínimo)
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
- **`src/gateway/main.py`** — entrypoint FastAPI com `lifespan` que conecta no RabbitMQ no startup, declara as 3 filas do projeto e armazena a conexão em `app.state.rabbitmq` para as rotas consumirem.
- **`src/gateway/routes.py`** — `APIRouter` com `/health` (liveness probe), `/ingest` (fire-and-forget publicando no RabbitMQ) e `/query` (RPC sobre AMQP com reply queue exclusiva e timeout de 120s).
- **`tests/integration/test_gateway_smoke.py`** — smoke do `/health` (skipável via `RUN_INTEGRATION=1`), validando que o app sobe e o lifespan completa sem explodir.
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

### 2.7 FastAPI: lifespan, `app.state` e o padrão "gateway"

Implementar o gateway (Task 8 do B1) consolidou três coisas que eu não tinha clareza antes:

- **`lifespan` com `@asynccontextmanager`** substitui os antigos `@app.on_event("startup")` / `@app.on_event("shutdown")`. A função tem um único `yield` no meio — tudo antes roda no startup, tudo depois roda no shutdown, e o `yield` é o "ponto onde o FastAPI toma controle e serve requests". Como o lifespan não devolve valor pro framework, a assinatura é `AsyncIterator[None]` e o `yield` vai sozinho, sem valor.
- **Definir vs usar context manager async** — duas operações diferentes que eu confundia. O decorator `@asynccontextmanager` apenas **transforma** uma função em fábrica de context manager; quem efetivamente dispara o ciclo de vida (entra → executa código pré-yield → entrega o valor → sai → executa código pós-yield) é o `async with`. Os dois precisam coexistir.
- **`app.state` como namespace compartilhado** — é uma instância de `types.SimpleNamespace` que vive na instância do app. Eu armazeno a conexão do RabbitMQ no startup (`app.state.rabbitmq = conn`) e qualquer rota acessa via `request.app.state.rabbitmq`. Isso evita global module-level, evita import circular entre `main.py` e `routes.py`, e funciona limpo em testes (basta sobrescrever o state no app de teste).

Um conceito de arquitetura também ficou concreto: **por que se chama "gateway"**. É o mesmo termo de redes (porta de entrada/saída entre dois domínios), aplicado em camada diferente. Aqui, o gateway é o **único ponto HTTP** do sistema — clientes externos só conhecem ele, e por baixo do capô ele traduz HTTP em mensagens RabbitMQ pros workers (que não expõem HTTP). Mesma família dos *payment gateways*, *email gateways* (SendGrid), *SMS gateways* (Twilio): adapters que escondem complexidade na fronteira do sistema.

Outro detalhe que quase me passou: **circular imports só acontecem quando `routes.py` importa de `main.py`**. Como uso `APIRouter` (objeto local em `routes.py`) e o `main.py` que faz `app.include_router(router)`, a direção dos imports é única (DAG limpa). É o padrão recomendado pelo próprio FastAPI exatamente por isso.

Já a sintaxe de **varargs** (`*names`) com asterisco também caiu na ficha: na **definição** da função (`def f(*names)`), o asterisco "junta" os args extras numa tupla; na **chamada** da função (`f(*lista)`), ele "espalha" o iterável em args separados. Mesmo símbolo, operações inversas. Travou em mim quando errei a chamada de `declare_queues` passando uma tupla onde o esperado eram args separados.

### 2.8 Implementação de `/ingest` e `/query`: pattern RPC sobre AMQP e cleanup aninhado

Na continuação da Task 8, parei com a skill `code-partner` ativada pra implementar o miolo dos dois endpoints. Foi a sessão onde mais errei e mais aprendi nesta semana — vários bugs entraram, foram revisados, e cada correção consolidou um conceito.

**Pattern RPC sobre AMQP.** HTTP é request/response síncrono; RabbitMQ é fire-and-forget assíncrono. Como o `/query` consegue **esperar** uma resposta numa fila? A solução foi clara depois que escrevi: o gateway abre um **channel novo** só pra declarar uma `reply_queue` com `exclusive=True, auto_delete=True`, publica a pergunta na fila normal incluindo `reply_to=reply_queue.name` no header AMQP, e fica iterando na reply_queue com `timeout=120`. O worker, do outro lado, lê o `reply_to` e publica a resposta exatamente nessa fila. O motivo do channel próprio também ficou concreto: a `reply_queue` exclusiva morre quando o channel fecha, então cada `/query` simultâneo tem isolamento total — não dá pra dois requests pegarem a resposta um do outro.

**`try/finally` aninhado.** Minha primeira tentativa enfiou `channel.close()` dentro do `async for`, e o `clear_correlation_id()` foi parar dentro de um `finally` que só rodava depois do `async with`. Resultado: se desse timeout, **nenhum dos dois rodava**. A IA me forçou a verbalizar o conceito: `finally` só dispara se o `try` correspondente foi **entrado**; exceção que sobe antes do `try` não aciona ele. A regra prática que ficou: cada `try` "guarda" o recurso criado logo antes dele, e cleanup acontece de dentro pra fora (channel primeiro, contextvar do log por último). Foi a primeira vez que `try/finally` deixou de ser receita e virou ferramenta de gerência de recursos.

**Análise de fluxo do mypy.** Depois que o código rodava na minha cabeça, o `mypy --strict` reclamou: "Missing return statement". Eu queria descartar como ruído, mas a análise era correta — o `async for` pode terminar sem iterar nenhuma vez, e nesse caminho a função saía sem `return` nem `raise`. A correção foi adicionar um `raise HTTPException(504)` **fora do `async with` e dentro do `try`**, cobrindo tanto o caso "aio-pika levantou TimeoutError" quanto o caso "loop esgotou silencioso". O ponto que ficou: type checker estático não é decorativo, é uma camada de prova que pega caminhos que o teste de runtime talvez nem exercite.

**`return` sai da função, não do bloco.** Em algum momento me confundi achando que o `raise` da rede de segurança ia disparar sempre que o `async with` terminasse, mesmo após `return`. Errado. `return` em Python sai da função inteira — ele não é como `break`. Os `finally` em torno rodam no caminho de saída, mas o código depois do `async with` (incluindo o `raise`) só é alcançado se o controle realmente chegar até lá. Conceito que eu sabia "no abstrato" mas confundi na prática quando os blocos aninhados ficaram densos.

**`asyncio.TimeoutError` foi unificado com `TimeoutError` builtin no Python 3.11.** A IA me orientou a `except asyncio.TimeoutError`, e o `ruff` reescreveu pra `except TimeoutError` (regra UP041) e removeu o `import asyncio` (F401). Fui investigar e aprendi: a partir do 3.11, `asyncio.TimeoutError is TimeoutError` (mesmo objeto). Antes eram classes separadas com hierarquias diferentes. Como o projeto pina `>=3.12`, a forma moderna é usar o builtin direto. Lição embolada: nem toda recomendação de IA é a forma mais idiomática — o `ruff` muitas vezes carrega regras de modernização mais atualizadas que o conhecimento "histórico" reproduzido em respostas.

**Bugs clássicos de async/concorrência.** Em ambos os endpoints esqueci o `await` no `publish_json`. Sem `await`, a coroutine é criada e descartada — a mensagem **nunca chega no broker**, mas o endpoint responde 200/202 alegremente. É um bug silencioso que só aparece quando você vai ver fila vazia. O `mypy --strict` pegou em uma das vezes (coroutine retornada e ignorada); na outra eu mesmo tive que perceber. Ficou claro por que o CLAUDE.md insiste em "async-first, sem mistura": código async sem `await` é uma armadilha onde o tipo da expressão é "promessa não cumprida".

**Detalhes de Python que pareciam triviais mas pegaram.** Três coisas pequenas: (1) `hashlib.sha256(s)` exige `bytes`, não `str` — precisa `.encode()` antes — e devolve um objeto `HASH`, não uma string — precisa `.hexdigest()` depois. (2) `b'req.filename'` é uma **literal de bytes** com o texto ASCII `req.filename`, **não** uma referência à variável; a interpolação só existe em f-strings. (3) Posição do slice em f-string: `f"i-{uuid.uuid4().hex}"[:8]` corta a string inteira (6 chars hex), enquanto `f"i-{uuid.uuid4().hex[:8]}"` corta antes da interpolação (8 chars hex). O ponto: micro-confusões com tipo (bytes vs str, literal vs expressão, ordem de operações) custam muito tempo se não forem identificadas cedo — type hints e revisão crítica ajudam, mas no fim é preciso conhecer a semântica fina das primitivas.

**Refactor por extração de variáveis.** A linha do `doc_id` ficou ilegível depois de empilhar `sha256 + encode + hexdigest + slice`. A IA não propôs a refatoração — eu pedi, e ela me ofereceu **opções de nome** (sem escrever a versão final). Quebrei em quatro linhas (`b64_prefix → fingerprint_source → sha256_hex → doc_id`), e a cadeia conta a história sozinha. Internalizou o princípio: legibilidade ≠ verbosidade. Variáveis intermediárias com nomes bons substituem comentário e documentam intenção.

---

## 3. Aprendizados de processo e metodologia

### 3.1 Spec antes de código

A disciplina insiste em **engenharia de contexto** e isso ficou concreto: antes de escrever uma linha de Python, passamos por brainstorming socrático que produziu uma spec densa (`docs/superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md`) e planos de bloco detalhados. Quando comecei a codar, eu sabia exatamente onde cada arquivo entrava no sistema maior. Em projetos anteriores, eu pulava direto pro código e descobria a arquitetura "no susto".

### 3.2 TDD onde dá valor real (não dogmático)

`tests/unit/test_ollama_client.py` cobre o cliente HTTP **antes** de eu integrar com o Ollama de verdade — é onde TDD brilha porque a lógica de retry/timeout é testável isoladamente com `respx`. Em contrapartida, não escrevi unit test pro `worker/main.py` (vai ser validado no smoke test ponta-a-ponta). Aprendi que TDD não é regra cega: é ferramenta que se aplica onde o custo de teste é menor que o custo de bug em produção.

Um refinamento que veio na Task 8: mesmo quando o módulo cai no bucket de **smoke test** (não TDD canônico), ainda vale escrever o teste **antes** da implementação. A IA tinha proposto começar pela implementação do `main.py`, mas perguntei "não seria primeiro os testes?" — ela recalibrou e escreveu o `test_gateway_smoke.py` antes. O teste falhou com `ImportError` (red esperado), e os símbolos que ele exigia (`from src.gateway.main import app`, status 200, payload `{"status": "ok"}`) viraram diretamente a checklist de o que `main.py` + `routes.py` precisavam expor. **O teste vira spec executável**, mesmo no escopo "smoke", e essa disciplina precisa ser lembrada inclusive quando a IA propõe pular.

### 3.3 Trabalhar com IA como parceiro, não como gerador

A skill `code-partner` foi adotada em parte das sessões justamente pra eu não terceirizar o aprendizado. A IA escreve estrutura (imports, assinaturas, esqueletos comentados); eu escrevo o miolo. Em momentos de pressa, eu *quis* só receber o código pronto — e a IA me lembrou (corretamente) que esse era exatamente o cenário que a skill existia pra evitar. A lição que fica: **mesmo IAs sofisticadas precisam de revisão crítica humana**. Confiança não pode virar automatismo.

### 3.4 Convenções como infraestrutura silenciosa

NumPy docstrings, type hints em todas as assinaturas, linha 100, `snake_case`, async-first sem mistura com I/O síncrono — escrever isso no `CLAUDE.md` desde o início significa que cada arquivo novo nasce no padrão. Aprendi que **convenção documentada vale mais que disciplina individual**: ninguém precisa lembrar das regras se elas estão escritas e o linter as enforce.

---

## 4. O que ainda quero aprender (em aberto pros próximos blocos)

- **B1 finalização**: Tasks 9–14 (chunking recursivo, parsing PDF, workers fim-a-fim, prompts versionados, smoke test, Makefile). Task 8 (gateway FastAPI completo) fechada.
- **B2**: cache distribuído (L1 in-memory, L2 Redis), reranker com cross-encoder bge-reranker-v2-m3, observabilidade Prometheus + Grafana.
- **B3**: o pulo do gato deste projeto — passar de Modo 1 (Compose num host) pra Modo 2 (3 PCs reais via Tailscale). Aqui vou aprender de verdade sobre rede entre hosts, IaC com Terraform/Ansible, e tolerância a falhas em ambiente distribuído real (não simulado).
- **B4**: experimentos quantitativos (latência, throughput, tolerância a falhas) e — se o cronograma permitir — comparação Ollama vs vLLM (bônus +10).
- **B5**: documento técnico final, slides, apresentação.

---

## 5. Conclusão

Em 4 dias trabalhando no Bloco B1, saí de "sei o que é um sistema RAG no abstrato" pra ter os tijolos da fundação no código, com tooling Python moderno, observabilidade desenhada desde o início e infraestrutura Docker preparada pra escalar pra 3 hosts. Mais importante que os artefatos individuais foi internalizar uma forma de trabalhar: **spec antes de código, convenção antes de disciplina, IA como parceiro crítico em vez de gerador opaco**.

Os próximos blocos vão me forçar a sair da zona de conforto do "tudo num host" pra lidar com rede física, particionamento de carga e falhas reais — que é onde a disciplina de Programação Distribuída e Paralela realmente vai cobrar o que eu aprendi.
