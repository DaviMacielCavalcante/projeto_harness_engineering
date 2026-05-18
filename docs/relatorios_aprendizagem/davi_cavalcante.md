# Relatório de aprendizagem — Davi Maciel Cavalcante

> **Status:** rascunho gerado a partir de evidências objetivas (commits, código escrito, conversas registradas com a IA assistente). Davi precisa revisar, ajustar a voz, podar o que não se aplica e adicionar o que ficou de fora antes da entrega.

- **Disciplina:** Engenharia de Contexto e Harness Engineering aplicada à Programação Distribuída e Paralela
- **Tema:** 5 — Sistema RAG distribuído em 3 PCs físicos via Tailscale
- **Período relatado:** 2026-05-09 a 2026-05-17 (Bloco B1 — setup e pipeline mínimo)
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
- **`src/workers/ingest/chunking.py`** — recursive splitter completo: `count_tokens_approx` (aproximação 1 token ≈ 4 chars, com `max(1, ...)` pra evitar zero), `_split_with_separators` (recursão sobre lista de separadores, anexando o separador de volta pra que a reconstituição via `"".join(parts)` seja lossless) e `chunk_text` (acumulação em buffer + corte hard por caractere para peças maiores que o alvo + prepend de overlap entre chunks adjacentes).
- **`tests/unit/test_chunking.py`** — testes-spec do splitter (5 casos cobrindo atalho, fronteira de parágrafo, overlap, e limite de tolerância de 25% sobre o alvo).
- **`src/workers/query/prompt_builder.py`** — escrevi o miolo de `_load` (lê o prompt versionado e remove o frontmatter YAML) e `build_prompt` (seleciona o system prompt por idioma, renderiza o template Jinja do usuário e trunca os blocos de contexto pela cauda dentro de um orçamento de caracteres). Atribuição honesta: nesta sessão, pelo modelo da §2.5 do `USO_DE_IA.md`, os testes (`tests/unit/test_prompt_builder.py`) e os 3 arquivos de prompt vieram da IA como contrato executável/configuração; o **código de produção foi meu**.
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

### 2.9 Estratégia de chunking no RAG: granularidade e overlap

Antes da Task 9 eu sabia que "chunking divide o texto", mas não tinha claro **por que dividir** nem **por que esses parâmetros específicos** (target 800 tokens, overlap 120). Conversando sobre o desenho da função, dois motivos práticos viraram concretos:

**Granularidade do retrieval.** Se eu indexasse um PDF inteiro como um vetor só no Qdrant, a busca semântica conseguiria me dizer "esse documento é relevante", mas não **qual trecho**. O LLM receberia o documento inteiro no contexto — polui a janela, consome tokens caros, e a resposta vira genérica. Com chunks de ~800 tokens, o retrieval traz **o parágrafo certo** pra responder a pergunta. A diferença entre "este livro fala sobre X" e "este parágrafo responde X" é a diferença entre um sistema RAG ruim e um bom.

**Qualidade do embedding.** Embeddings tipo `nomic-embed-text` aceitam até 8k tokens, mas o que aprendi é que **aceitar não é o mesmo que representar bem**. O vetor 768d gerado tenta resumir o conteúdo todo numa só direção do espaço — quanto maior o texto, mais o vetor representa "a média" e perde detalhes específicos. Chunks menores produzem vetores mais "afiados", semanticamente focados, que casam melhor com perguntas específicas.

**Por que o splitter é "recursive character" e não um split simples.** A estratégia tenta quebrar primeiro em **fronteiras semânticas** (parágrafo `\n\n` → linha `\n` → frase `. ` → palavra ` `) e só cai pra corte arbitrário por caractere se nenhuma das fronteiras anteriores estiver disponível. A intuição: quebrar no meio de uma frase mutila o significado; entre parágrafos preserva a coerência. A recursão é o mecanismo que tenta o "menos invasivo" primeiro.

**Por que o overlap existe.** Sem overlap, uma frase importante que cai exatamente na fronteira entre dois chunks é cortada — **nenhum** dos dois chunks fica com a frase inteira, e o retrieval pode perder o conteúdo relevante. Com ~15% de overlap (120 tokens dos 800), o final do chunk anterior aparece no começo do próximo, garantindo que ao menos um deles contenha a frase contígua. É uma redundância barata que paga em recall.

**Por que a função tem parâmetros e não constantes.** `chunk_text` recebe `target_tokens` e `overlap_tokens` em vez de hardcodar 800/120. Em B4, parte dos experimentos quantitativos vai variar esses números (400 vs 800 vs 1200) e medir impacto no recall do retrieval. Manter a função parametrizada é o que vai permitir rodar o experimento mudando só o call site, sem tocar na lógica. Aprendi a olhar API design não só pelo "o que o caller quer agora" mas pelo "o que o experimento futuro vai precisar".

