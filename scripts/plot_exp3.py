"""Plot do Exp 3: Ollama vs vLLM — throughput e latência p95 lado a lado.

Lê ``data/exp3/{ollama,vllm}/results.csv`` (gerados por
``run_exp3_ollama_vs_vllm.py``) e salva ``data/exp3/exp3.png``. A tese a ler no
gráfico: as curvas de QPS divergem conforme a concorrência C sobe — o
continuous batching do vLLM segue escalando onde o Ollama satura.
"""

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt


def load(label: str) -> list[dict[str, float | None]]:
    """Carrega o CSV de uma rodada, convertendo células vazias/None em ``None``."""
    rows: list[dict[str, float | None]] = []
    with Path(f"data/exp3/{label}/results.csv").open() as handle:
        for row in csv.DictReader(handle):
            rows.append({k: (float(v) if v not in ("", "None") else None) for k, v in row.items()})
    rows.sort(key=lambda r: r["C"] or 0.0)
    return rows


def main() -> int:
    olm = load("ollama")
    vll = load("vllm")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    axes[0].plot([r["C"] for r in olm], [r["qps"] for r in olm], "o-", label="Ollama")
    axes[0].plot([r["C"] for r in vll], [r["qps"] for r in vll], "s-", label="vLLM")
    axes[0].set_xlabel("Concorrência C")
    axes[0].set_ylabel("QPS")
    axes[0].set_title("Exp 3 — Throughput")
    axes[0].set_xscale("log", base=2)
    axes[0].grid(True)
    axes[0].legend()

    axes[1].plot([r["C"] for r in olm], [r["p95"] or 0 for r in olm], "o-", label="Ollama p95")
    axes[1].plot([r["C"] for r in vll], [r["p95"] or 0 for r in vll], "s-", label="vLLM p95")
    axes[1].set_xlabel("Concorrência C")
    axes[1].set_ylabel("Latência p95 (s)")
    axes[1].set_title("Exp 3 — Latência p95")
    axes[1].set_xscale("log", base=2)
    axes[1].grid(True)
    axes[1].legend()

    fig.tight_layout()
    out = Path("data/exp3/exp3.png")
    fig.savefig(out, dpi=150)
    print(f"[plot3] salvo em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
