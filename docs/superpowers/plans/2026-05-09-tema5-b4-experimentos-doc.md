# Tema 5 — B4: Experimentos e Documento Técnico

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rodar os experimentos do plano experimental do spec (Exp 1 a 4), gerar gráficos, e produzir o documento técnico de 8–15 páginas (entregável 8.2).

**Architecture:** Sistema do B3 já em produção (Modo 2). Adicionamos: dataset de queries de avaliação, runners parametrizáveis para cada experimento (variam N workers, C concorrência, modelo gerador), coleta de CSVs, scripts de plot em matplotlib, e a estrutura do documento técnico.

**Tech Stack:** Adições: `matplotlib>=3.9`, `pandas>=2.2` para análise dos CSVs. (`locust` opcional para Exp 2 se quisermos um gerador de carga industrial; alternativa: script asyncio caseiro mais simples).

**Bloco do cronograma:** B4 (21–23/05/2026, 3 dias). Exp 3 (vLLM) é condicional: roda apenas se entrar no dia 21 com cronograma verde.

**Marco luz-verde do bloco:** todos os experimentos não-condicionais executados, CSVs salvos, gráficos gerados em PNG, documento técnico em rascunho avançado (todas as seções com conteúdo, ainda que sujeito a polimento em B5).

---

## Estrutura de arquivos a criar/modificar

```
projeto_harness_engineering/
├── data/
│   ├── eval_queries.jsonl                       # CREATE: 50 queries curadas
│   ├── exp1/                                    # CREATE: outputs Exp 1
│   ├── exp2/
│   ├── exp3/
│   └── exp4/
├── scripts/
│   ├── eval_dataset.py                          # CREATE: cura/gera queries de eval
│   ├── run_exp1_indexing_speedup.py             # CREATE
│   ├── run_exp2_query_throughput.py             # CREATE
│   ├── run_exp3_ollama_vs_vllm.py               # CREATE (condicional)
│   ├── run_exp4_chaos.py                        # CREATE
│   ├── plot_exp1.py                             # CREATE
│   ├── plot_exp2.py
│   ├── plot_exp3.py
│   └── plot_exp4.py
├── docs/
│   ├── arquitetura.md                           # CREATE: doc técnico (8–15 pg)
│   ├── decisoes.md                              # CREATE: ADRs
│   └── prompts.md                               # CREATE: apêndice
└── pyproject.toml                               # MODIFY: matplotlib, pandas
```

---

## Task 1: Dataset de avaliação (`scripts/eval_dataset.py`)

**Files:**
- Create: `data/eval_queries.jsonl`
- Create: `scripts/eval_dataset.py` (opcional — pode ser curadoria 100% manual)

- [ ] **Step 1: Curar 50 queries em PT/EN sobre engenharia de software**

Crie `data/eval_queries.jsonl` com uma query por linha. Distribua entre PT e EN (proporção ~70/30) e cubra tópicos do corpus:

```jsonl
{"id":"q001","lang":"pt","question":"O que é arquitetura hexagonal?","topic":"arquitetura"}
{"id":"q002","lang":"pt","question":"Quais são os princípios SOLID?","topic":"design"}
{"id":"q003","lang":"pt","question":"Como funciona um circuit breaker?","topic":"resiliência"}
{"id":"q004","lang":"pt","question":"Qual a diferença entre microserviços e monolito modular?","topic":"arquitetura"}
{"id":"q005","lang":"pt","question":"O que é eventual consistency?","topic":"distribuído"}
{"id":"q006","lang":"pt","question":"Como o padrão CQRS separa leitura e escrita?","topic":"design"}
{"id":"q007","lang":"pt","question":"O que caracteriza uma aplicação 12-factor?","topic":"deploy"}
{"id":"q008","lang":"pt","question":"Quando usar gRPC em vez de REST?","topic":"protocolos"}
{"id":"q009","lang":"pt","question":"Como mensageria assíncrona ajuda em arquiteturas distribuídas?","topic":"distribuído"}
{"id":"q010","lang":"pt","question":"O que são bounded contexts em DDD?","topic":"design"}
{"id":"q011","lang":"en","question":"What is the saga pattern?","topic":"distribuído"}
{"id":"q012","lang":"en","question":"Explain the strangler fig pattern.","topic":"refactoring"}
{"id":"q013","lang":"en","question":"What are idempotent operations?","topic":"resiliência"}
{"id":"q014","lang":"en","question":"How does sharding differ from partitioning?","topic":"dados"}
{"id":"q015","lang":"en","question":"What is a deadletter queue used for?","topic":"mensageria"}
```

