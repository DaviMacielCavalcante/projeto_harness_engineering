"""Experimento 2 — throughput de queries vs concorrência (Modo 2).

Para cada nível de concorrência C, dispara um lote de queries contra o gateway
com no máximo C em voo e mede throughput agregado (QPS), latência p50/p95/p99 e
taxa de erro. Escreve ``data/exp2/results.csv`` (uma linha por C).

É mode-agnostic: só fala HTTP com o gateway. Em Modo 2 aponte ``--host`` para o
IP Tailscale do PC1; o pool de ``query-worker`` é fixo (controlado fora daqui,
por host) durante toda a varredura de C.

Uso:
  uv run python scripts/run_exp2_query_throughput.py --host 100.x.y.z
  uv run python scripts/run_exp2_query_throughput.py --c-values 1,4,16 --n-queries 100
"""

import argparse
import asyncio
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path

import httpx


def load_queries(path: Path, n_queries: int) -> list[dict[str, str]]:
    """Carrega as queries de eval e repete a lista até atingir ``n_queries``."""
    base: list[dict[str, str]] = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                base.append(json.loads(line))
    if not base:
        return []
    out: list[dict[str, str]] = []
    while len(out) < n_queries:
        out.extend(base)
    return out[:n_queries]


async def run_query(
    client: httpx.AsyncClient, gateway: str, question: str, top_k: int
) -> tuple[float, bool]:
    started = time.perf_counter()
    try:
        resp = await client.post(f"{gateway}/query", json={"question": question, "top_k": top_k})
        ok = resp.status_code == 200
    except httpx.HTTPError:
        ok = False
    return time.perf_counter() - started, ok


async def run_round(
    gateway: str, concurrency: int, queries: list[dict[str, str]], top_k: int, client_timeout: float
) -> dict[str, float | None]:
    sem = asyncio.Semaphore(concurrency)

    async def gated(client: httpx.AsyncClient, question: str) -> tuple[float, bool]:
        async with sem:
            return await run_query(client, gateway, question, top_k)

    async with httpx.AsyncClient(timeout=client_timeout) as client:
        started = time.perf_counter()
        results = await asyncio.gather(*(gated(client, q["question"]) for q in queries))
        total = time.perf_counter() - started

    latencies = sorted(latency for latency, ok in results if ok)
    errors = sum(1 for _, ok in results if not ok)
    qps = len(queries) / total if total > 0 else 0.0
    return {
        "C": float(concurrency),
        "total_s": round(total, 2),
        "qps": round(qps, 2),
        "p50": round(statistics.median(latencies), 3) if latencies else None,
        "p95": round(statistics.quantiles(latencies, n=20)[18], 3)
        if len(latencies) >= 20
        else None,
        "p99": round(statistics.quantiles(latencies, n=100)[98], 3)
        if len(latencies) >= 100
        else None,
        "error_rate": round(errors / len(queries), 3) if queries else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("RAG_EXP_HOST", "localhost"))
    parser.add_argument("--gateway-url", default=os.environ.get("RAG_GATEWAY_URL"))
    parser.add_argument("--queries-file", type=Path, default=Path("data/eval_queries.jsonl"))
    parser.add_argument("--c-values", default="1,2,4,8,16,32")
    parser.add_argument("--n-queries", type=int, default=200)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    gateway = args.gateway_url or f"http://{args.host}:8000"

    if not args.queries_file.exists():
        print(f"[exp2] queries inexistentes: {args.queries_file}")
        return 2

    queries = load_queries(args.queries_file, args.n_queries)
    if not queries:
        print(f"[exp2] nenhuma query em {args.queries_file}")
        return 2

    c_values = [int(c) for c in args.c_values.split(",") if c.strip()]
    out = Path("data/exp2")
    out.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, float | None]] = []
    for concurrency in c_values:
        print(f"\n=== Exp2 C={concurrency} | {len(queries)} queries | gateway={gateway} ===")
        row = asyncio.run(run_round(gateway, concurrency, queries, args.top_k, args.timeout))
        print(row)
        rows.append(row)

    csv_path = out / "results.csv"
    fieldnames = ["C", "total_s", "qps", "p50", "p95", "p99", "error_rate"]
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[exp2] resultados em {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
