"""Experimento 3 (bônus) — Ollama vs vLLM no mesmo pipeline (spec §10.3).

Roda o Experimento 2 (varredura de concorrência) DUAS vezes — uma com o gerador
em Ollama, outra em vLLM — e arquiva os CSVs separados em
``data/exp3/{ollama,vllm}/results.csv`` para o ``plot_exp3.py`` comparar.

A troca de backend é manual e fora deste script (parar Ollama-gerador, subir
vLLM, ``INFERENCE_BACKEND=vllm``, reiniciar o query-worker), porque envolve a
GPU do PC1 e o ciclo de vida de containers — o script só orquestra as duas
rodadas e pausa entre elas. Ver ``infra/docker/vllm-compose.override.yml``.

Qualquer argumento extra é repassado ao ``run_exp2_query_throughput.py``
(ex.: ``--host`` para Modo 2):

  uv run python scripts/run_exp3_ollama_vs_vllm.py --host 100.x.y.z --n-queries 200
"""

import shutil
import subprocess
import sys
from pathlib import Path


def run_exp2(label: str, passthrough: list[str]) -> None:
    """Executa uma rodada do Exp 2 e arquiva o CSV sob ``data/exp3/<label>``."""
    print(f"\n=== Exp 3 — rodada {label} ===")
    subprocess.run(
        ["uv", "run", "python", "scripts/run_exp2_query_throughput.py", *passthrough],
        check=True,
    )
    out_dir = Path("data/exp3") / label
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy("data/exp2/results.csv", out_dir / "results.csv")
    print(f"[exp3] CSV da rodada '{label}' em {out_dir / 'results.csv'}")


def main() -> int:
    passthrough = sys.argv[1:]
    Path("data/exp3").mkdir(parents=True, exist_ok=True)

    # Rodada 1 — Ollama (assume INFERENCE_BACKEND=ollama, o default).
    print("[exp3] Rodada Ollama. Garanta INFERENCE_BACKEND=ollama e o query-worker no ar.")
    run_exp2("ollama", passthrough)

    # Troca manual de backend entre as rodadas.
    print("\n[exp3] AGORA, antes de continuar:")
    print("       1. docker stop rag-ollama        (libera VRAM do gerador)")
    print("       2. suba o vLLM pelo override e troque INFERENCE_BACKEND=vllm")
    print("       3. reinicie o query-worker (e deixe o embedder em CPU/Ollama)")
    print("       Pressione Enter quando o vLLM estiver respondendo...")
    input()

    # Rodada 2 — vLLM.
    run_exp2("vllm", passthrough)

    print("\n[exp3] Pronto. CSVs em data/exp3/{ollama,vllm}/results.csv")
    print("[exp3] Gere o gráfico: uv run python scripts/plot_exp3.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