> Continue até 50 entradas. Se o tempo apertar, 30 já dão experimentos significativos.

**Gold answers** (opcional para B4, alvo se sobrar tempo):
- Adicione campo `"expected_keywords": ["domínio", "porta", "adaptador"]` a cada query.
- Permite calcular um proxy de qualidade (% de respostas que contêm pelo menos 2 das keywords esperadas).

---

## Task 2: Experimento 1 — Speedup da indexação

**Files:**
- Create: `scripts/run_exp1_indexing_speedup.py`
- Create: `scripts/plot_exp1.py`

- [ ] **Step 1: Implementar `run_exp1_indexing_speedup.py`**

```python
"""
Experimento 1: speedup da indexação variando N workers de chunk.

Para cada N ∈ N_VALUES:
  1. purge filas + drop collection Qdrant
  2. ajusta réplicas do worker chunk via docker compose scale
  3. dispara ingestão de samples/corpus/* via gateway
  4. mede tempo até points_count estabilizar
  5. registra throughput agregado em data/exp1/results.csv

Uso:
  uv run python scripts/run_exp1_indexing_speedup.py [--corpus samples/corpus]
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx


N_VALUES = [1, 2, 4, 6, 8]
GATEWAY = "http://localhost:8000"
QDRANT = "http://localhost:6333"


def reset_state():
    print("[exp1] purgando filas e collection")
    subprocess.run(["docker", "exec", "rag-rabbitmq", "rabbitmqctl", "purge_queue", "ingest.documents"], check=False)
    subprocess.run(["docker", "exec", "rag-rabbitmq", "rabbitmqctl", "purge_queue", "ingest.chunks"], check=False)
    httpx.delete(f"{QDRANT}/collections/se_corpus", timeout=10)
    time.sleep(2)


def scale_chunk_workers(n: int):
    print(f"[exp1] escalando ingest-worker-chunk para {n} réplicas")
    subprocess.run(
        ["docker", "compose", "--profile", "all", "up", "-d", "--scale", f"ingest-worker-chunk={n}", "ingest-worker-chunk"],
        check=True,
    )
    time.sleep(5)


def submit_corpus(corpus: Path) -> int:
    files = list(corpus.glob("**/*.pdf")) + list(corpus.glob("**/*.md"))
    print(f"[exp1] submetendo {len(files)} arquivos")
    submitted = 0
    for f in files:
        try:
            import base64
            content = base64.b64encode(f.read_bytes()).decode()
            r = httpx.post(
                f"{GATEWAY}/ingest",
                json={
                    "filename": f.name,
                    "content_b64": content,
                    "source_type": "pdf" if f.suffix.lower() == ".pdf" else "md",
                },
                timeout=20,
            )
            if r.is_success:
                submitted += 1
        except Exception:
            pass
    return submitted


def wait_for_indexing(target: int, timeout: float = 1200) -> tuple[float, int]:
    """Espera points_count parar de crescer ou atingir target. Retorna (elapsed_s, final_count)."""
    started = time.perf_counter()
    last_count = 0
    stable_for = 0
    while time.perf_counter() - started < timeout:
        try:
            r = httpx.get(f"{QDRANT}/collections/se_corpus", timeout=5).json()
            count = r["result"]["points_count"]
        except Exception:
            time.sleep(2)
            continue
        if count == last_count:
            stable_for += 1
            if stable_for >= 5:  # 25s estável
                break
        else:
            stable_for = 0
            last_count = count
        time.sleep(5)
    return time.perf_counter() - started, last_count


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", default="samples/corpus")
    args = p.parse_args()

    out = Path("data/exp1")
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for n in N_VALUES:
        print(f"\n=== Exp1 N={n} ===")
        reset_state()
        scale_chunk_workers(n)
        submitted = submit_corpus(Path(args.corpus))
        elapsed, count = wait_for_indexing(target=submitted * 30)  # estimativa de chunks
        chunks_per_s = count / elapsed if elapsed > 0 else 0
        print(f"[exp1] N={n} elapsed={elapsed:.1f}s chunks={count} cps={chunks_per_s:.2f}")
        rows.append({"N": n, "elapsed_s": round(elapsed, 1), "chunks": count, "chunks_per_s": round(chunks_per_s, 2)})

    csv_path = out / "results.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["N", "elapsed_s", "chunks", "chunks_per_s"])
        w.writeheader()
        w.writerows(rows)
    print(f"[exp1] resultados em {csv_path}")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Implementar `plot_exp1.py`**

```python
"""Plot Exp 1: speedup e eficiência."""
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    csv_path = Path("data/exp1/results.csv")
    rows = []
    with csv_path.open() as f:
        for r in csv.DictReader(f):
            rows.append({"N": int(r["N"]), "elapsed_s": float(r["elapsed_s"]), "cps": float(r["chunks_per_s"])})

    rows.sort(key=lambda x: x["N"])
    base = rows[0]["elapsed_s"]
    speedups = [base / r["elapsed_s"] for r in rows]
    efficiency = [s / r["N"] for s, r in zip(speedups, rows)]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    axes[0].plot([r["N"] for r in rows], speedups, "o-", label="medido")
    axes[0].plot([r["N"] for r in rows], [r["N"] for r in rows], "--", label="ideal (linear)")
    axes[0].set_xlabel("N workers de chunk")
    axes[0].set_ylabel("Speedup (T₁ / Tₙ)")
    axes[0].set_title("Exp 1 — Speedup da indexação")
    axes[0].grid(True)
    axes[0].legend()

    axes[1].plot([r["N"] for r in rows], efficiency, "s-")
    axes[1].axhline(1.0, color="gray", linestyle="--", alpha=0.5)
    axes[1].set_xlabel("N workers de chunk")
    axes[1].set_ylabel("Eficiência (speedup / N)")
    axes[1].set_title("Exp 1 — Eficiência paralela")
    axes[1].grid(True)
    axes[1].set_ylim(0, 1.2)

    fig.tight_layout()
    out = Path("data/exp1/exp1.png")
    fig.savefig(out, dpi=150)
    print(f"[plot1] salvo em {out}")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Adicionar deps**

