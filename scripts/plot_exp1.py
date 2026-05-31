"""Plot do Exp 1 — speedup e eficiência paralela da indexação.

Lê ``data/exp1/results.csv`` (acumulado por ``run_exp1_indexing_speedup.py``,
uma linha por N), deduplica por N mantendo a execução mais recente, e gera
``data/exp1/exp1.png`` com dois painéis: speedup(N)=T(1)/T(N) contra o ideal
linear, e eficiência(N)=speedup/N.

Uso:
  uv run python scripts/plot_exp1.py
"""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_rows(csv_path: Path) -> list[dict[str, float]]:
    """Carrega o CSV deduplicando por N (último registro de cada N vence)."""
    by_n: dict[int, dict[str, float]] = {}
    with csv_path.open() as handle:
        for raw in csv.DictReader(handle):
            n = int(float(raw["N"]))
            by_n[n] = {
                "N": float(n),
                "elapsed_s": float(raw["elapsed_s"]),
                "chunks_per_s": float(raw["chunks_per_s"]),
            }
    return [by_n[n] for n in sorted(by_n)]


def main() -> int:
    csv_path = Path("data/exp1/results.csv")
    if not csv_path.exists():
        print(f"[plot1] CSV inexistente: {csv_path} — rode run_exp1 primeiro.")
        return 2

    rows = load_rows(csv_path)
    if len(rows) < 2:
        print(f"[plot1] preciso de >=2 valores de N para speedup; tenho {len(rows)}.")
        return 2

    ns = [r["N"] for r in rows]
    base = rows[0]["elapsed_s"]
    speedups = [base / r["elapsed_s"] if r["elapsed_s"] > 0 else 0.0 for r in rows]
    efficiency = [s / n if n > 0 else 0.0 for s, n in zip(speedups, ns, strict=True)]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    axes[0].plot(ns, speedups, "o-", label="medido")
    axes[0].plot(ns, ns, "--", color="gray", label="ideal (linear)")
    axes[0].set_xlabel("N workers de chunk")
    axes[0].set_ylabel("Speedup (T₁ / Tₙ)")
    axes[0].set_title("Exp 1 — Speedup da indexação")
    axes[0].grid(visible=True)
    axes[0].legend()

    axes[1].plot(ns, efficiency, "s-", color="tab:green")
    axes[1].axhline(1.0, color="gray", linestyle="--", alpha=0.5)
    axes[1].set_xlabel("N workers de chunk")
    axes[1].set_ylabel("Eficiência (speedup / N)")
    axes[1].set_title("Exp 1 — Eficiência paralela")
    axes[1].grid(visible=True)
    axes[1].set_ylim(0, 1.2)

    fig.tight_layout()
    out = Path("data/exp1/exp1.png")
    fig.savefig(out, dpi=150)
    print(f"[plot1] salvo em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
