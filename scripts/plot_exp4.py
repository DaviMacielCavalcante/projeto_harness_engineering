"""Plot do Exp 4 — séries temporais de cada cenário de chaos.

Lê ``data/exp4/<cenario>.csv`` (gerados por ``run_exp4_chaos.py``) e empilha um
painel por cenário existente em ``data/exp4/exp4.png``. Eixo-x é o tempo
relativo ao início do cenário; cada métrica vira uma linha.

Uso:
  uv run python scripts/plot_exp4.py
"""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCENARIOS = ["kill_ollama", "kill_chunk_worker", "burst"]


def load(name: str) -> dict[str, list[tuple[float, float]]]:
    series: dict[str, list[tuple[float, float]]] = {}
    path = Path(f"data/exp4/{name}.csv")
    if not path.exists():
        return series
    with path.open() as handle:
        for raw in csv.DictReader(handle):
            series.setdefault(raw["metric"], []).append((float(raw["t"]), float(raw["value"])))
    for points in series.values():
        points.sort(key=lambda p: p[0])
    return series


def main() -> int:
    available = [(name, load(name)) for name in SCENARIOS]
    available = [(name, data) for name, data in available if data]
    if not available:
        print("[plot4] nenhum CSV em data/exp4/ — rode run_exp4_chaos.py primeiro.")
        return 2

    fig, axes = plt.subplots(len(available), 1, figsize=(10, 3 * len(available)), squeeze=False)
    for row, (name, data) in enumerate(available):
        ax = axes[row][0]
        for metric, points in data.items():
            t0 = points[0][0]
            xs = [t - t0 for t, _ in points]
            ys = [v for _, v in points]
            ax.plot(xs, ys, label=metric)
        ax.set_title(f"Exp 4 — {name}")
        ax.set_xlabel("t (s desde o início do cenário)")
        ax.set_ylabel("valor")
        ax.grid(visible=True)
        ax.legend(fontsize="small")

    fig.tight_layout()
    out = Path("data/exp4/exp4.png")
    fig.savefig(out, dpi=150)
    print(f"[plot4] salvo em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