`pyproject.toml`: `"matplotlib>=3.9"`, `"pandas>=2.2"`.

- [ ] **Step 4: Executar**

Run: `uv run python scripts/run_exp1_indexing_speedup.py`
Run (após terminar): `uv run python scripts/plot_exp1.py`

Expected: `data/exp1/results.csv` com 5 linhas e `data/exp1/exp1.png`.

---

## Task 3: Experimento 2 — Throughput de queries

**Files:**
- Create: `scripts/run_exp2_query_throughput.py`
- Create: `scripts/plot_exp2.py`

- [ ] **Step 1: Implementar `run_exp2_query_throughput.py`**

```python
"""
Experimento 2: throughput de queries vs concorrência.

Para cada C ∈ C_VALUES, dispara 200 queries com C concorrência e mede:
- tempo total (e qps agregado)
- p50/p95/p99 de latência por query
- taxa de erro

Pool de query-workers fixo em 6 (2 por PC). Ajuste via docker compose scale antes de rodar:
  docker compose up -d --scale query-worker=6

Uso:
  uv run python scripts/run_exp2_query_throughput.py
"""
import asyncio
import csv
import json
import statistics
import sys
import time
from pathlib import Path

import httpx


C_VALUES = [1, 2, 4, 8, 16, 32]
GATEWAY = "http://localhost:8000"
N_QUERIES = 200


async def run_query(client: httpx.AsyncClient, q: dict) -> tuple[float, bool]:
    started = time.perf_counter()
    try:
        r = await client.post(
            f"{GATEWAY}/query",
            json={"question": q["question"], "top_k": 5},
            timeout=180,
        )
        ok = r.status_code == 200
    except Exception:
        ok = False
    return time.perf_counter() - started, ok


async def run_round(c: int, queries: list[dict]) -> dict:
    sem = asyncio.Semaphore(c)
    async with httpx.AsyncClient() as client:
        results = []
        async def gated(q):
            async with sem:
                return await run_query(client, q)
        started = time.perf_counter()
        results = await asyncio.gather(*[gated(q) for q in queries])
        total = time.perf_counter() - started

    latencies = [l for l, ok in results if ok]
    errors = sum(1 for _, ok in results if not ok)
    qps = len(queries) / total if total > 0 else 0
    return {
        "C": c,
        "total_s": round(total, 2),
        "qps": round(qps, 2),
        "p50": round(statistics.median(latencies), 3) if latencies else None,
        "p95": round(statistics.quantiles(latencies, n=20)[18], 3) if len(latencies) >= 20 else None,
        "p99": round(statistics.quantiles(latencies, n=100)[98], 3) if len(latencies) >= 100 else None,
        "error_rate": round(errors / len(queries), 3),
    }


async def main():
    queries = []
    with Path("data/eval_queries.jsonl").open() as f:
        for line in f:
            queries.append(json.loads(line))
    # Repete a lista até atingir N_QUERIES
    while len(queries) < N_QUERIES:
        queries = queries + queries
    queries = queries[:N_QUERIES]

    out = Path("data/exp2")
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for c in C_VALUES:
        print(f"\n=== Exp2 C={c} ===")
        r = await run_round(c, queries)
        print(r)
        rows.append(r)

    csv_path = out / "results.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"[exp2] resultados em {csv_path}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Implementar `plot_exp2.py`**

```python
"""Plot Exp 2: throughput agregado e latência percentil."""
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    rows = []
    with Path("data/exp2/results.csv").open() as f:
        for r in csv.DictReader(f):
            rows.append({k: float(v) if v not in ("", "None") else None for k, v in r.items()})
    rows.sort(key=lambda x: x["C"])

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    axes[0].plot([r["C"] for r in rows], [r["qps"] for r in rows], "o-")
    axes[0].set_xlabel("Concorrência C")
    axes[0].set_ylabel("Throughput (queries/s)")
    axes[0].set_title("Exp 2 — Throughput agregado")
    axes[0].grid(True)
    axes[0].set_xscale("log", base=2)

    for label, key, color in [("p50", "p50", "tab:blue"), ("p95", "p95", "tab:orange"), ("p99", "p99", "tab:red")]:
        ys = [r[key] for r in rows if r[key] is not None]
        xs = [r["C"] for r in rows if r[key] is not None]
        axes[1].plot(xs, ys, "o-", label=label, color=color)
    axes[1].set_xlabel("Concorrência C")
    axes[1].set_ylabel("Latência (s)")
    axes[1].set_title("Exp 2 — Latência por percentil")
    axes[1].grid(True)
    axes[1].set_xscale("log", base=2)
    axes[1].legend()

    fig.tight_layout()
    out = Path("data/exp2/exp2.png")
    fig.savefig(out, dpi=150)
    print(f"[plot2] salvo em {out}")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Executar**

