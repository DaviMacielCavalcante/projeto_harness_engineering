"""Smoke test do gateway FastAPI.

Cobertura mínima desta Task 8: garante que o app sobe, o lifespan conecta no
RabbitMQ sem explodir e o endpoint `/health` responde 200 com o payload
esperado. Os endpoints `/ingest` e `/query` NÃO são testados aqui — eles são
exercitados pelo smoke ponta-a-ponta da Task 14, com workers reais consumindo
as filas.

Pré-requisitos para rodar:
- RabbitMQ subido: ``docker compose --profile server up -d rabbitmq``
- Variável de ambiente: ``RUN_INTEGRATION=1``

Execução:
    RUN_INTEGRATION=1 uv run pytest tests/integration/test_gateway_smoke.py -v
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient

from src.gateway.main import app

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="define RUN_INTEGRATION=1 e suba o RabbitMQ para rodar",
)


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    """`GET /health` deve retornar 200 com `{'status': 'ok'}`."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
