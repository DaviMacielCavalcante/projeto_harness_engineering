# Evidencias operacionais - Pablo

Coleta feita em 2026-05-25 nesta maquina local do Pablo, em Modo 1 com Docker
Compose. Esta evidencia nao substitui a validacao distribuida via PC1/Tailscale,
mas comprova que a stack local, observabilidade e smoke estavam funcionais.

## Commit revisado

Commit no topo do historico:

```text
4d51cf3 (HEAD -> main, origin/main, origin/HEAD) Finalizacao de trilha operacional do Pablo
```

Resumo do commit:

- 32 arquivos alterados.
- 1657 linhas adicionadas e 39 removidas.
- Inclui workers `/metrics`, scripts operacionais, corpus minimo, queries de
  avaliacao, slides, documentos de entrega e handoff em `CLAUDE.md`.

Observacao: depois desse commit ainda havia uma alteracao local em
`docs/proximos-passos-pablo.md`, apenas para corrigir o papel da
`abdon-workstation` e reforcar que este PC e o worker real.

## Containers locais

`docker ps` mostrou a stack local ativa:

- `rag-gateway`
- `rag-rabbitmq`
- `rag-qdrant`
- `rag-redis`
- `rag-ollama`
- `rag-rerank`
- `rag-prometheus`
- `rag-grafana`
- `rag-loki`
- `rag-promtail`
- `rag-ingest-worker-doc`
- `rag-ingest-worker-chunk`
- `rag-query-worker`

## Saude dos servicos

Validacoes HTTP:

- Gateway: `GET http://localhost:8000/health` retornou `{"status":"ok"}`.
- Prometheus: `GET http://localhost:9090/-/ready` retornou `Prometheus Server is Ready`.
- Grafana: `GET http://localhost:3000/api/health` retornou status `ok`.
- Loki: `GET http://localhost:3100/ready` retornou `ready` apos aguardar a janela de inicializacao.

## Prometheus targets

`GET http://localhost:9090/api/v1/targets?state=active` mostrou todos estes
targets como `up`:

| job | instance | health |
| --- | --- | --- |
| gateway | gateway:8000 | up |
| prometheus | localhost:9090 | up |
| rabbitmq | rabbitmq:15692 | up |
| rerank-service | rerank-service:8081 | up |
| workers | ingest-worker-doc:9100 | up |
| workers | ingest-worker-chunk:9100 | up |
| workers | query-worker:9100 | up |

## Grafana

A API autenticada do Grafana listou o dashboard provisionado:

| uid | titulo | url |
| --- | --- | --- |
| `rag-distribuido` | RAG Distribuido | `/d/rag-distribuido/rag-distribuido` |

## Workers `/metrics`

Os endpoints dos workers responderam com metricas `rag_*`:

- `http://localhost:9100/metrics`
- `http://localhost:9101/metrics`
- `http://localhost:9102/metrics`

Exemplos observados:

- `rag_ingest_pipeline_duration_seconds`
- `rag_throughput_docs_total`
- `rag_query_pipeline_duration_seconds`
- `rag_throughput_queries_total`
- `rag_tokens_total`
- `rag_cache_hits_total`
- `rag_cache_misses_total`
- `rag_ollama_inflight_requests`

No `query-worker`, havia metricas reais de uso, incluindo queries, cache e
tokens. Isso indica que o dashboard tinha dados para popular os paineis apos o
smoke/chaos test.

## Qdrant

`GET http://localhost:6333/collections/se_corpus` retornou:

- status da collection: `green`;
- tamanho do vetor: `768`;
- distancia: `Cosine`;
- `points_count=6`.

## Smoke test

Comando executado:

```powershell
uv run python scripts\smoke_test.py --file samples\corpus\rag-contexto.md --question "O que e RAG e por que citacoes sao importantes?" --wait 10 --health-timeout 30
```

Resultado final:

- health do gateway: OK;
- ingest aceito;
- query respondida;
- smoke B1: OK;
- checks B2: cache/sessao/metrics/rerank sem erro fatal;
- resultado final: `[smoke] OK`.

Observacao importante: uma tentativa anterior com timeout total de 120 segundos
estourou o limite enquanto o Ollama carregava/rodava em CPU. Os logs mostraram
que a query foi respondida depois, e a segunda tentativa terminou com sucesso em
aproximadamente 40,7 segundos. Isso e coerente com o uso local em CPU/AMD e nao
invalida a evidencia funcional.

## Achado tecnico durante a coleta

Nos logs do `query-worker`, apareceu uma falha recuperada na primeira tentativa:

```text
ValidationError: Citation.page
Input should be a valid integer, unable to parse string as an integer
input_value='null'
```

Depois da falha, a mesma query foi reprocessada e respondeu com sucesso. Isso
nao bloqueia a entrega local, mas e um ponto tecnico para investigar se sobrar
tempo: normalizar valores de pagina como `null`, `"null"` ou `"n/a"` antes de
criar o schema `Citation`.

## O que continua fora desta evidencia

- Acesso real deste PC aos servicos do PC1 via Tailscale.
- Worker deste PC rodando em Modo 2 distribuido.
- Experimentos B4 completos com multiplos workers e corpus de escala.
- Screenshots PNG do Prometheus/Grafana/Loki. A coleta visual foi tentada com
  Edge headless, mas o navegador nao gravou os arquivos no workspace; por isso,
  esta evidencia ficou baseada nas APIs HTTP dos servicos.
