import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.shared.config import settings


def default_rabbitmq_url() -> str:
    """Default para uso no host local, preservando override explícito por CLI."""
    return settings.rabbitmq_url.replace("@rabbitmq:", "@localhost:")


def base_queue_from_dlq(dlq_name: str) -> str:
    if dlq_name.endswith(".dlq"):
        return dlq_name.removesuffix(".dlq")
    raise ValueError("fila DLQ deve terminar com .dlq ou use --target")


async def connect(url: str) -> AbstractRobustConnection:
    return await aio_pika.connect_robust(url=url)


async def get_one(queue: aio_pika.abc.AbstractQueue) -> AbstractIncomingMessage | None:
    try:
        return await queue.get(no_ack=False, fail=False)
    except aio_pika.exceptions.QueueEmpty:
        return None


async def list_dlq(rabbitmq_url: str, queue_name: str, limit: int) -> int:
    conn = await connect(rabbitmq_url)
    try:
        channel = await conn.channel()
        queue = await channel.declare_queue(queue_name, passive=True)
        total = queue.declaration_result.message_count
        print(f"queue={queue_name} messages={total}")

        messages: list[AbstractIncomingMessage] = []
        for seen in range(limit):
            msg = await get_one(queue)
            if msg is None:
                break
            messages.append(msg)
            body = msg.body.decode("utf-8", errors="replace")
            print(
                f"[{seen}] correlation_id={msg.correlation_id} "
                f"headers={dict(msg.headers or {})} body={body[:500]}"
            )

        for msg in messages:
            await msg.nack(requeue=True)

        return 0
    finally:
        await conn.close()


async def replay_dlq(rabbitmq_url: str, queue_name: str, target: str, limit: int) -> int:
    conn = await connect(rabbitmq_url)
    try:
        channel = await conn.channel()
        queue = await channel.declare_queue(queue_name, passive=True)

        replayed = 0
        for _ in range(limit):
            msg = await get_one(queue)
            if msg is None:
                break

            headers: dict[str, Any] = dict(msg.headers or {})
            headers.pop("x-attempts", None)

            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=msg.body,
                    headers=headers,
                    correlation_id=msg.correlation_id,
                    reply_to=msg.reply_to,
                    content_type=msg.content_type,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=target,
            )
            await msg.ack()
            replayed += 1

        print(f"replayed={replayed} from={queue_name} to={target}")
        return 0
    finally:
        await conn.close()


async def purge_dlq(rabbitmq_url: str, queue_name: str, yes: bool) -> int:
    if not yes:
        print("recusado: use --yes para purgar")
        return 2

    conn = await connect(rabbitmq_url)
    try:
        channel = await conn.channel()
        queue = await channel.declare_queue(queue_name, passive=True)
        purged = await queue.purge()
        print(f"purged={purged} queue={queue_name}")
        return 0
    finally:
        await conn.close()


async def async_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rabbitmq-url", default=default_rabbitmq_url())
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("queue")
    list_parser.add_argument("--limit", type=int, default=10)

    replay_parser = sub.add_parser("replay")
    replay_parser.add_argument("queue")
    replay_parser.add_argument("--limit", type=int, default=10)
    replay_parser.add_argument("--target")

    purge_parser = sub.add_parser("purge")
    purge_parser.add_argument("queue")
    purge_parser.add_argument("--yes", action="store_true")

    args = parser.parse_args()

    if args.cmd == "list":
        return await list_dlq(args.rabbitmq_url, args.queue, args.limit)
    if args.cmd == "replay":
        target = args.target or base_queue_from_dlq(args.queue)
        return await replay_dlq(args.rabbitmq_url, args.queue, target, args.limit)
    if args.cmd == "purge":
        return await purge_dlq(args.rabbitmq_url, args.queue, args.yes)

    raise AssertionError(args.cmd)


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