Esse foi o primeiro momento em que entendi o chunking não como detalhe técnico, mas como **decisão de produto**: a estratégia define se o RAG vai trazer parágrafos cirúrgicos ou documentos atacadistas, se vai ter redundância suficiente nas fronteiras, e se vai ser experimentável depois. Tudo isso antes de uma linha de implementação.

### 2.10 Implementação dos primeiros helpers do splitter: `count_tokens_approx` e `_split_with_separators`

Comecei a Task 9 pela base do recursive splitter, antes do `chunk_text` propriamente dito. Duas funções pequenas, mas cada uma trouxe um conceito que ficou.

**`count_tokens_approx` — heurística 1:4 e o `max(1, ...)`.** O projeto evita puxar `tiktoken` nesta fase e usa a aproximação "1 token ≈ 4 caracteres". É bruta, mas suficiente pra dimensionar chunks no B1; se precisar de precisão em B2, troca-se só a função. O detalhe que me fez parar foi o `return max(1, tokens)`: pra string vazia, `len("") // 4 == 0`, e zero token causa divisão por zero em cálculos downstream (proporções, médias). Forçar um piso de 1 é uma daquelas decisões defensivas que parecem bobas mas evitam crash num caso de borda real.

**`_split_with_separators` — recursão como cascata de fallback.** Aqui ficou concreto o "recursive" do "recursive character splitter": a função tenta o separador mais semântico primeiro (`\n\n`); se não está presente no texto, **recursivamente** chama a si mesma com a lista encurtada (`separators[1:]`), tentando o próximo. A recursão é o jeito natural de modelar "tentei A, falhou, agora tento B, falhou, agora C..." sem escrever um if/elif em cascata gigante. Pra cada novo separador adicionado no futuro, basta colocar na lista — a lógica não muda.

**O sentinela `""` como caso-base.** A lista `_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]` termina com string vazia. Mas `text.split("")` levanta `ValueError` em Python, então a função tem um ramo especial: se o separador é o vazio, devolve `[text]` inteiro — a peça sai intacta, e o corte hard por caractere fica pro `chunk_text` resolver depois. Esse padrão "**valor sentinela no fim da lista garante terminação da recursão**" foi a primeira vez que vi recursão num contexto utilitário (não algoritmo de árvore/grafo). Sem o `""` no fim, eu precisaria de uma segunda condição de parada — o sentinela elimina o caso especial.

**Split lossless: anexar o separador de volta.** `text.split(sep)` consome o separador e o **descarta**. Se eu usasse o resultado direto, perderia os `\n\n` originais e a reconstituição via `"".join(parts)` daria um texto diferente do original. Pra preservar a invariante "join devolve o texto inteiro", anexo o separador no fim de cada peça exceto a última (a última não tem separador depois dela no texto). O princípio que ficou: ao decompor uma estrutura pra processar peça a peça, **manter as fronteiras anexadas é o que torna a operação reversível**. Vejo isso agora em parsers, tokenizers, e diff/patch — qualquer transformação que precise ser desfeita.

**Tipagem do retorno vazio.** Mypy strict me obrigou a pensar no caso `text == ""`: a função retorna `list[str]`, então tenho que devolver explicitamente `[]`, não `None`. Pareceu trivial, mas é exatamente o tipo de contrato que o type checker enforce automaticamente e me poupa de quebrar quem consome a função esperando iterável.

### 2.11 Fechando `chunk_text`: prepend, escopo e o teste como spec falível

A última parte da Task 9 foi montar o miolo do `chunk_text`: acumular peças num buffer até estourar o alvo, fechar como chunk, e no fim aplicar overlap entre chunks adjacentes. A primeira versão tinha bugs em quase todas as linhas da fase de overlap; a sessão de revisão virou um desfile de erros pequenos que ensinaram coisas grandes.

**Prepend ≠ append em strings.** Eu escrevi `chunks[i] += text_tail`, achando que estava colando a cauda **antes** do chunk. Mas `x += y` é `x = x + y` — cola **depois**. A IA me forçou a verbalizar a diferença: em prepend, a ordem da concatenação é `cauda + atual`; em append, `atual + cauda`. Mesmo operador, mesma sintaxe, ordem inversa. O efeito visível é que o teste que checava o "começo lógico" do chunk dava certo no append por acidente, mas semanticamente o overlap não estava preservando contexto coisa nenhuma — estava poluindo o final.

**Sobrescrever a variável de iteração com seu próprio valor derivado.** Numa primeira tentativa eu escrevi `overlap_chars = chunks[i-1][-overlap_chars]`, com dois bugs aninhados: (1) reatribui a variável `overlap_chars` (que era um `int` contador) com o resultado da expressão da direita, então na próxima volta do loop o "contador" não existe mais — virou string; (2) `s[-n]` (sem `:`) retorna **um único caractere**, não uma fatia. Pra pegar substring são `s[-n:]` (slice). Aprendi a olhar com mais cuidado pra qualquer linha onde o nome da variável aparece dos **dois lados** de uma atribuição, e a tratar slice vs indexação simples como operações categoricamente diferentes (uma devolve sequência, a outra devolve elemento).

