"""Plot standalone do Exp 2 — lê ``data/exp2/results.csv`` e gera ``data/exp2/exp2.png``.

Script à parte (independente do runner): roda sozinho sobre o CSV já coletado.
Dois painéis lado a lado: throughput (QPS) × concorrência e latência
p50/p95/p99 × concorrência, com o teto de timeout do gateway (~120 s, a partir
do qual a query cai em *degraded mode*) marcado por uma linha tracejada.

Uso:
  uv run python scripts/plotar_exp2.py
"""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CSV_PATH = Path("data/exp2/results.csv")
OUT_PATH = Path("data/exp2/exp2.png")
GATEWAY_TIMEOUT_S = 120.0


def load_rows(path: Path) -> list[dict[str, float | None]]:
    rows: list[dict[str, float | None]] = []
    with path.open() as handle:
        for raw in csv.DictReader(handle):
            rows.append({k: (float(v) if v not in ("", "None") else None) for k, v in raw.items()})
    rows.sort(key=lambda r: r["C"] or 0.0)
    return rows


def main() -> int:
    if not CSV_PATH.exists():
        print(f"[plotar-exp2] CSV inexistente: {CSV_PATH} — rode run_exp2 primeiro.")
        return 2

    rows = load_rows(CSV_PATH)
    cs = [r["C"] for r in rows]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # Painel 1 — throughput agregado
    axes[0].plot(cs, [r["qps"] for r in rows], "o-", color="tab:green")
    axes[0].set_xlabel("Concorrência C (clientes simultâneos)")
    axes[0].set_ylabel("Throughput (queries/s)")
    axes[0].set_title("Exp 2 — Throughput agregado")
    axes[0].set_xscale("log", base=2)
    axes[0].grid(visible=True)

    # Painel 2 — latência por percentil, com o teto de timeout do gateway
    for label, color in (("p50", "tab:blue"), ("p95", "tab:orange"), ("p99", "tab:red")):
        xs = [r["C"] for r in rows if r[label] is not None]
        ys = [r[label] for r in rows if r[label] is not None]
        if xs:
            axes[1].plot(xs, ys, "o-", label=label, color=color)
    axes[1].axhline(
        GATEWAY_TIMEOUT_S,
        color="gray",
        linestyle="--",
        alpha=0.7,
        label=f"timeout gateway (~{GATEWAY_TIMEOUT_S:.0f}s → degraded)",
    )
    axes[1].set_xlabel("Concorrência C (clientes simultâneos)")
    axes[1].set_ylabel("Latência (s)")
    axes[1].set_title("Exp 2 — Latência por percentil")
    axes[1].set_xscale("log", base=2)
    axes[1].grid(visible=True)
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(OUT_PATH, dpi=150)
    print(f"[plotar-exp2] salvo em {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
