"""Experimento 1 — speedup da indexação variando N workers de chunk (Modo 2).

Mede o tempo de indexação do corpus inteiro para um dado número de
``ingest-worker-chunk`` ativos e registra uma linha em ``data/exp1/results.csv``.

Diferente do rascunho do plano B4, este runner **não** usa ``docker compose
--scale``. Em Modo 2 a stack sobe via **Terraform** (``infra/terraform``, módulo
``worker``), que é o control plane dos containers — não o Compose. O número de
chunk-workers é a variável ``chunk_worker_count`` do Terraform, ajustada por host
worker entre os apply:

  terraform -chdir=infra/terraform apply -var-file=envs/pc2.tfvars -var chunk_worker_count=4
  # ou edite chunk_worker_count no .tfvars e: make tf-apply HOST=pc2

Você roda **uma vez por N**, informando ``--n`` com o valor de
``chunk_worker_count`` ativo no momento (o ``--n`` é só o rótulo gravado no CSV;
quem muda a topologia é o ``terraform apply``). O CSV acumula as linhas e o
``plot_exp1.py`` deduplica por N (último vence).

Todos os acessos de estado (purge das filas, reset da collection, contagem de
pontos) são via HTTP contra o PC1, então o script roda igual em Modo 1
(``--host localhost``) e Modo 2 (``--host <IP-Tailscale-do-PC1>``).

Uso (Modo 2, N=4 chunk-workers ativos):
  uv run python scripts/run_exp1_indexing_speedup.py --host 100.x.y.z --n 4

Fluxo por execução:
  1. purga ``ingest.documents`` + ``ingest.chunks`` (RabbitMQ mgmt API)
  2. recria a collection Qdrant ``se_corpus`` (768d, Cosine) — zera os pontos
  3. submete o corpus via ``POST /ingest`` no gateway
  4. espera ``points_count`` estabilizar e mede o tempo decorrido
  5. anexa ``{N, elapsed_s, chunks, chunks_per_s}`` ao CSV

Cada execução também espelha o stdout em ``data/exp1/log.txt`` (append).
"""

import argparse
import base64
import csv
import os
import sys
import time
from pathlib import Path
from typing import Any, TextIO, cast

import httpx

SOURCE_TYPES = {
    ".pdf": "pdf",
    ".md": "md",
    ".markdown": "md",
    ".html": "html",
    ".htm": "html",
}

EMBEDDING_DIM = 768
COLLECTION = "se_corpus"


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


def iter_corpus_files(corpus: Path) -> list[Path]:
    return sorted(
        path for path in corpus.rglob("*") if path.is_file() and path.suffix.lower() in SOURCE_TYPES
    )


def purge_queues(rabbitmq_mgmt: str, user: str, password: str) -> None:
    """Esvazia as filas de ingestão via RabbitMQ Management API (vhost ``/``)."""
    for queue in ("ingest.documents", "ingest.chunks"):
        url = f"{rabbitmq_mgmt}/api/queues/%2F/{queue}/contents"
        try:
            resp = httpx.delete(url, auth=(user, password), timeout=10)
            print(f"[exp1] purge {queue}: HTTP {resp.status_code}")
        except httpx.HTTPError as exc:
            print(f"[exp1] purge {queue} falhou (segue): {exc}")


def reset_collection(qdrant: str) -> None:
    """Dropa e recria a collection — reseta ``points_count`` para 0.

    Recria com a mesma config do worker (``ensure_qdrant_collection``): 768
    dimensões, distância Cosine. Como o worker checa existência antes de criar,
    não há conflito no próximo boot.
    """
    try:
        httpx.delete(f"{qdrant}/collections/{COLLECTION}", timeout=15)
    except httpx.HTTPError as exc:
        print(f"[exp1] delete collection falhou (segue): {exc}")
    resp = httpx.put(
        f"{qdrant}/collections/{COLLECTION}",
        json={"vectors": {"size": EMBEDDING_DIM, "distance": "Cosine"}},
        timeout=15,
    )
    print(f"[exp1] recreate collection: HTTP {resp.status_code}")
    time.sleep(2)