**Mutação de lista durante iteração — risco de cascata.** A versão "quase certa" usava `chunks[i] = text_tail + chunks[i]` — modificava a lista original enquanto o loop ainda lia dela. Nos tamanhos dos testes não dava problema visível, mas a IA apontou que era armadilha latente: na próxima iteração, `chunks[i-1]` é o chunk **já modificado**, e a cauda extraída dele inclui parte da cauda anterior — se um chunk for menor que `overlap_chars`, o overlap começa a "cascatear" conteúdo de chunks distantes. O conserto idiomático foi não tocar em `chunks` durante o loop: construir uma string nova localmente (`text_tail + chunks[i]`) e dar `append` numa lista acumuladora separada (`with_overlap`). Princípio que ficou: **separar leitura de escrita** quando se itera sobre uma estrutura mutável.

**Escopo de variáveis dentro de `if` em Python.** Depois de tudo certo, eu escrevi `return with_overlap` no fim da função, mas `with_overlap` só é criada **dentro** do `if overlap_chars > 0 and len(chunks) > 1`. Se cair no caso falso (overlap zerado ou só um chunk), `with_overlap` nunca foi atribuída e o `return` dispara `UnboundLocalError`. Os 4 testes não pegavam — todos ou caíam no atalho do `if` inicial, ou geravam múltiplos chunks. Mas era bug latente. A correção idiomática foi a "Opção A": atribuir `chunks = with_overlap` **dentro** do `if` (depois do loop), e o `return chunks` fora — assim a variável `with_overlap` vive no escopo onde faz sentido, e o `return` final usa uma variável que sempre existe. Aprendi que Python não tem escopo de bloco como C/Java: variáveis criadas em `if`/`for`/`while` "vazam" pro escopo da função, mas só **se a linha foi executada** — referenciar antes da criação é o que dispara o `UnboundLocalError`.

**O teste como spec — quando o teste é que está errado.** O caso mais conceitualmente interessante: depois que tudo passou no type-check e na revisão lógica, rodei os testes e um falhou — `test_chunk_text_breaks_on_paragraph_boundary`. O teste verificava que `c.lstrip()[0]` de cada chunk continha as letras `a`, `b`, `c`, esperando que cada parágrafo virasse início de um chunk. Mas com prepend de overlap, o chunk 1 começava com a cauda do chunk 0 (que era `"...aaaa\n\n"`), então `lstrip()[0]` continuava sendo `'a'`, não `'b'`. A pergunta ficou desconfortável: **bug na implementação ou no teste?**

A IA me ajudou a articular as duas leituras: (1) implementação tá certa, teste é frouxo demais; (2) teste tá certo, implementação devia "limpar" a cauda nas fronteiras semânticas. A resposta veio de fora do código: a literatura padrão (LangChain, LlamaIndex) e a própria docstring do `chunk_text` definem overlap como "prepend dos últimos N chars do anterior, sem exceção". Limpar a cauda em fronteira de parágrafo seria comportamento custom não documentado. O teste foi escrito com expectativa ingênua de quem ainda não tinha entendido como o overlap funciona na prática.

A correção foi reescrever o teste pra verificar a **intenção real** — que cada bloco `"a" * 1000`, `"b" * 1000`, `"c" * 1000` aparece **íntegro** dentro de algum chunk (substring). Se a função tivesse partido um parágrafo no meio, nenhum chunk teria os 1000 chars contínuos. A métrica mudou de "primeira letra após lstrip" (frágil, dependente do prepend) pra "substring presente em algum chunk" (robusta, mede o que realmente importa: fronteira respeitada).

A lição que ficou: **teste é spec executável, e spec pode ter erro**. Quando teste e implementação discordam, nem sempre o teste é a verdade — às vezes a métrica do teste foi mal escolhida pra capturar a intenção. A pergunta certa não é "como faço o teste passar?", é "qual comportamento eu quero?". Se o comportamento atual é o correto pelo design canônico, o teste é que precisa se ajustar — e o ajuste melhora o teste, porque a nova métrica é menos frágil.

### 2.12 Worker de ingestão fim-a-fim: idempotência, closures e a armadilha da coroutine

A Task 11 amarrou tudo do B1 num pipeline só dentro de um handler: `parse_document` (Task 10 — base64 → lista de páginas `(page, texto)`) → detecção de idioma → `chunk_text` → embed no Ollama → upsert no Qdrant. Foi a sessão que mais consolidou conceitos de async e de sistemas distribuídos — e, de novo, onde mais bugs entraram e foram revisados antes de fechar.

