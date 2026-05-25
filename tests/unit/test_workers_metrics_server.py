from aiohttp.test_utils import TestClient, TestServer

from src.shared.workers_metrics_server import create_metrics_app


async def test_workers_metrics_endpoint_exposes_prometheus_text() -> None:
    app = create_metrics_app()

    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/metrics")
        body = await resp.text()

    assert resp.status == 200
    assert resp.content_type == "text/plain"
    assert "rag_errors_total" in body