def submit_corpus(gateway: str, files: list[Path], timeout: float) -> int:
    submitted = 0
    with httpx.Client(base_url=gateway, timeout=timeout) as client:
        for path in files:
            source_type = SOURCE_TYPES[path.suffix.lower()]
            content_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            try:
                resp = client.post(
                    "/ingest",
                    json={
                        "filename": path.name,
                        "content_b64": content_b64,
                        "source_type": source_type,
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"[exp1] falha ingest {path.name}: {exc}")
                continue
            submitted += 1
    return submitted


def points_count(qdrant: str) -> int:
    resp = httpx.get(f"{qdrant}/collections/{COLLECTION}", timeout=5)
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return int(data["result"]["points_count"])


def wait_for_indexing(
    qdrant: str, timeout: float, stable_checks: int, interval: float
) -> tuple[float, int]:
    """Espera ``points_count`` estabilizar (sem crescer por N polls) ou estourar.

    Returns
    -------
    tuple of (float, int)
        Tempo decorrido em segundos e a contagem final de pontos.
    """
    started = time.perf_counter()
    last_count = -1
    stable_for = 0
    while time.perf_counter() - started < timeout:
        try:
            count = points_count(qdrant)
        except httpx.HTTPError:
            time.sleep(interval)
            continue
        if count == last_count and count > 0:
            stable_for += 1
            if stable_for >= stable_checks:
                break
        else:
            stable_for = 0
            last_count = count
        time.sleep(interval)
    return time.perf_counter() - started, max(last_count, 0)


def append_row(csv_path: Path, row: dict[str, float]) -> None:
    fieldnames = ["N", "elapsed_s", "chunks", "chunks_per_s"]
    is_new = not csv_path.exists()
    with csv_path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, required=True, help="chunk-workers ativos agora")
    parser.add_argument("--corpus", type=Path, default=Path("samples/corpus"))
    parser.add_argument("--host", default=os.environ.get("RAG_EXP_HOST", "localhost"))
    parser.add_argument("--gateway-url", default=os.environ.get("RAG_GATEWAY_URL"))
    parser.add_argument("--qdrant-url", default=os.environ.get("RAG_QDRANT_URL"))
    parser.add_argument("--rabbitmq-mgmt-url", default=os.environ.get("RAG_RABBITMQ_MGMT_URL"))
    parser.add_argument("--rabbitmq-user", default=os.environ.get("RAG_RABBITMQ_USER", "guest"))
    parser.add_argument("--rabbitmq-pass", default=os.environ.get("RAG_RABBITMQ_PASS", "guest"))
    parser.add_argument("--timeout", type=float, default=1200.0, help="teto de espera (s)")
    parser.add_argument("--stable-checks", type=int, default=5)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--ingest-timeout", type=float, default=30.0)
    args = parser.parse_args()

    gateway = args.gateway_url or f"http://{args.host}:8000"
    qdrant = args.qdrant_url or f"http://{args.host}:6333"
    rabbitmq_mgmt = args.rabbitmq_mgmt_url or f"http://{args.host}:15672"

    out = Path("data/exp1")
    original_stdout = sys.stdout
    tee = _Tee(original_stdout, out / "log.txt")
    sys.stdout = cast(TextIO, tee)
    print(f"\n# === run {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    try:
        if not args.corpus.exists():
            print(f"[exp1] corpus inexistente: {args.corpus}")
            return 2

        files = iter_corpus_files(args.corpus)
        if not files:
            print(f"[exp1] nenhum arquivo suportado em {args.corpus}")
            return 2

        print(f"\n=== Exp1 N={args.n} | {len(files)} arquivos | gateway={gateway} ===")
        purge_queues(rabbitmq_mgmt, args.rabbitmq_user, args.rabbitmq_pass)
        reset_collection(qdrant)

        submitted = submit_corpus(gateway, files, args.ingest_timeout)
        print(f"[exp1] submetidos {submitted}/{len(files)} arquivos; medindo indexação")

        elapsed, count = wait_for_indexing(qdrant, args.timeout, args.stable_checks, args.interval)
        chunks_per_s = count / elapsed if elapsed > 0 else 0.0
        print(f"[exp1] N={args.n} elapsed={elapsed:.1f}s chunks={count} cps={chunks_per_s:.2f}")

        append_row(
            out / "results.csv",
            {
                "N": float(args.n),
                "elapsed_s": round(elapsed, 1),
                "chunks": float(count),
                "chunks_per_s": round(chunks_per_s, 2),
            },
        )
        print(f"[exp1] linha anexada em {out / 'results.csv'}")
        return 0
    finally:
        sys.stdout = original_stdout
        tee.close()


if __name__ == "__main__":
    raise SystemExit(main())