**`await` em função síncrona.** Minha primeira versão tinha `await bind_correlation_id(...)` e `await parse_document(...)`. As duas são `def` normais — `await` num retorno `None`/lista quebra em runtime (`object ... can't be used in 'await' expression`). O conceito que ficou: `await` não é "marcador de chamada importante", é operador que só se aplica a awaitables. Colar `await` por reflexo em tudo que parece I/O é antipadrão — a regra é olhar a assinatura: só `async def` recebe `await`.

**Lista de tuplas → string: desempacotamento + join, e a ordem importa.** Pra detectar idioma eu precisava de uma amostra de texto, mas `parse_document` devolve `list[tuple[int|None, str]]`. Tentei `parsed_doc[:500]` — isso fatia a *lista de páginas* (500 páginas), não 500 chars. Aprendi a colapsar com `" ".join(text for _, text in parsed_doc)` (desempacotando a tupla no generator, ignorando o page_num com `_`) e só **depois** fatiar `[:500]`. Junta primeiro, corta no fim — cortar antes de juntar mede a coisa errada.

**`model_config` é atributo reservado do Pydantic.** Bug sutil que custaria tempo: escrevi `ollama.embed(model=settings.model_config)`. `model_config` *existe* em todo `BaseSettings` — é a config interna da classe (env_prefix etc.), não um campo meu. O mypy nem reclama porque o atributo de fato existe; só explodiria no Ollama com um modelo inválido. Lição: prefixo `model_` no Pydantic é zona de colisão com internos; o campo certo era `settings.embedding_model`.

**Id estável = idempotência = tolerância a falhas.** O conceito que mais me marcou. O id de cada ponto no Qdrant vem de `sha256(f"{doc_id}:{chunk_index}")` convertido pra int. Eu via como "gerar um id qualquer", mas a IA me fez conectar: id derivado deterministicamente do conteúdo torna o `upsert` **idempotente** — reenviar o mesmo documento (retry, replay de DLQ no B3, colega reprocessando) sobrescreve os mesmos pontos em vez de duplicar o corpus. Id aleatório quebraria essa garantia silenciosamente. Foi a primeira vez que "content-addressable" deixou de ser jargão e virou propriedade de projeto que consigo justificar no doc técnico. O `% (2**63 - 1)` é só espremer o hash gigante pro range de id que o Qdrant aceita.

**`PointStruct`: id + vector + payload.** Entendi o modelo de dados do Qdrant: cada "ponto" é o id (chave única, sobrescreve no upsert), o vector (os 768 floats que o embed devolve — é por ele que a busca por similaridade roda) e o payload (metadados que voltam no resultado: doc_id, texto do chunk, página, idioma). A busca acontece no vetor; o payload é o que me deixa montar a citação depois.

**Closure como injeção de dependência manual.** O `consume_forever` chama o handler como `handler(msg, payload)`, mas meu `handle_document` é `(payload, ollama, qdrant)` — não recebe `msg` e precisa dos clientes. Minha primeira tentativa foi *chamar* `handle_document(qdrant=..., ollama=...)` e passar o resultado como `handler` — dois erros: (1) `f()` chama agora e passa o retorno; `handler=` quer a *função* pra ser chamada depois (conceito `f` vs `f()`, callback clássico); (2) faltava `payload`, que nem existe no escopo do `main` — ele só nasce quando chega uma mensagem. A solução foi o **closure**: uma `async def handler(msg, payload)` interna que ignora `msg`, captura `ollama`/`qdrant` do escopo do `main` e adia a chamada de `handle_document` até a mensagem chegar. Isso é dependency injection na unha — clientes de vida longa criados uma vez no `main` e "injetados" via captura de escopo, em vez de abrir conexão por mensagem.

**Criar coroutine ≠ executar coroutine (de novo, e pior).** Já tinha apanhado disso nos endpoints do gateway (esquecer `await` no `publish_json`) e reincidi: escrevi `return handle_document(...)` dentro do closure, sem `await`. A cadeia de efeito é traiçoeira: o `consume_forever` faz `async with msg.process()`, o handler retorna a coroutine **sem rodar**, o bloco fecha sem exceção → a mensagem é **ack'd** → o RabbitMQ acha que processou → o documento nunca foi indexado. Ingestão "funciona" sem erro e o Qdrant fica vazio. Python só sussurra um `RuntimeWarning: coroutine was never awaited`. É o pior tipo de bug: silencioso, com perda de dados, e o sinal de erro fácil de ignorar. Internalizei a heurística: chamada `async` sem `await` (e que não vai pra `gather`/`create_task`) é sempre suspeita — o "tipo" daquela expressão é uma promessa não cumprida.