Run: `docker compose up -d --scale query-worker=6 query-worker`
Run: `uv run python scripts/run_exp2_query_throughput.py`
Run: `uv run python scripts/plot_exp2.py`

Expected: 6 linhas no CSV e gráfico mostrando saturação a partir de algum C.

---

## Task 4: Experimento 4 — Tolerância a falhas (chaos)

**Files:**
- Create: `scripts/run_exp4_chaos.py`
- Create: `scripts/plot_exp4.py`

> Para B4, automatizamos o `chaos_test.sh` do B3 e coletamos métricas durante o experimento.

- [ ] **Step 1: `run_exp4_chaos.py`**

```python
"""
Experimento 4: tolerância a falhas. Mede taxa de erro, fila depth e tempo de recuperação durante 3 cenários.

Cenário 1: kill ingest-worker no meio de indexação de 50 docs.
Cenário 2: kill Ollama por 30s durante carga de queries.
Cenário 3: rajada de 100 queries em 5s.

Coleta métricas Prometheus em data/exp4/timeseries.csv via /api/v1/query_range.
"""
import asyncio
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx


PROM = "http://localhost:9090"
GATEWAY = "http://localhost:8000"


def query_range(metric: str, start: float, end: float, step: int = 5) -> list[tuple[float, float]]:
    r = httpx.get(
        f"{PROM}/api/v1/query_range",
        params={"query": metric, "start": start, "end": end, "step": step},
        timeout=10,
    ).json()
    if not r["data"]["result"]:
        return []
    return [(float(t), float(v)) for t, v in r["data"]["result"][0]["values"]]


def run_scenario_kill_ingest(corpus: Path) -> dict:
    print("\n[chaos] cenário 1: kill ingest-worker-chunk")
    started = time.time()
    # dispara seed em background
    subprocess.Popen(["uv", "run", "python", "scripts/seed_corpus.py", "--corpus", str(corpus)])
    time.sleep(20)
    subprocess.run(["docker", "stop", "rag-ingest-worker-chunk"], check=False)
    time.sleep(5)
    subprocess.run(["docker", "start", "rag-ingest-worker-chunk"], check=False)
    time.sleep(60)
    end = time.time()
    return {"scenario": "kill_ingest", "start": started, "end": end}


def run_scenario_kill_ollama(queries: list[dict]) -> dict:
    print("\n[chaos] cenário 2: kill Ollama por 30s")
    started = time.time()
    # dispara queries em background
    proc = subprocess.Popen(["uv", "run", "python", "scripts/run_exp2_query_throughput.py"])
    time.sleep(10)
    subprocess.run(["docker", "stop", "rag-ollama"], check=False)
    time.sleep(30)
    subprocess.run(["docker", "start", "rag-ollama"], check=False)
    proc.wait(timeout=300)
    return {"scenario": "kill_ollama", "start": started, "end": time.time()}


def run_scenario_burst(queries: list[dict]) -> dict:
    print("\n[chaos] cenário 3: rajada de 100 queries")
    started = time.time()
    async def burst():
        async with httpx.AsyncClient() as c:
            await asyncio.gather(*[
                c.post(f"{GATEWAY}/query", json={"question": q["question"], "top_k": 3}, timeout=180)
                for q in queries[:100]
            ])
    asyncio.run(burst())
    return {"scenario": "burst_100", "start": started, "end": time.time()}


def collect(scenario: dict, name: str) -> Path:
    metrics = {
        "errors_per_s": "sum(rate(rag_errors_total[1m]))",
        "queue_depth_chunks": "rabbitmq_queue_messages{queue=\"ingest.chunks\"}",
        "qps": "sum(rate(rag_throughput_queries_total[1m]))",
    }
    out = Path("data/exp4") / f"{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, q in metrics.items():
        for t, v in query_range(q, scenario["start"], scenario["end"]):
            rows.append({"t": t, "metric": label, "value": v})
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["t", "metric", "value"])
        w.writeheader()
        w.writerows(rows)
    return out


def main():
    queries = [json.loads(l) for l in Path("data/eval_queries.jsonl").read_text().splitlines()]
    s1 = run_scenario_kill_ingest(Path("samples/corpus"))
    collect(s1, "kill_ingest")
    s2 = run_scenario_kill_ollama(queries)
    collect(s2, "kill_ollama")
    s3 = run_scenario_burst(queries)
    collect(s3, "burst")
    print("[exp4] arquivos em data/exp4/")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: `plot_exp4.py`** (3 painéis stacked)

```python
"""Plot Exp 4: timeseries por cenário."""
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt


