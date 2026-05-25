# Proximos passos - Pablo

Contexto atualizado em 2026-05-24 apos o pull que trouxe o commit `c4739bd`
(`B3 Task 4 fechada - observabilidade + doc tecnico`).

## Quem esta usando este contexto

Voce e o Pablo. Este PC atual **nao** e a `abdon-workstation`; e uma maquina
extra com AMD RX 7600 8 GB VRAM. A decisao operacional atual e usar **este PC**
como a maquina que vai conectar ao ambiente distribuido e subir o worker. A
`abdon-workstation` fica apenas como maquina de teste para validar Tailscale.

## Estado atualizado do projeto

O pull mudou bastante a situacao:

- Observabilidade B3 Task 4 foi adicionada:
  - `infra/prometheus/prometheus.yml`
  - `infra/grafana/`
  - `infra/loki/`
  - `infra/promtail/`
  - novos services no `docker-compose.yml`: Prometheus, Grafana, Loki, Promtail
  - RabbitMQ com `rabbitmq_prometheus` e porta `15692`
- `docs/arquitetura.md` foi redigido como documento tecnico.
- `docs/arquitetura.pdf` ja existe no repo.
- Diagramas foram adicionados em `docs/diagrams/`.
- `docs/observabilidade.md` foi adicionado.
- `PENDENCIAS_FINAIS.md` virou a fonte mais clara para o fechamento.
- O Exp 3, Ollama vs vLLM, foi cortado oficialmente.

O que continua critico para a sua trilha:

- `/metrics` nos workers foi implementado e validado no Prometheus com Docker saudavel.
- este PC ja entrou no Tailscale e enxerga as maquinas da tailnet;
- ainda falta validar acesso aos servicos do PC1 quando o Davi estiver disponivel;
- `abdon-workstation` pode ser usada apenas como teste simples de Tailscale.
- O corpus minimo versionavel existe; o corpus de escala (~80 PDFs) ainda precisa
  ser curado/seedado fora do repo.
- Scripts operacionais foram criados: `seed_corpus.py`, `dlq_inspector.py`,
  `chaos_test.sh` e `chaos_test.ps1`.

## Seu PC atual

Este PC:

- tem AMD RX 7600 8 GB VRAM;
- nao tem NVIDIA/CUDA;
- nao deve ser tratado como PC1;
- substitui a `abdon-workstation` como worker real da trilha do Pablo;
- deve ser usado para desenvolvimento, testes unitarios, documentacao e smoke
  leve com modelo pequeno.

Uso recomendado:

- editar e testar codigo;
- rodar `uv run pytest tests/unit -v`;
- subir a stack local em CPU/modelo pequeno;
- validar RabbitMQ, Qdrant, Redis, Gateway e Grafana;
- manter validada a Task 3 de metrics nos workers.

Nao contar com este PC para:

- validar `nvidia-container-toolkit`;
- rodar `qwen2.5:7b-instruct` com desempenho de demo;
- reproduzir o PC1;
- substituir a validacao final em GPU NVIDIA.

## Ambiente deste PC

Encontrado:

- Python 3.12.10 no `.venv`.
- `uv 0.11.16`.
- Docker 29.4.3.
- `docker-compose v5.1.3`.
- `docker compose` nao funciona; usar `docker-compose`.
- Node e `npx` existem.
- `make` ausente.
- `terraform` ausente.
- `ansible` ausente.
- `pandoc` e `xelatex` ausentes.
- `tailscale` instalado e conectado na tailnet.
- `nvidia-smi` ausente.

Correcoes locais ja feitas:

- `uv.toml` criado com cache local:

```toml
cache-dir = ".uv-cache"
```

- `.uv-cache/` adicionada ao `.gitignore`.
- `uv run python --version` validado com sucesso.
- `.env.local` criado localmente com DNS interno do Compose e
  `GENERATION_MODEL=llama3.2:1b`.

## Atencao ao Docker neste PC AMD

O `docker-compose.yml` ainda tem bloco de GPU NVIDIA no service `ollama`:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