A lição transversal da Task 11: a glue de IO de um sistema distribuído é onde os conceitos de async (await, coroutine, closure, escopo) e os de tolerância a falhas (idempotência, semântica do ack) param de ser teoria e viram a diferença entre "pipeline funciona" e "pipeline finge que funciona".

### 2.13 `prompt_builder`: engenharia de contexto na prática e a semântica fina das strings

A Task 13 começou pelo `prompt_builder` — o módulo que monta o prompt final enviado ao modelo de geração. Foi a primeira vez que "engenharia de contexto", o nome da disciplina, deixou de ser título e virou código que eu escrevi.

**Por que esse módulo existe (o "A" de RAG).** O Qwen nunca viu o nosso corpus — ele foi treinado em dado genérico, não nos PDFs que o worker de ingestão indexou. Se eu perguntar direto, ele alucina. RAG resolve recuperando os chunks relevantes e **colando no prompt**: o `prompt_builder` é a etapa de *Augmentation*, a ponte entre o retrieval (Qdrant) e a geração (Ollama). O que ficou concreto: **o prompt é o único canal** — tudo que o modelo sabe sobre aquela query é o que está ali. Por isso são dois arquivos com papéis distintos: o *system* (`system_qa_pt.md`) é a **política** (responder só pelo contexto, dizer "não encontrei" se não cobrir — o freio anti-alucinação —, formato de citação `[source: ...]`); o *user template* (`user_qa_template.md`) é o **payload** Jinja dinâmico com os chunks etiquetados e a pergunta. A etiqueta de fonte em cada bloco não é decoração: é o que **viabiliza a citação**, requisito do marco luz-verde do B1.

**Orçamento de chars como proxy de tokens.** O Qwen tem janela finita (`num_ctx=8192`). Se o prompt estoura, o runtime corta silenciosamente — e geralmente corta o fim, que pode ser a própria pergunta. Por isso `build_prompt` corta de propósito, e corta a **cauda** (o retrieval entrega rankeado por similaridade, então a cauda é o menos relevante). Aprendi que o `max_chars` é um *proxy* grosseiro de tokens (~4 chars/token), aceitável no B1, refinável com tokenizer real se um experimento do B4 mostrar que precisa. A decisão de *quem* sacrificar é minha, explícita — não do runtime, às cegas.

**`str.lstrip(chars)` opera sobre um conjunto de caracteres, não sobre um prefixo.** O erro mais instrutivo: troquei `.lstrip("\n")` (certo) por `.lstrip("---")` achando que removia a string `"---"`. Não: o argumento vira o **conjunto** `{'-'}`, e `.lstrip("---")` é idêntico a `.lstrip("-")`. Pra remover prefixo existe `str.removeprefix`. Pior que o lint: se um prompt um dia começasse com um bullet markdown (`- item`), `.lstrip("-")` comeria o conteúdo. Errado-pro-objetivo **e** destrutivo.

**`str.find` devolve `-1` quando não acha.** Se eu fatiar usando esse `-1` sem checar (`raw[(-1)+3:]` vira `raw[2:]`), decapito os 2 primeiros chars do arquivo silenciosamente. Tratar o `-1` explicitamente não é paranoia — é a diferença entre "sem frontmatter, devolve tudo" e "devolve lixo".

**Diretório não é arquivo; e o parâmetro que evaporou.** Escrevi `_PROMPTS_DIR.read_text()` — mas `_PROMPTS_DIR` é a **pasta**, e `.read_text()` numa pasta levanta `IsADirectoryError`. Pior: o parâmetro `name` (qual prompt carregar) tinha sumido da linha. O certo era `(_PROMPTS_DIR / name).read_text(...)`. Lição: quando uma função recebe um parâmetro e ele não aparece no corpo, é red flag.

**Ordem dos campos numa dataclass: posicional e nomeado colidem.** `ContextBlock(block.text[:n], source=..., page=...)` — o 1º argumento é **posicional**, então casa com o **primeiro campo declarado** (`source`), e aí `source=...` repete → `TypeError: got multiple values for argument 'source'`. Eu queria que o posicional fosse `text` (3º campo). Aprendi a passar tudo nomeado quando a ordem não é óbvia, e que a assinatura de uma dataclass é a ordem de declaração dos campos, não a ordem em que eu penso neles.

**Confundir os dois prompts quebrou o módulo inteiro.** O bug-raiz: carreguei o arquivo *system* dentro de um `Template` que chamei de `user_template`, **nunca** carreguei o `user_qa_template.md`, e perdi o `system` como string. Consequência em cascata: o `.render(question=..., context_blocks=...)` rodava sobre um texto sem placeholders Jinja, ignorando pergunta e blocos; e o `system` nem entrava no retorno. Foi o que mais consolidou a distinção **política vs payload** — não são dois nomes pra mesma coisa, são dois arquivos com responsabilidades diferentes, e fundi-los esvazia o RAG.