def load(name: str) -> dict[str, list[tuple[float, float]]]:
    out = {}
    with Path(f"data/exp4/{name}.csv").open() as f:
        for r in csv.DictReader(f):
            out.setdefault(r["metric"], []).append((float(r["t"]), float(r["value"])))
    return out


def main():
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=False)
    for i, scenario in enumerate(["kill_ingest", "kill_ollama", "burst"]):
        data = load(scenario)
        ax = axes[i]
        for metric, series in data.items():
            ts = [t - series[0][0] for t, _ in series]
            ys = [v for _, v in series]
            ax.plot(ts, ys, label=metric)
        ax.set_title(f"Exp 4 — {scenario}")
        ax.set_xlabel("t (s desde início do cenário)")
        ax.set_ylabel("valor")
        ax.legend()
        ax.grid(True)

    fig.tight_layout()
    out = Path("data/exp4/exp4.png")
    fig.savefig(out, dpi=150)
    print(f"[plot4] salvo em {out}")


if __name__ == "__main__":
    sys.exit(main())
```

---

## Task 5: Experimento 3 — Ollama vs vLLM (CONDICIONAL)

**Files:**
- Create: `infra/docker/vllm-compose.override.yml`
- Create: `scripts/run_exp3_ollama_vs_vllm.py`
- Create: `scripts/plot_exp3.py`

> ⚠️ **Condicional:** só execute esta tarefa se ao iniciar o dia 21 todos os critérios de B3 estiverem verdes E os Exp 1, 2 e 4 já estiverem rodando ou completos.

- [ ] **Step 1: `infra/docker/vllm-compose.override.yml`** — sobe vLLM em paralelo na porta 8000 do host (ajuste se conflitar)

```yaml
services:
  vllm:
    image: vllm/vllm-openai:latest
    container_name: rag-vllm
    profiles: ["vllm"]
    ports:
      - "8002:8000"
    environment:
      HUGGING_FACE_HUB_TOKEN: ""
    volumes:
      - vllm_models:/root/.cache/huggingface
    command:
      - "--model=Qwen/Qwen2.5-7B-Instruct-AWQ"
      - "--quantization=awq"
      - "--max-model-len=8192"
      - "--gpu-memory-utilization=0.9"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

