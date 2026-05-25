---
marp: true
theme: default
paginate: true
---

# RAG Distribuído

Sistema de Q&A com Retrieval-Augmented Generation em 3 PCs físicos via Tailscale.

---

# Objetivo

- Responder perguntas sobre corpus de engenharia de software.
- Usar contexto recuperado, não conhecimento solto do modelo.
- Demonstrar paralelismo, tolerância a falhas, observabilidade e IaC.

---

# Topologia

- PC1: gateway, RabbitMQ, Qdrant, Redis, Ollama, rerank-service, observabilidade.
- PC2/PC3: workers de ingestão e query.
- Rede privada: Tailscale.
- Modo local: Docker Compose profile `all`.

---

# Pipeline de Ingestão

- `POST /ingest` publica em `ingest.documents`.
- `ingest-worker-doc`: parse + chunk.
- `ingest-worker-chunk`: embedding + upsert no Qdrant.
- Duas filas permitem paralelismo de dados.

---

# Pipeline de Query

- Gateway usa RPC sobre RabbitMQ.
- Query-worker executa embed, retrieval, rerank, cache, prompt e geração.
- Citações vêm de tool calling ou fallback estrutural.
- Cache L1/L2 e sessão usam Redis.

---

# Engenharia de Contexto

- Chunking recursivo com overlap.
- Retrieval top-20 por embedding.
- Re-ranking top-k com cross-encoder.
- Prompts versionados em `prompts/`.
- Tool `cite_source` para citações estruturadas.

---

# Tolerância a Falhas

- Retry com backoff em clients HTTP.
- DLX/DLQ por fila.
- Gateway com degraded mode quando query-worker não responde.
- Fallback estrutural de citações.

---

# Observabilidade

- `/metrics` no gateway, rerank-service e workers.
- Prometheus coleta métricas `rag_*`.
- Grafana mostra throughput, p95 por fase, tokens, erros e cache hit ratio.
- Loki recebe logs JSON via Promtail.

---

# IaC

- Docker Compose para Modo 1.
- Ansible para bootstrap e deploy.
- Terraform com provider Docker para containers por host.
- Tailscale para rede privada entre PCs.

---

# Demonstração

1. Subir stack local.
2. Validar `/health` e `/targets`.
3. Seed de corpus.
4. Rodar query.
5. Mostrar métricas no Grafana e logs no Loki.

---

# Limitações

- Modo 2 completo depende dos três PCs conectados.
- Exp 3 com vLLM foi cortado por cronograma.
- Tool calling funciona isolado, mas perde aderência sob contexto RAG denso.
- Corpus de escala precisa ser curado fora do repositório.

---

# Fechamento

O projeto demonstra distribuição real, paralelismo por filas, engenharia de
contexto explícita, tolerância a falhas e observabilidade operacional em uma
stack local reproduzível.