**Verde não é prova de correção (de novo, mais sutil).** Numa versão intermediária o `---` de fechamento vazava pro prompt. Os testes checam `marcador in prompt` e comprimento — o marcador aparece *depois* do lixo, então passariam mesmo com o bug. E o `_load` só é exercitado quando `build_prompt` o chama: enquanto `build_prompt` era `raise NotImplementedError`, **nenhum teste tocava o `_load`** — correção dele ficou latente até a integração. Reforçou o que eu já tinha visto no chunking: teste é amostra, não prova; ausência de contraexemplo não é corretude.

A lição transversal da Task 13: quase todos os bugs foram **semântica fina de primitivas** (string como conjunto vs prefixo, `-1` do `find`, Path vs file, binding de argumento de dataclass) e **confusão conceitual de papéis** (system vs user) — não erro de algoritmo. O loop de truncamento, que era a única lógica "de verdade", saiu certo de primeira. Engenharia de contexto é, ao mesmo tempo, decisão de produto (o que entra no prompt e por quê) e precisão cirúrgica nas primitivas que montam esse texto.

### 2.14 Integração e infra: a primeira execução real do pipeline

Fechado o código do B1 (Tasks 8–14, tudo verde no mypy/ruff), veio a Task 15
— **a aceitação**, primeira vez que o pipeline roda de verdade contra a
stack subida. Aprendi mais sobre "verde ≠ correto" aqui do que em qualquer
review, porque os problemas não foram de código nenhum.

**Código que passa no linter nunca rodou.** `handle_document` e
`handle_query` passaram mypy strict + ruff e mesmo assim **nunca executaram**.
A primeira tentativa de subir nem chegou no meu código: quebrou em infra. A
lição do dia inteiro (do `args.wat`, do `str+int`) escalou de camada: type
checker prova forma, não comportamento; e nem o comportamento importa se a
stack não sobe.

**Config local não é versionada — e isso é um passo de setup.** `make dev`
falhou de cara: `env file .env.local not found`. O `.env.local` é
gitignored de propósito (config de máquina, cada dev faz o seu a partir do
`.env.example`); o `docker compose` exige o `env_file` existir. Entendi na
prática a separação `.env.example` (versionado, template) vs `.env.local`
(local, real) que eu só tinha lido na teoria no `config.py`.

**Ler log em escala: volume não é problema.** O RabbitMQ vomitou centenas
de linhas no boot — `Application mnesia exited with reason: stopped`,
`rebuilding indices from scratch`, `peer discovery ... does not contain the
local node []`. Pareceu desastre; era boot **saudável** (single-node, data
dir vazio). Aprendi a varrer log por `ERROR`/`exited with reason: {error}`/
exit ≠ 0, não por existir `[warning]` ou muito `[info]`. E que `docker
compose ps` (coluna STATUS: Up/Exited/healthy) diagnostica estado de
container muito melhor que `tail` em log.

**O plano é rascunho; a ferramenta instalada manda.** O comentário do
`docker-compose.yml` dizia que o bloco GPU era "ignorado se não tiver
toolkit". O `docker compose` v2 **não ignora — falha duro**
(`could not select device driver "nvidia"`). Mesmíssima lição do
`asyncio.TimeoutError`→builtin e do `qdrant.search` deprecado (§2.8, §2.13):
documentação/plano envelhece, confie no que está instalado.

**Habilitar GPU é uma cadeia em camadas.** Diagnostiquei com `lspci -nnk`:
a linha da NVIDIA tinha `Kernel modules: nvidiafb, nouveau` mas **sem**
`Kernel driver in use: nvidia` — driver proprietário ausente, por isso não
havia `nvidia-smi`. A cadeia é hardware → driver proprietário → NVIDIA
Container Toolkit → Docker; não dá pra pular camada. Máquina híbrida (Intel
UHD pro vídeo + RTX 4060 Ti pra cálculo) é o cenário ideal e foi o que tinha.

**Defeito de repo só aparece executando.** O bloco `deploy.resources` (GPU)
do `ollama` está obrigatório no compose, então qualquer host sem GPU/toolkit
(colega, clone limpo) não sobe — quebra o "smoke a partir de clone limpo" do
B5. Isso **não** apareceu em review nenhum; só rodando num host sem o toolkit
configurado. Reforça que execução real é uma camada de verificação que
review e type-check não cobrem. Documentei o setup como runbook executável
(`docs/setup-gpu-pc1.md`) — mesma filosofia de spec-antes-de-código (§3.1),
agora aplicada a infra: a pré-condição vira documento, não conhecimento
tribal.

### 2.15 Debugar o pipeline real: contrato do chunker e fronteira de erro do worker

