"""Smoke test ponta-a-ponta do B1.

Exercita o pipeline inteiro pela primeira vez de verdade: gateway HTTP →
RabbitMQ → ingest-worker → Ollama/Qdrant → query-worker → resposta com
citação. mypy/ruff não validam isto; só rodar contra a stack subida valida.

Pré-requisitos:
  1. ``make dev`` (sobe os containers do Modo 1)
  2. Modelos puxados:
       make pull-models                       # GPU (qwen2.5:7b-instruct)
       make pull-models MODEL=llama3.2:1b     # CPU

Uso:
  uv run python scripts/smoke_test.py [--question "..."] [--file samples/exemplo.pdf]

Códigos de saída: 0 = OK, 1 = falha de conteúdo (resposta vazia),
2 = erro de pré-condição (arquivo não existe).
"""

import argparse
import base64
import sys
import time
from pathlib import Path

import httpx

GATEWAY = "http://localhost:8000"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="samples/ap_es_v1.pdf")
    parser.add_argument("--question", default="Sobre o que fala este documento?")
    parser.add_argument("--wait", type=float, default=30.0, help="segundos para indexação")
    args = parser.parse_args()

    if not Path(args.file).exists():
        print("PDF inexistente.", file=sys.stderr)
        return 2

    resp = httpx.get(url=f"{GATEWAY}/health", timeout=5)

    resp.raise_for_status()

    assert resp.json() == {"status": "ok"}

    print("[smoke] health OK")

    pdf_file = Path(args.file).read_bytes()

    content_b64 = base64.b64encode(pdf_file).decode()

    source_type = "pdf" if Path(args.file).suffix.lower() == ".pdf" else "md"

    resp = httpx.post(
        url=f"{GATEWAY}/ingest",
        timeout=10,
        json={
            "filename": Path(args.file).name,
            "content_b64": content_b64,
            "source_type": source_type,
        },
    )

    resp.raise_for_status()

    ingest = resp.json()

    print(ingest["doc_id"], ingest["correlation_id"])

    print(f"[smoke] aguardando {args.wait}s")

    time.sleep(args.wait)

    started = time.perf_counter()

    resp = httpx.post(
        url=f"{GATEWAY}/query", timeout=180, json={"question": args.question, "top_k": 3}
    )

    resp.raise_for_status()

    data = resp.json()

    elapsed_time = time.perf_counter() - started

    print(
        f"elapsed: {elapsed_time}",
        data["latency_ms"],
        data["usage"]["tokens_in"],
        data["usage"]["tokens_out"],
        len(data["citations"]),
        data["answer"],
    )

    if not data["citations"]:
        print("[smoke] AVISO: resposta sem citações")
    else:
        for c in data["citations"]:
            print(f"{c['source']}, {c.get('page')}")

    if data["answer"].strip() == "":
        print("[smoke] FALHA: resposta vazia.", file=sys.stderr)
        return 1
    else:
        print("[smoke] OK")
        return 0


if __name__ == "__main__":
    sys.exit(main())
