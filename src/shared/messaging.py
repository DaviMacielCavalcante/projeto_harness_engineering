"""Helpers de mensageria com aio-pika (RabbitMQ).

Camada fina sobre `aio_pika` para padronizar as 4 operações que todos os
serviços do projeto fazem: conectar, declarar filas, publicar JSON, consumir
em loop. Validação por smoke test (Task 14), não há teste unitário aqui
porque `aio-pika` exige broker real.
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection

# Assinatura do callback consumido por `consume_forever`. Recebe a msg crua
# (para ack/nack manual se preciso) e o payload já parseado de JSON.
Handler = Callable[[AbstractIncomingMessage, dict[str, Any]], Awaitable[None]]


@asynccontextmanager
async def connect(url: str) -> AsyncIterator[AbstractRobustConnection]:
    """Abre conexão robusta com RabbitMQ e garante fechamento no fim do bloco.

    Parameters
    ----------
    url : str
        URL AMQP, ex: ``amqp://guest:guest@rabbitmq:5672/``.

    Yields
    ------
    AbstractRobustConnection
        Conexão com auto-reconnect (resiliente a quedas curtas do broker).
    """
    conn = await aio_pika.connect_robust(url=url)
    try:
        yield conn
    finally:
        await conn.close()


async def declare_queues(conn: AbstractRobustConnection, *names: str) -> None:
    """Declara filas durable no broker. DLX e binds explícitos vêm em B3.

    Parameters
    ----------
    conn : AbstractRobustConnection
        Conexão já aberta (use junto com :func:`connect`).
    *names : str
        Nomes das filas a declarar. Idempotente — se já existir, no-op.
    """
    channel = await conn.channel()

    try:
        for name in names:
            await channel.declare_queue(name=name, durable=True)
    finally:
        await channel.close()


async def publish_json(
    conn: AbstractRobustConnection,
    queue: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
    reply_to: str | None = None,
) -> None:
    """Publica um dict como JSON persistente na fila indicada.

    Parameters
    ----------
    conn : AbstractRobustConnection
        Conexão já aberta.
    queue : str
        Nome da fila destino (routing_key no default exchange).
    payload : dict
        Dict serializável em JSON. Será encodado em UTF-8.
    correlation_id : str, optional
        ID para rastrear o fluxo entre serviços (vai no header AMQP).
    reply_to : str, optional
        Nome da fila de resposta para padrão RPC (worker publica de volta lá).
    """
    channel = await conn.channel()

    try:
        serialized_payload = json.dumps(payload).encode()

        message = aio_pika.Message(
            body=serialized_payload,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            correlation_id=correlation_id,
            reply_to=reply_to,
        )

        await channel.default_exchange.publish(message=message, routing_key=queue)
    finally:
        await channel.close()


async def consume_forever(
    conn: AbstractRobustConnection,
    queue_name: str,
    handler: Handler,
    prefetch: int = 1,
) -> None:
    """Consome a fila indefinidamente, chamando `handler` para cada mensagem.

    O ack é automático ao sair do bloco ``async with msg.process(...)`` sem
    exceção; em caso de exceção, a msg é rejeitada (vai para DLQ quando DLX
    estiver configurada em B3).

    Parameters
    ----------
    conn : AbstractRobustConnection
        Conexão já aberta.
    queue_name : str
        Nome da fila a consumir.
    handler : Handler
        Função async ``(msg, payload_dict) -> None`` chamada para cada msg.
    prefetch : int, default 1
        Quantas mensagens podem estar em voo simultaneamente neste consumer
        (QoS). 1 = processa uma de cada vez, garante fairness entre workers.
    """
    channel = await conn.channel()

    try:
        await channel.set_qos(prefetch_count=prefetch)

        queue = await channel.declare_queue(name=queue_name, durable=True)

        async with queue.iterator() as it:
            async for msg in it:
                async with msg.process(requeue=False):
                    payload = json.loads(msg.body)
                    await handler(msg, payload)
    finally:
        await channel.close()