Com a GPU no ar, o `make smoke` finalmente rodou o meu código de ponta a
ponta — e foi onde aprendi mais nesta sessão. Quatro camadas de bug
(GPU → toolkit → chunker → worker), todas invisíveis pro mypy/ruff.

**O verde do script não é o marco.** O smoke saiu `[smoke] OK` com **0
citações** e a resposta-fallback "could not find this information". O exit
code mentiu porque "sem citações" era só AVISO no script, não FALHA. Pior
que o §2.14: lá o verde era do type checker; aqui era do meu próprio teste
de aceitação. A definição do marco e o check executável tinham divergido.

**Leia o log de quem produziu o erro, não de quem recebeu.** O worker via
`HTTP 500`; a causa só apareceu no log do **Ollama**: `llm embedding error:
the input length exceeds the context length`. Os dois IPs no GIN log
(`.0.6` ingest falhando, `.0.8` query passando) explicaram por que o smoke
"rodava" sem indexar nada — a pergunta é curta e embeda, os chunks do PDF
estouravam. Sintoma e causa moram em serviços diferentes.

**Heurística não é garantia, e não se audita sozinha.** O
`count_tokens_approx` (chars/4, §2.10) é regra de inglês com tokenizer BPE.
Texto em PT, extraído de PDF (tabela, EAP), tokenizado por WordPiece:
subestima feio — chunk que o código achava ~800 tokens tinha >2048 reais,
e o nomic recusava. Corolário que ficou: pra *provar* o contrato o teste
precisa medir token real; uma heurística só prova que concorda com ela
mesma. Tokenizer real adiado pro B2 — exatamente o que a docstring que eu
escrevi na §2.10 já previa. A realidade cobrou o cheque mais cedo.

**Mira vs teto, e a unidade que me mordeu três revisões seguidas.**
`target_tokens` é preferência (qualidade de retrieval); `max_tokens` é
restrição física do modelo. Não são a mesma variável — o dimensionamento
correto é `min(target, budget)`. Mas o budget nascia em tokens e o loop
media `len()` em chars; levei três rodadas de review pra a conversão `*4`
encaixar (e numa delas introduzi perda silenciosa de 75% do conteúdo com
`passo ≠ fatia`). Aprendi a tratar unidade como invariante explícito,
convertido e nomeado **uma vez** (`budget_chars`) — conversão espalhada foi
a raiz de todos esses bugs.

**Código defensivo morto é dívida, não segurança.** Eu ia escrever uma
varredura-de-garantia no chunker. Depois da prova algébrica de que o teto
nunca estoura, ela virou redundante (nunca dispara) **e** cega (mediria com
a mesma métrica falha). Cancelei antes de escrever. O backstop real do
risco "chars/4 mentiu" mora na fronteira de execução (o embedding recusando),
não no chunker — e a produção confirmou: os chunks que sobraram grandes
foram pegos lá, não numa varredura que não existe.

**Fronteira de erro: "chunk ruim, siga" vs "mundo quebrado, pare".**
Capturar `httpx.HTTPStatusError` (pula o chunk, segue o doc) e deixar
`httpx.TransportError` propagar (Ollama fora = pular não faz sentido, todo
chunk falharia). `except Exception` largo mascara bug próprio — provei na
pele: um typo `e.responde` *dentro do próprio handler de erro*
reintroduziu, silencioso, o crash que o handler existia pra evitar. A
camada de retry (tenacity, §2.4) e a fronteira se encaixam: o retry filtra
o transitório, o `except` lida com o que sobrou (permanente nesta execução).

**Skip invisível ≈ perda silenciosa.** Meu primeiro `except` tinha
`log.info("")`. Um chunk descartado sem rastro é tão ruim quanto um crash
sem rastro. Virou `log.warning("ingest.chunk.skipped", doc_id=...,
chunk_index=..., page=..., status=...)` — perda auditável, com
`correlation_id` pra reconstituir o fluxo (§2.3).

**Tudo-ou-nada transforma falha parcial em total.** O upsert era único no
fim do documento; uma exceção no meio descartava até os chunks que já
tinham embedado. Virou upsert incremental por página + um contador que só
cresce (resetar `points` quebrou o `len(points)` do log final — consertar
uma coisa expôs a suposição em outra). Idempotência por ID derivado de
posição, não de conteúdo: limitação que assumi explicitamente, replay real
é B3.

O resultado: 122 chunks indexados, resposta fundamentada sobre o conteúdo
real do PDF, 3 citações válidas. Os chunks pulados (`chunk_index 1`, págs.
2–4, status 500) são a prova viva de que `chars/4` não garante nem com a
margem `//2` — e a razão de o backstop certo ser a fronteira do worker, não
o chunker. Levei o pipeline de "verde mentindo" a "verde porque funciona",
e a diferença não estava em nenhum review nem type-check: estava na
execução. É o §2.14 fechando — execução real é uma camada de verificação
própria, e o code-partner me fez *debugar* cada camada em vez de receber o
patch pronto.

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

