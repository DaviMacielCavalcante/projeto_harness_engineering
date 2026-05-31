import argparse
import base64
from pathlib import Path

import httpx

SOURCE_TYPES = {
    ".pdf": "pdf",
    ".md": "md",
    ".markdown": "md",
    ".html": "html",
    ".htm": "html",
}


def iter_corpus_files(corpus: Path) -> list[Path]:
    return sorted(
        path for path in corpus.rglob("*") if path.is_file() and path.suffix.lower() in SOURCE_TYPES
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=Path("samples/corpus"))
    parser.add_argument("--gateway", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    if not args.corpus.exists():
        print(f"corpus inexistente: {args.corpus}")
        return 2

    files = iter_corpus_files(args.corpus)
    if not files:
        print(f"nenhum arquivo suportado em {args.corpus}")
        print("enviados=0 falhas=0")
        return 0

    enviados = 0
    falhas = 0

    with httpx.Client(base_url=args.gateway, timeout=args.timeout) as client:
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
            except Exception as exc:
                falhas += 1
                print(f"falha arquivo={path} erro={exc}")
                continue

            enviados += 1
            data = resp.json()
            print(
                f"enviado arquivo={path} doc_id={data['doc_id']} "
                f"correlation_id={data['correlation_id']}"
            )

    print(f"enviados={enviados} falhas={falhas}")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
