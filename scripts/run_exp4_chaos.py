"""Experimento 4 — tolerância a falhas (chaos test) em Modo 2.

Gera carga contra o sistema e injeta falhas controladas, coletando séries
temporais do Prometheus (taxa de erro, QPS, profundidade de fila) durante cada
cenário. Um CSV por cenário em ``data/exp4/<cenario>.csv``.

Cenários:
  - ``kill_ollama``      — sob carga de queries, derruba o Ollama (PC1) por uma
                           janela e religa; mede erro e recuperação.
  - ``kill_chunk_worker``— sob ingestão do corpus, derruba um ``ingest-worker-chunk``
                           e religa; mede acúmulo/escoamento da fila ``ingest.chunks``.
  - ``burst``            — rajada de queries concorrentes sem matar nada; mede
                           saturação e erro sob pico.

Modo 2: o script roda de qualquer máquina. Aponte ``--host`` para o PC1 (gateway,
Prometheus, etc.) e use ``--docker-pc1`` / ``--docker-worker`` para alcançar o
host certo de cada container. Exemplos (via docker context SSH):
  --docker-pc1   "docker -H ssh://pc1-davi"
  --docker-worker "docker -H ssh://pc2-jm"
Em Modo 1 ambos são apenas ``docker`` (default).

Uso:
  uv run python scripts/run_exp4_chaos.py --host 100.x.y.z
  uv run python scripts/run_exp4_chaos.py --scenarios burst,kill_ollama

Cada execução também espelha o stdout em ``data/exp4/log.txt`` (append).
"""

import argparse
import asyncio
import base64
import contextlib
import csv
import json
import os
import random
import shlex
import sys
import time
from pathlib import Path
from typing import Any, TextIO, cast

import httpx

SOURCE_TYPES = {".pdf": "pdf", ".md": "md", ".markdown": "md", ".html": "html", ".htm": "html"}

METRICS = {
    "errors_per_s": "sum(rate(rag_errors_total[1m]))",
    "qps": "sum(rate(rag_throughput_queries_total[1m]))",
    "queue_chunks": 'rabbitmq_queue_messages_ready{queue="ingest.chunks"}',
    "ollama_inflight": "rag_ollama_inflight_requests",
}


class _Tee:
    """Espelha tudo escrito em stdout também num arquivo de log (append)."""

    def __init__(self, stream: TextIO, log_path: Path) -> None:
        self._stream = stream
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = log_path.open("a", encoding="utf-8")

    def write(self, data: str) -> int:
        self._stream.write(data)
        self._log.write(data)
        return len(data)

    def flush(self) -> None:
        self._stream.flush()
        self._log.flush()

    def close(self) -> None:
        self._log.close()


def load_queries(path: Path) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def iter_corpus_files(corpus: Path) -> list[Path]:
    return sorted(p for p in corpus.rglob("*") if p.is_file() and p.suffix.lower() in SOURCE_TYPES)


async def docker_action(docker_cmd: str, action: str, container: str) -> None:
    """Roda ``<docker_cmd> <action> <container>`` (start/stop), sem bloquear o loop."""
    argv = [*shlex.split(docker_cmd), action, container]
    print(f"[chaos] {' '.join(argv)}")
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()


async def query_load(
    gateway: str, queries: list[dict[str, str]], duration: float, concurrency: int, top_k: int
) -> None:
    """Mantém ``concurrency`` queries em voo contra o gateway por ``duration`` s."""
    deadline = time.perf_counter() + duration

    async def worker(client: httpx.AsyncClient) -> None:
        while time.perf_counter() < deadline:
            question = random.choice(queries)["question"]
            with contextlib.suppress(httpx.HTTPError):
                await client.post(
                    f"{gateway}/query",
                    json={"question": question, "top_k": top_k},
                    timeout=180,
                )

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(worker(client) for _ in range(concurrency)))


def build_ingest_payloads(files: list[Path]) -> list[dict[str, str]]:
    """Lê os arquivos (IO síncrono) e monta os corpos do ``/ingest``."""
    return [
        {
            "filename": path.name,
            "content_b64": base64.b64encode(path.read_bytes()).decode("ascii"),
            "source_type": SOURCE_TYPES[path.suffix.lower()],
        }
        for path in files
    ]


async def ingest_load(gateway: str, payloads: list[dict[str, str]]) -> None:
    """Submete os corpos pré-montados via ``/ingest`` (concorrência modesta)."""
    sem = asyncio.Semaphore(4)

    async def submit(client: httpx.AsyncClient, payload: dict[str, str]) -> None:
        async with sem:
            with contextlib.suppress(httpx.HTTPError):
                await client.post(f"{gateway}/ingest", json=payload, timeout=30)

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(submit(client, p) for p in payloads))


