"""Helpers de mensageria com aio-pika (RabbitMQ).

Camada fina sobre `aio_pika` para padronizar as 4 operações que todos os
serviços do projeto fazem: conectar, declarar filas, publicar JSON, consumir
em loop. Validação por smoke test (Task 14), não há teste unitário aqui
porque `aio-pika` exige broker real.
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

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


async def declare_topology(conn: AbstractRobustConnection, *bases: str) -> None:
    """Declara a topologia completa: DLX + filas principais (com dead-letter) + DLQs.

    Substitui o ``declare_queues`` do B1/B2. Cada fila principal ganha os
    argumentos ``x-dead-letter-exchange``/``x-dead-letter-routing-key`` apontando
    pra ``rag.dlx``; uma mensagem rejeitada sem requeue (``consume_forever`` após
    ``max_attempts``) é "dead-lettered" pra DLX, que a roteia pra ``<base>.dlq``.

    Parameters
    ----------
    conn : AbstractRobustConnection
        Conexão já aberta (use junto com :func:`connect`).
    *bases : str
        Nomes das filas principais (o caller passa de ``settings.queue_*`` —
        fonte única). Cada uma ganha uma ``<base>.dlq`` correspondente.

    Notes
    -----
    Filas criadas no B1/B2 **sem** esses argumentos precisam ser apagadas e
    recriadas — o RabbitMQ recusa redeclaração com argumentos diferentes
    (``PRECONDITION_FAILED``). Mais limpo: ``make down -v && make dev``.
    """
    channel = await conn.channel()
    try:
        rag_dlx = await channel.declare_exchange(
            name="rag.dlx", type=aio_pika.ExchangeType.DIRECT, durable=True
        )

        for base in bases:
            dlq_name = f"{base}.dlq"

            dlq_queue = await channel.declare_queue(name=dlq_name, durable=True)

            await dlq_queue.bind(rag_dlx, routing_key=base)

            await channel.declare_queue(
                name=base,
                durable=True,
                arguments={"x-dead-letter-exchange": "rag.dlx", "x-dead-letter-routing-key": base},
            )
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
    max_attempts: int = 3,
) -> None:
    """Consome a fila indefinidamente com retry contado e DLQ após N falhas.

    Ack/nack agora é **manual** (não mais ``async with msg.process()``), porque
    precisamos decidir, a cada falha, entre *retentar* (republicar com contador
    incrementado) e *desistir* (``reject(requeue=False)`` → cai na DLX → DLQ).

    Parameters
    ----------
    conn : AbstractRobustConnection
        Conexão já aberta.
    queue_name : str
        Nome da fila a consumir (já declarada por :func:`declare_topology`).
    handler : Handler
        Função async ``(msg, payload_dict) -> None`` chamada para cada msg.
    prefetch : int, default 1
        QoS — quantas mensagens em voo simultâneas neste consumer.
    max_attempts : int, default 3
        Após esta tentativa falhar, a mensagem vai pra DLQ em vez de retentar.
    """
    channel = await conn.channel()
    try:
        await channel.set_qos(prefetch_count=prefetch)

        queue = await channel.declare_queue(name=queue_name, passive=True)

        async with queue.iterator() as it:
            async for msg in it:
                attempts = 1 + cast(int, (msg.headers or {}).get("x-attempts", 0))

                try:
                    payload = json.loads(msg.body)
                    await handler(msg, payload)
                    await msg.ack()
                except Exception:
                    if attempts >= max_attempts:
                        await msg.reject(requeue=False)
                    else:
                        headers = dict(msg.headers or {})

                        headers["x-attempts"] = attempts

                        await channel.default_exchange.publish(
                            aio_pika.Message(
                                body=msg.body,
                                headers=headers,
                                correlation_id=msg.correlation_id,
                                reply_to=msg.reply_to,
                                content_type=msg.content_type,
                            ),
                            routing_key=queue_name,
                        )

                        await msg.ack()
    finally:
        await channel.close()