volumes:
  vllm_models:
```

> Para subir: `docker compose -f docker-compose.yml -f infra/docker/vllm-compose.override.yml --profile vllm up -d vllm`. **Pare o Ollama do gerador antes** (libera VRAM): `docker stop rag-ollama` (mantém o Ollama de embeddings desligado também — ou sobe um container Ollama separado só para embeddings se quiser cobertura completa; em B4 simplificar).

- [ ] **Step 2: Adaptar query-worker para apontar para vLLM**

Em `.env.local`, troque temporariamente:
```
OLLAMA_URL=http://vllm:8000
GENERATION_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ
```

> **Importante:** o `OllamaClient` usa endpoints `/api/embeddings` e `/api/generate`. vLLM expõe `/v1/embeddings` e `/v1/completions` (OpenAI-compat). Como solução simples para o experimento: criar uma **subclasse** ou **client alternativo** `VllmClient` em `src/shared/vllm_client.py` que faz os ajustes; selecionado via `INFERENCE_BACKEND=ollama|vllm` em config.

Esqueleto de `src/shared/vllm_client.py`:

```python
import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter


class VllmClient:
    def __init__(self, base_url: str, timeout: float = 120.0):
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def embed(self, text: str, model: str) -> list[float]:
        # vLLM AWQ não serve embeddings; manter Ollama para embed durante Exp 3
        raise NotImplementedError("vLLM client neste experimento não serve embeddings.")

    async def generate(self, prompt: str, model: str, options: dict | None = None) -> dict:
        opts = options or {}
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": 1024,
            "temperature": opts.get("temperature", 0.2),
        }
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1, max=8),
            retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=self._timeout) as http:
                    r = await http.post(f"{self._base}/v1/completions", json=payload)
                    r.raise_for_status()
                    j = r.json()
                    return {
                        "text": j["choices"][0]["text"],
                        "tokens_in": j["usage"]["prompt_tokens"],
                        "tokens_out": j["usage"]["completion_tokens"],
                    }
        raise RuntimeError("unreachable")
```

E em `query-worker`, escolha cliente baseado em `settings.inference_backend`:

```python
from src.shared.config import settings
from src.shared.ollama_client import OllamaClient
from src.shared.vllm_client import VllmClient

if settings.inference_backend == "vllm":
    deps.generator = VllmClient(base_url=settings.vllm_url)
else:
    deps.generator = OllamaClient(base_url=settings.ollama_url)
