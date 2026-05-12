"""Rotas HTTP do gateway.

Endpoints:
    - `GET /health` — liveness probe trivial.
    - `POST /ingest` — aceita um documento e publica na fila de ingestão (a fazer).
    - `POST /query` — pergunta sob padrão RPC sobre RabbitMQ (a fazer).
"""

from fastapi import APIRouter

from src.shared.logging import configure_logging

log = configure_logging("gateway")
router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe: confirma que o app subiu e o event loop responde."""
    return {"status": "ok"}


# `/ingest` e `/query` entram nos próximos passos da Task 8 — não implementar agora.