Em PC sem NVIDIA, isso pode falhar ao subir o container do Ollama. Se acontecer,
nao e bug da aplicacao; e incompatibilidade do perfil local com seu hardware.
O caminho pragmatico e criar/usar um override local para remover a reserva de
GPU ou testar no PC1. Antes de mexer no Compose versionado, confirme o erro
real ao rodar `docker-compose --profile all up -d --build`.

## Checklist imediato neste PC

- [x] `uv` corrigido com cache local.
- [x] `.env.local` criado para Modo 1 local.
- [x] Validar testes unitarios:

```powershell
uv run pytest tests/unit -v
```

- [x] Validar config do Compose:

```powershell
docker-compose --profile all config --services
```

- [x] Tentar subir stack local:

```powershell
docker-compose --profile all up -d --build
```

- [x] Se o Ollama falhar por GPU NVIDIA ausente, parar e ajustar caminho local
  antes de perder tempo investigando aplicacao.
- [x] Baixar modelos leves:

```powershell
docker exec rag-ollama ollama pull nomic-embed-text
docker exec rag-ollama ollama pull llama3.2:1b
```

- [x] Rodar smoke apenas depois de containers saudaveis:

```powershell
uv run python scripts/smoke_test.py
```

## Suas prioridades tecnicas

### 1. B3 Task 3 - `/metrics` nos workers

Esta e a maior pendencia sua porque bloqueia o dashboard completo.

- [x] Criar `src/shared/workers_metrics_server.py`.
- [x] Usar `aiohttp` para expor endpoint `/metrics` em processo standalone.
- [x] Reutilizar `metrics_response()` de `src/shared/metrics.py`.
- [x] Chamar o servidor de metrics no bootstrap de:
  - [x] `src/workers/ingest/main.py`
  - [x] `src/workers/query/main.py`
- [x] Fazer os workers ouvirem porta `9100` dentro do container.
- [x] Expor portas diferentes por container no Compose, se necessario:
  - [x] `ingest-worker-doc`: host `9100`
  - [x] `ingest-worker-chunk`: host `9101`
  - [x] `query-worker`: host `9102`
- [x] Validar no Prometheus `/targets` que o job `workers` saiu de `DOWN`.

Criterio de aceite:

- `curl http://localhost:9100/metrics` retorna metricas `rag_*`.
- `curl http://localhost:9101/metrics` retorna metricas `rag_*`.
- `curl http://localhost:9102/metrics` retorna metricas `rag_*`.
- Grafana comeca a popular throughput, latencia por fase, tokens e cache hit ratio apos smoke.

### 2. Adicionar a maquina worker do Pablo via Tailscale

Decisao atual: este PC sera o worker real. A `abdon-workstation` sera usada
apenas para teste de Tailscale.

- [x] Instalar Tailscale neste PC.
- [x] Entrar na tailnet correta do trio.
- [x] Confirmar que as maquinas aparecem na tailnet.
- [ ] Confirmar/anotar IP `100.x.y.z` deste PC.
- [x] Instalar Docker + Docker Compose.
- [x] Instalar Python/uv ou validar `uv sync`.
- [x] Clonar repo.
- [ ] Preencher configs de Modo 2 conforme `infra/ansible/inventory.yml.example`.
- [ ] Validar que este PC consegue acessar o PC1 via Tailscale:
  - RabbitMQ `5672`
  - Ollama `11434`
  - Qdrant `6333`
  - Redis `6379`
  - Rerank `8081`
- [ ] Aguardar Davi estar disponivel para validar o acesso real ao PC1.

### 3. Corpus seedado

- [x] Criar `samples/corpus/`.
- [x] Curar documentos sobre engenharia de software.
- [x] Evitar commitar PDFs grandes se `.gitignore` mandar ignorar.
- [x] Criar `scripts/seed_corpus.py`.
- [x] Script deve enviar PDFs/MDs para `POST /ingest`.
- [x] Registrar quantidade de arquivos enviados/falhas.

Criterio de aceite:

- `uv run python scripts/seed_corpus.py --corpus samples/corpus`
- Retorna `enviados=N falhas=0` ou falhas justificadas.
- Qdrant mostra aumento de `points_count`.

### 4. DLQ inspector

- [x] Criar `scripts/dlq_inspector.py`.
- [x] Suportar comandos:
  - `list <queue.dlq>`
  - `replay <queue.dlq> --limit N`
  - `purge <queue.dlq> --yes`
- [x] Usar `aio-pika`.
- [x] Reusar `settings.rabbitmq_url`.

Criterio de aceite:

```powershell
uv run python scripts/dlq_inspector.py list ingest.chunks.dlq
```

### 5. Chaos test

- [x] Criar `scripts/chaos_test.sh` ou equivalente PowerShell se necessario.
- [x] Cen H1: parar e reiniciar `rag-ingest-worker-chunk`.
- [x] Cen H2: parar e reiniciar `rag-ollama`.
- [x] Cen H3: rajada de queries.
- [x] Salvar saida em `data/b3-chaos.txt` ou `data/exp4/`.

## Prioridades de entrega geral

Ja melhorou apos o pull:

- [x] `docs/arquitetura.md` existe como doc tecnico.
- [x] `docs/arquitetura.pdf` existe.
- [x] observabilidade foi adicionada.
- [x] diagramas existem.
- [x] `PENDENCIAS_FINAIS.md` existe.

Ainda falta ou precisa revisar:

- [x] Sua Task 3 dos workers metrics.
- [x] Este PC conectado ao Tailscale como worker real.
- [ ] Testar acesso ao PC1 via Tailscale quando Davi estiver disponivel.
- [x] `scripts/seed_corpus.py`.
- [x] `scripts/dlq_inspector.py`.
- [x] `scripts/chaos_test.sh`.
- [x] `data/eval_queries.jsonl` com pelo menos 30 queries.
- [x] `docs/decisoes.md`.
- [x] `docs/prompts.md`.
- [x] `docs/slides/slides.md` e `slides.pdf`.
- [x] `ENTREGA.md`.
- [x] Relatorio individual do Pablo: `docs/relatorios_aprendizagem/pablo_abdon.md`.
- [x] Revisar `README.md` final.

## Comandos uteis neste PC

Validar `uv`:

```powershell
uv cache dir
uv run python --version
uv run pytest tests/unit -v
```

Validar Compose:

```powershell
docker-compose --profile all config --services
```

Subir stack:

```powershell
docker-compose --profile all up -d --build
```

Ver containers:

```powershell
docker ps
```

Baixar modelos:

```powershell
docker exec rag-ollama ollama pull nomic-embed-text
docker exec rag-ollama ollama pull llama3.2:1b
```

Smoke:

```powershell
uv run python scripts/smoke_test.py
```

Logs:

```powershell
docker-compose --profile all logs -f --tail=200
```

Derrubar stack:

```powershell
docker-compose --profile all down
```

Limpar volumes:

```powershell
docker-compose --profile all down -v
```

UIs locais apos subir:

- Gateway: `http://localhost:8000/docs`
- RabbitMQ UI: `http://localhost:15672` (`guest`/`guest`)
- RabbitMQ metrics: `http://localhost:15692/metrics`
- Qdrant: `http://localhost:6333/dashboard`
- Prometheus: `http://localhost:9090`
- Prometheus targets: `http://localhost:9090/targets`
- Grafana: `http://localhost:3000` (`admin`/`admin`)
- Loki ready: `http://localhost:3100/ready`

## Ordem recomendada para voce

1. Rodar testes unitarios neste PC.
2. Tentar subir Compose local.
3. Se Compose falhar por NVIDIA/Ollama, registrar erro e nao tratar como bug do app.
4. Implementar `/metrics` nos workers.
5. Validar workers no Prometheus.
6. Criar `seed_corpus.py`.
7. Criar `dlq_inspector.py`.
8. Criar `chaos_test.sh`.
9. Adicionar/configurar este PC no Tailscale como worker real.
10. Escrever seu relatorio individual.
11. Ajudar a revisar doc/slides/README/ENTREGA.
