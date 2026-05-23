"""Teste de integração: msg que falha 3× cai na DLQ.

Valida o ciclo de retry + dead-lettering implementado na Task 1 do B3:
  - `declare_topology` cria fila principal com `x-dead-letter-*` + DLQ ligada à DLX.
  - `consume_forever` republica a msg com `x-attempts` incrementado a cada falha.
  - Após `max_attempts=3` falhas, a msg é rejeitada sem requeue → cai na DLQ.

Pré-requisitos:
- RabbitMQ subido: ``docker compose --profile server up -d rabbitmq``
- Variável de ambiente: ``RUN_INTEGRATION=1``

Execução:
    RUN_INTEGRATION=1 uv run pytest tests/integration/test_dlq.py -v
"""

import asyncio
import os
from typing import Any

import aio_pika
import pytest
from aio_pika.abc import AbstractIncomingMessage

from src.shared.messaging import connect, consume_forever, publish_json

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="define RUN_INTEGRATION=1 e suba o RabbitMQ para rodar",
)


@pytest.mark.asyncio
async def test_message_lands_in_dlq_after_max_attempts() -> None:
    """Msg cujo handler sempre falha cai na DLQ após `max_attempts` tentativas."""
    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

    # Nomes únicos do teste — isolam de filas reais em broker compartilhado.
    queue_name = "test.b3.dlq.queue"
    dlq_name = f"{queue_name}.dlq"
    dlx_name = "test.b3.dlx"

    async with connect(url) as conn:
        # Setup da topologia (espelha declare_topology, mas com nomes únicos —
        # não dá pra chamar declare_topology porque ele hardcoda "rag.dlx").
        ch = await conn.channel()
        try:
            dlx = await ch.declare_exchange(
                name=dlx_name,
                type=aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            dlq = await ch.declare_queue(name=dlq_name, durable=True)
            await dlq.bind(dlx, routing_key=queue_name)
            await ch.declare_queue(
                name=queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": dlx_name,
                    "x-dead-letter-routing-key": queue_name,
                },
            )
        finally:
            await ch.close()

        # Handler que sempre falha — registra a chamada ANTES do raise pra
        # provarmos que houve exatamente N tentativas.
        attempts_seen: list[int] = []

        async def always_fails(
            msg: AbstractIncomingMessage, payload: dict[str, Any]
        ) -> None:
            attempts_seen.append(1)
            raise RuntimeError("explode")

        # Consumer em background — consume_forever é loop infinito, roda como
        # task e cancela no fim.
        consumer_task = asyncio.create_task(
            consume_forever(conn, queue_name, always_fails, max_attempts=3)
        )

        # Publica uma única mensagem; o consumer pega quase imediatamente
        # e começa o ciclo de retry.
        await publish_json(conn, queue_name, {"x": 1})

        # Polling com teto ~15s — espera as 3 tentativas chegarem ao handler.
        # asyncio.sleep fixo seria frágil (depende do load do broker).
        for _ in range(30):
            if len(attempts_seen) >= 3:
                break
            await asyncio.sleep(0.5)

        # Cancela e aguarda o consumer encerrar limpo — evita warning de
        # "task was destroyed but it is pending" no teardown do pytest-asyncio.
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

        # Asserção 1: exatamente 3 entregas ao handler (nem mais, nem menos).
        assert len(attempts_seen) == 3, (
            f"esperado 3 tentativas, observado {len(attempts_seen)}"
        )

        # Asserção 2: a msg final caiu na DLQ. passive=True na inspeção pra NÃO
        # redeclarar (redeclaração com arguments divergentes dá PRECONDITION_FAILED).
        ch = await conn.channel()
        try:
            dlq_inspect = await ch.declare_queue(
                name=dlq_name, durable=True, passive=True
            )
            assert dlq_inspect.declaration_result.message_count >= 1, (
                f"DLQ vazia: message_count={dlq_inspect.declaration_result.message_count}"
            )
        finally:
            await ch.close()