def query_range(
    prom: str, expr: str, start: float, end: float, step: int
) -> list[tuple[float, float]]:
    try:
        resp = httpx.get(
            f"{prom}/api/v1/query_range",
            params={"query": expr, "start": start, "end": end, "step": step},
            timeout=15,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
    except httpx.HTTPError as exc:
        print(f"[chaos] prometheus falhou para '{expr}': {exc}")
        return []
    series = data["data"]["result"]
    if not series:
        return []
    return [(float(ts), float(val)) for ts, val in series[0]["values"]]


def collect(prom: str, name: str, start: float, end: float, step: int) -> Path:
    out = Path("data/exp4") / f"{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, float | str]] = []
    for label, expr in METRICS.items():
        for ts, val in query_range(prom, expr, start, end, step):
            rows.append({"t": ts, "metric": label, "value": val})
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["t", "metric", "value"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[chaos] {name}: {len(rows)} pontos em {out}")
    return out


async def scenario_kill_ollama(args: argparse.Namespace, gateway: str, prom: str) -> None:
    print("\n[chaos] cenário kill_ollama")
    queries = load_queries(args.queries_file)
    start = time.time()
    load = asyncio.create_task(query_load(gateway, queries, duration=130, concurrency=4, top_k=5))
    await asyncio.sleep(20)
    await docker_action(args.docker_pc1, "stop", args.ollama_container)
    await asyncio.sleep(30)
    await docker_action(args.docker_pc1, "start", args.ollama_container)
    await load
    end = time.time()
    collect(prom, "kill_ollama", start, end, args.step)


async def scenario_kill_chunk_worker(args: argparse.Namespace, gateway: str, prom: str) -> None:
    print("\n[chaos] cenário kill_chunk_worker")
    if not args.corpus.exists():
        print(f"[chaos] corpus inexistente ({args.corpus}); pulando cenário.")
        return
    payloads = build_ingest_payloads(iter_corpus_files(args.corpus))
    start = time.time()
    load = asyncio.create_task(ingest_load(gateway, payloads))
    await asyncio.sleep(15)
    await docker_action(args.docker_worker, "stop", args.chunk_worker_container)
    await asyncio.sleep(20)
    await docker_action(args.docker_worker, "start", args.chunk_worker_container)
    await load
    await asyncio.sleep(30)  # deixa a fila escoar para a série mostrar a recuperação
    end = time.time()
    collect(prom, "kill_chunk_worker", start, end, args.step)


async def scenario_burst(args: argparse.Namespace, gateway: str, prom: str) -> None:
    print("\n[chaos] cenário burst")
    queries = load_queries(args.queries_file)
    start = time.time()
    await query_load(gateway, queries, duration=30, concurrency=50, top_k=3)
    await asyncio.sleep(20)  # cauda de drenagem
    end = time.time()
    collect(prom, "burst", start, end, args.step)


SCENARIOS = {
    "kill_ollama": scenario_kill_ollama,
    "kill_chunk_worker": scenario_kill_chunk_worker,
    "burst": scenario_burst,
}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("RAG_EXP_HOST", "localhost"))
    parser.add_argument("--gateway-url", default=os.environ.get("RAG_GATEWAY_URL"))
    parser.add_argument("--prom-url", default=os.environ.get("RAG_PROM_URL"))
    parser.add_argument("--scenarios", default="kill_ollama,kill_chunk_worker,burst")
    parser.add_argument("--queries-file", type=Path, default=Path("data/eval_queries.jsonl"))
    parser.add_argument("--corpus", type=Path, default=Path("samples/corpus"))
    parser.add_argument("--docker-pc1", default=os.environ.get("RAG_DOCKER_PC1", "docker"))
    parser.add_argument("--docker-worker", default=os.environ.get("RAG_DOCKER_WORKER", "docker"))
    parser.add_argument("--ollama-container", default="rag-ollama")
    parser.add_argument("--chunk-worker-container", default="rag-ingest-worker-chunk")
    parser.add_argument("--step", type=int, default=5, help="resolução do query_range (s)")
    args = parser.parse_args()

    gateway = args.gateway_url or f"http://{args.host}:8000"
    prom = args.prom_url or f"http://{args.host}:9090"

    out = Path("data/exp4")
    original_stdout = sys.stdout
    tee = _Tee(original_stdout, out / "log.txt")
    sys.stdout = cast(TextIO, tee)
    print(f"\n# === run {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    try:
        if not args.queries_file.exists():
            print(f"[chaos] queries inexistentes: {args.queries_file}")
            return 2

        selected = [s.strip() for s in args.scenarios.split(",") if s.strip()]
        unknown = [s for s in selected if s not in SCENARIOS]
        if unknown:
            print(f"[chaos] cenários desconhecidos: {unknown}; válidos: {list(SCENARIOS)}")
            return 2

        for name in selected:
            await SCENARIOS[name](args, gateway, prom)

        print("\n[chaos] arquivos em data/exp4/ — rode plot_exp4.py para gerar o gráfico")
        return 0
    finally:
        sys.stdout = original_stdout
        tee.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
