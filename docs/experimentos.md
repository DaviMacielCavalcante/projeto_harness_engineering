# Análise de Experimentos — Tema 5 (RAG Distribuído)

> Resultados, implicações e melhorias. Complementa o §7 de [`arquitetura.md`](arquitetura.md).
> Dados brutos em `data/exp*/`.

## Exp 2 — Throughput de queries vs concorrência (Modo 2, 2026-05-31)

200 queries por nível de concorrência C contra `POST /query` (query-workers em PC2/PC3; geração no
Ollama único do PC1). Runner `scripts/run_exp2_query_throughput.py`; gráfico `scripts/plotar_exp2.py`.

| C | QPS | p50 | p95 | p99 | Erros |
|---|---|---|---|---|---|
| 1 | 0.08 | 12.2 s | 16.6 s | 18.5 s | 0 % |
| 2 | 0.09 | 23.8 s | 31.1 s | 33.7 s | 0 % |
| 4 | 0.10 | 36.2 s | 46.2 s | 59.2 s | 0 % |
| 8 | 0.08 | 95.9 s | 120.1 s | 120.7 s | 0 % |
| 16 | 0.13 | 120.1 s | 120.3 s | 120.8 s | 0 % |
| 32 | 0.24 | 120.3 s | 120.6 s | 120.8 s | 0 % |

### Achados

- **Zero erros** em toda a faixa: ao saturar, as queries caem em *degraded mode* no timeout de
  ~120 s (§5.3) — troca qualidade por disponibilidade.
- **Latência satura no teto**: p50 12 s → 120 s; de C=8 em diante a maioria já degrada. O QPS que
  "cresce" (0.08 → 0.24) é majoritariamente degraded.
- **Gargalo = geração no Ollama único (1 GPU)**: ~12 s por resposta, serializada. Mais
  query-workers não ajudam — a geração afunila num só ponto.
- **Cache L2 sem efeito nesta rodada**: ~170 das 200 queries são repetições, mas o p50 no C=1 é
  12 s (não ~0). Hipótese: workers não alcançam o Redis do PC1 (cache *fail-open* → miss). A
  investigar.

### Melhorias propostas

1. **Geração (o gargalo)**: vLLM com continuous batching; múltiplos Ollama (1/GPU); modelo
   quantizado / cap de `num_predict`.
2. **Backpressure no gateway**: limitar concorrência admitida e responder 429/503 cedo, em vez de
   empurrar tudo pro timeout.
3. **Degradação proativa**: timeout menor ou degraded mode antecipado sob fila longa.
4. **Cache**: corrigir o L2 em Modo 2 (maior ganho rápido); depois, cache semântico.
5. **Observabilidade**: expor "degraded ratio" no dashboard — QPS sem esse contexto engana.
6. **Streaming** de tokens (latência percebida) e **metodologia**: rodar com queries variadas /
   `FLUSHALL` para separar geração fria de cache.

---

> Exp 1 (speedup de indexação) no §7.3 do documento técnico; Exp 4 (chaos) pendente.
