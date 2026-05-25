"""Servidor HTTP standalone para expor `/metrics` nos workers.

Workers rodam como consumidores AMQP, sem FastAPI/Uvicorn. Este modulo sobe
um pequeno servidor aiohttp no mesmo event loop para o Prometheus raspar o
registro compartilhado de `src.shared.metrics`.
"""

from aiohttp import web

from src.shared.metrics import metrics_response


def create_metrics_app() -> web.Application:
    """Cria o app aiohttp usado pelo endpoint de metricas dos workers."""
    app = web.Application()
    app.router.add_get("/metrics", handle_metrics)
    return app


async def handle_metrics(request: web.Request) -> web.Response:
    """Devolve as metricas Prometheus do processo atual."""
    body, content_type = metrics_response()
    return web.Response(body=body, headers={"Content-Type": content_type})


async def start_metrics_server(host: str = "0.0.0.0", port: int = 9100) -> web.AppRunner:
    """Inicia o endpoint `/metrics` e retorna o runner para manter vivo."""
    runner = web.AppRunner(create_metrics_app())
    await runner.setup()

    site = web.TCPSite(runner, host=host, port=port)
    await site.start()

    return runner