### 3.5 A declaração de uso de IA como artefato defensável; e a fronteira de quem executa

A sessão de 17/05 cristalizou dois aprendizados de processo que não são sobre código.

**A declaração de uso de IA não é formalidade — é peça de defesa.** Em certo momento pedi pra IA reescrever o `USO_DE_IA.md` afirmando que uma divisão de trabalho "sempre foi assim", apagando o changelog datado. A IA segurou: o texto anterior do próprio documento, o histórico do repo e o que tinha acontecido na própria sessão contradiziam o "sempre". Minha primeira reação foi me sentir acusado de mentir. O que aprendi, depois que a IA separou as coisas, é a diferença entre **"estou sendo chamado de mentiroso"** e **"este documento precisa sobreviver a um cruzamento de evidências numa arguição"**. Esquecer de atualizar um doc de processo num sprint de 16 dias é normal e humano; retroajustar a declaração de honestidade pra esconder isso é exatamente o erro que o documento existe pra evitar. A saída honesta foi enquadrar o **princípio estável** (a IA dá estrutura e contrato executável; eu escrevo a solução) sem backdatar, com uma linha datada só pro que de fato mudou naquele dia. Ficou a regra: o documento cuja função é honestidade é o último lugar pra arredondar canto — e `CLAUDE.md` e `USO_DE_IA.md` precisam ser mantidos coerentes deliberadamente, não por acaso.

**Quem roda os comandos sou eu.** Estabeleci como convenção (em `CLAUDE.md` + memória de feedback, análogo ao "não commitar") que a IA **sugere** os comandos de teste/lint/type-check mas **não os executa** — nem "só pra confirmar". O porquê: o ciclo rodar → ler o erro → corrigir é onde mora o aprendizado e a posse do código; terceirizar isso pra IA esvazia o exercício. No mesmo espírito, combinei que a granularidade dos `TODO`s de scaffolding se adapta à experiência que eu **declaro** ter naquela parte — pedir o nível certo de ajuda (esqueleto detalhado em terreno novo, conciso no familiar) é, ele mesmo, uma habilidade. A lição reforça a 3.3: trabalhar com IA como parceiro exige eu definir e policiar as fronteiras, não só consumir o que ela entrega.

---

## 4. O que ainda quero aprender (em aberto pros próximos blocos)

- **B1 finalização**: Tasks 8–14 com **código fechado** e gates verdes (mypy strict + ruff): gateway (3 endpoints), chunking, parsing, ingest worker, prompts, `prompt_builder` (TDD 7 testes), query worker (`handle_query` RPC), `Makefile` e `scripts/smoke_test.py`. **Task 15 (aceitação) iniciada e bloqueada** na pré-condição `[A]` do B1: GPU no PC1 (faltava driver NVIDIA proprietário + nvidia-container-toolkit). A stack só subiu pela metade — infra (redis/qdrant/rabbitmq) OK, mas `ollama`/`gateway`/workers não iniciaram pelo erro de GPU. Ou seja: **`handle_document` e `handle_query` ainda não rodaram de verdade nem uma vez** — só mypy/ruff. Setup de GPU documentado em `docs/setup-gpu-pc1.md`; o smoke ponta-a-ponta (e os bugs "verde mas quebra" que ele vai revelar) fica pendente até a GPU subir.
- **B2**: cache distribuído (L1 in-memory, L2 Redis), reranker com cross-encoder bge-reranker-v2-m3, observabilidade Prometheus + Grafana.
- **B3**: o pulo do gato deste projeto — passar de Modo 1 (Compose num host) pra Modo 2 (3 PCs reais via Tailscale). Aqui vou aprender de verdade sobre rede entre hosts, IaC com Terraform/Ansible, e tolerância a falhas em ambiente distribuído real (não simulado).
- **B4**: experimentos quantitativos (latência, throughput, tolerância a falhas) e — se o cronograma permitir — comparação Ollama vs vLLM (bônus +10).
- **B5**: documento técnico final, slides, apresentação.

---

## 5. Conclusão

Em 4 dias trabalhando no Bloco B1, saí de "sei o que é um sistema RAG no abstrato" pra ter os tijolos da fundação no código, com tooling Python moderno, observabilidade desenhada desde o início e infraestrutura Docker preparada pra escalar pra 3 hosts. Mais importante que os artefatos individuais foi internalizar uma forma de trabalhar: **spec antes de código, convenção antes de disciplina, IA como parceiro crítico em vez de gerador opaco**.

Os próximos blocos vão me forçar a sair da zona de conforto do "tudo num host" pra lidar com rede física, particionamento de carga e falhas reais — que é onde a disciplina de Programação Distribuída e Paralela realmente vai cobrar o que eu aprendi.