```

(Adicione `inference_backend: str = "ollama"`, `vllm_url: str = "http://vllm:8000"` em `Settings`.)

> Mantém `deps.ollama` para embeddings em qualquer caso.

- [ ] **Step 3: `run_exp3_ollama_vs_vllm.py`**

```python
"""
Exp 3: roda Exp 2 duas vezes — uma com OLLAMA, outra com VLLM — e gera comparativo.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run_exp2(label: str):
    print(f"\n=== Exp 3 — rodada {label} ===")
    subprocess.run(["uv", "run", "python", "scripts/run_exp2_query_throughput.py"], check=True)
    out_dir = Path("data/exp3") / label
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy("data/exp2/results.csv", out_dir / "results.csv")


def main():
    Path("data/exp3").mkdir(parents=True, exist_ok=True)

    # Rodada Ollama (assume INFERENCE_BACKEND=ollama)
    print("[exp3] garantindo INFERENCE_BACKEND=ollama no .env.local")
    run_exp2("ollama")

    print("[exp3] AGORA: pare Ollama-gerador, suba vLLM, troque INFERENCE_BACKEND=vllm")
    print("       e reinicie query-worker. Pressione Enter para continuar...")
    input()

    run_exp2("vllm")
    print("[exp3] CSV em data/exp3/{ollama,vllm}/results.csv")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: `plot_exp3.py`**

```python
"""Plot Exp 3: Ollama vs vLLM, throughput e p95 lado a lado."""
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt


def load(label: str) -> list[dict]:
    rows = []
    with Path(f"data/exp3/{label}/results.csv").open() as f:
        for r in csv.DictReader(f):
            rows.append({k: float(v) if v not in ("", "None") else None for k, v in r.items()})
    rows.sort(key=lambda x: x["C"])
    return rows


def main():
    olm = load("ollama")
    vll = load("vllm")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    axes[0].plot([r["C"] for r in olm], [r["qps"] for r in olm], "o-", label="Ollama")
    axes[0].plot([r["C"] for r in vll], [r["qps"] for r in vll], "s-", label="vLLM")
    axes[0].set_xlabel("Concorrência C"); axes[0].set_ylabel("QPS")
    axes[0].set_title("Exp 3 — Throughput")
    axes[0].set_xscale("log", base=2); axes[0].grid(True); axes[0].legend()

    axes[1].plot([r["C"] for r in olm], [r["p95"] or 0 for r in olm], "o-", label="Ollama p95")
    axes[1].plot([r["C"] for r in vll], [r["p95"] or 0 for r in vll], "s-", label="vLLM p95")
    axes[1].set_xlabel("Concorrência C"); axes[1].set_ylabel("Latência p95 (s)")
    axes[1].set_title("Exp 3 — Latência p95")
    axes[1].set_xscale("log", base=2); axes[1].grid(True); axes[1].legend()

    fig.tight_layout()
    out = Path("data/exp3/exp3.png")
    fig.savefig(out, dpi=150)
    print(f"[plot3] salvo em {out}")


if __name__ == "__main__":
    sys.exit(main())
```

---

## Task 6: Documento técnico (`docs/arquitetura.md`)

**Files:**
- Create: `docs/arquitetura.md` (8–15 páginas)
- Create: `docs/decisoes.md` (ADRs curtas)
- Create: `docs/prompts.md` (apêndice)

- [ ] **Step 1: Estrutura do `docs/arquitetura.md`**

Use este esqueleto e preencha com base no spec, nos resultados experimentais e na evidência coletada nos blocos anteriores. Cada seção deve ter ~1 página.

```markdown
# Tema 5 — RAG Distribuído: Documento Técnico

Equipe: <nomes>
Disciplina: Programação Distribuída e Paralela — CESUPA
Data: 2026-05-25

## Sumário

1. Introdução
2. Arquitetura
3. Fluxos de dados
4. Engenharia de contexto
5. Tolerância a falhas
6. IaC e topologia distribuída
7. Resultados experimentais
8. Discussão e limitações
9. Uso de ferramentas e IA
10. Conclusão
11. Referências
12. Apêndices

## 1. Introdução
- Contexto: engenharia de contexto + harnesses + PDP.
- Tema escolhido (5) e justificativa.
- Domínio do corpus.
- Restrição: ambiente local (sem AWS).

## 2. Arquitetura
- Diagrama (copiar do spec).
- Topologia distribuída (3 PCs via Tailscale).
- Componentes principais (gateway, RabbitMQ, Qdrant, Redis, Ollama, rerank-service, workers, observabilidade).

## 3. Fluxos de dados
- Ingestão em duas filas (paralelismo de dados).
- Atendimento de query (paralelismo de tarefas) com cache em duas camadas e re-ranking.

## 4. Engenharia de contexto
- Prompts versionados (referenciar `prompts/` e apêndice).
- Estratégia de chunking (recursivo com overlap).
- Re-ranking cross-encoder (bge-reranker-v2-m3).
- Montagem dentro do orçamento de tokens.
- Function calling (cite_source).
- Memória de sessão.

## 5. Tolerância a falhas
- Retry com backoff (tenacity).
- DLQ via x-dead-letter-exchange.
- Fallback degraded mode.
- Healthchecks.
- Resultados do Exp 4.

## 6. IaC e topologia distribuída
- Justificativa da substituição de AWS por equivalentes locais (tabela do spec).
- Terraform com provider docker.
- Ansible playbooks (bootstrap + deploy).
- Tailscale como rede privada.

## 7. Resultados experimentais
- Exp 1 — Speedup da indexação (gráfico + análise).
- Exp 2 — Throughput vs concorrência (gráfico + análise).
- (Se aplicável) Exp 3 — Ollama vs vLLM (gráfico + tese).
- Exp 4 — Tolerância a falhas (timeseries + análise).

## 8. Discussão e limitações
- Trade-offs observados.
- O que funcionou; o que não funcionou.
- Limitações (sem hybrid search, eval limitado, sem multi-tenancy).

## 9. Uso de ferramentas e IA
- Resumo da seção `docs/USO_DE_IA.md`.

## 10. Conclusão
- Aprendizados.
- Próximos passos.

## 11. Referências
- Anthropic. *Engineering with Claude*.
- vLLM team. PagedAttention paper (arXiv:2309.06180).
- Qdrant docs.
- RabbitMQ Reliability Guide.
- Tailscale docs.
- ... (preencher com o que foi consultado)

## 12. Apêndices
- A. Diagrama de arquitetura (alta resolução).
- B. Prompts versionados (link para `docs/prompts.md`).
- C. Saída completa do `make smoke`.
- D. Tabelas com CSVs dos experimentos.
```

- [ ] **Step 2: `docs/decisoes.md` (ADRs em 1 parágrafo cada)**

```markdown
# Architecture Decision Records

## ADR-001: Tema 5 (RAG distribuído)
**Decisão:** escolhemos o Tema 5 entre os 8 disponíveis.
**Razão:** o domínio RAG combina paralelismo de dados (indexação) com paralelismo de tarefas (atendimento), cobrindo dois ângulos da disciplina simultaneamente. Cache distribuído entra naturalmente.

## ADR-002: Ambiente local sem AWS
**Decisão:** rodar tudo em 3 PCs físicos via Tailscale, em vez de AWS Academy.
**Razão:** evitar custos e ter controle total da infraestrutura — alinhado com a Seção 7 do enunciado ("Plano B Final: Execução Local").

## ADR-003: RabbitMQ em vez de Redis Streams
**Decisão:** RabbitMQ.
**Razão:** DLQ first-class, vocabulário próximo de SQS/SNS, padrões clássicos de mensageria mais idiomáticos para a disciplina.

## ADR-004: Ollama na linha-base, vLLM no experimento
**Decisão:** Ollama para o pipeline; vLLM em experimento condicional ao final.
**Razão:** Ollama é trivial de subir; vLLM tem continuous batching, ideal para a análise pedida no bônus.

## ADR-005: Qdrant em vez de Chroma/pgvector
**Decisão:** Qdrant.
**Razão:** payload filters, dashboard built-in, performance superior em benchmarks abertos.

## ADR-006: Terraform + Ansible em vez de só Compose
**Decisão:** os dois.
**Razão:** Ansible provisiona os hosts (Docker, Tailscale, NVIDIA toolkit); Terraform descreve os containers de cada host. Cumpre formalmente o pedido do PDF e demonstra IaC didaticamente.
```

- [ ] **Step 3: `docs/prompts.md` (apêndice de prompts)**

```markdown
# Apêndice — Prompts Versionados

## system_qa_pt.md (versão 0.2.0-b2)

```
[colar conteúdo de prompts/system_qa_pt.md]
```

## system_qa_en.md (versão 0.2.0-b2)

```
[colar conteúdo de prompts/system_qa_en.md]
```

## user_qa_template.md

```
[colar conteúdo]
```

## tools/cite_source.json

```json
[colar conteúdo]
```
```

- [ ] **Step 4: Execução**

Cada integrante escreve a seção do doc técnico correspondente à sua trilha (A → §2, §6; B → §3, §4, §5; C → §7, §8). Compilar em B5.

---

## Task 7: Marco luz-verde do B4

- [ ] **Step 1: Critérios de aceite**

- ✅ `data/eval_queries.jsonl` com ≥30 queries.
- ✅ `data/exp1/results.csv` + `data/exp1/exp1.png` gerados.
- ✅ `data/exp2/results.csv` + `data/exp2/exp2.png` gerados.
- ✅ `data/exp4/{kill_ingest,kill_ollama,burst}.csv` + `data/exp4/exp4.png` gerados.
- ✅ (Condicional) `data/exp3/exp3.png` gerado.
- ✅ `docs/arquitetura.md` em rascunho avançado (todas as seções com conteúdo).
- ✅ `docs/decisoes.md` e `docs/prompts.md` completos.

- [ ] **Step 2: Capturar evidências**

Adicione todos os PNGs ao apêndice do doc técnico. Salve uma cópia das saídas dos scripts em `data/exp{1,2,3,4}/log.txt` para reprodutibilidade.

Quando todos passarem: **B4 concluído**.
