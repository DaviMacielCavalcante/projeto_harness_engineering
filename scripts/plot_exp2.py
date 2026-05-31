"""Plot do Exp 2 — throughput agregado e latência por percentil.

Lê ``data/exp2/results.csv`` e gera ``data/exp2/exp2.png`` com dois painéis:
QPS(C) e p50/p95/p99(C), ambos em eixo-x log base 2 (concorrência geométrica).

Uso:
  uv run python scripts/plot_exp2.py
"""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_rows(csv_path: Path) -> list[dict[str, float | None]]:
    rows: list[dict[str, float | None]] = []
    with csv_path.open() as handle:
        for raw in csv.DictReader(handle):
            rows.append({k: (float(v) if v not in ("", "None") else None) for k, v in raw.items()})
    rows.sort(key=lambda r: r["C"] or 0.0)
    return rows


def main() -> int:
    csv_path = Path("data/exp2/results.csv")
    if not csv_path.exists():
        print(f"[plot2] CSV inexistente: {csv_path} — rode run_exp2 primeiro.")
        return 2

    rows = load_rows(csv_path)
    cs = [r["C"] for r in rows]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    axes[0].plot(cs, [r["qps"] for r in rows], "o-")
    axes[0].set_xlabel("Concorrência C")
    axes[0].set_ylabel("Throughput (queries/s)")
    axes[0].set_title("Exp 2 — Throughput agregado")
    axes[0].set_xscale("log", base=2)
    axes[0].grid(visible=True)

    for label, color in (("p50", "tab:blue"), ("p95", "tab:orange"), ("p99", "tab:red")):
        xs = [r["C"] for r in rows if r[label] is not None]
        ys = [r[label] for r in rows if r[label] is not None]
        if xs:
            axes[1].plot(xs, ys, "o-", label=label, color=color)
    axes[1].set_xlabel("Concorrência C")
    axes[1].set_ylabel("Latência (s)")
    axes[1].set_title("Exp 2 — Latência por percentil")
    axes[1].set_xscale("log", base=2)
    axes[1].grid(visible=True)
    axes[1].legend()

    fig.tight_layout()
    out = Path("data/exp2/exp2.png")
    fig.savefig(out, dpi=150)
    print(f"[plot2] salvo em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
