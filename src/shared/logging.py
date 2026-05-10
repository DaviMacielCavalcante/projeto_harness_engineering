"""Configuração centralizada de logging.

Toda saída de log do projeto vai por aqui. Padrão: JSON estruturado no stdout,
um objeto por linha. Containers Docker capturam stdout, Promtail (B3) lê,
Loki indexa, Grafana exibe.

API pública:
- configure_logging(service_name) -> BoundLogger
    Configura o structlog (idempotente). Retorna um logger já com `service` bindado.
- bind_correlation_id(cid) / clear_correlation_id()
    Gerencia o contextvar para que toda linha de log dentro do mesmo
    contexto async carregue o `correlation_id` automaticamente.
"""

import logging
import sys

import structlog

from src.shared.config import settings


def configure_logging(service_name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Configura structlog para emitir JSON em stdout. Idempotente.

    Parameters
    ----------
    service_name : str or None
        Nome do serviço a ser bindado em todas as linhas (gateway, ingest-worker,
        query-worker, rerank-service, etc.). Se None, usa `settings.service_name`.

    Returns
    -------
    structlog.stdlib.BoundLogger
        Logger pronto para uso, já com `service` no contexto.
    """
    name = service_name or settings.service_name

    # Configura o logging do stdlib: stdout, level vem da settings.
    # structlog usa o stdlib internamente como sink.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            # 1. Injeta variáveis bindadas via contextvars (correlation_id, etc.)
            structlog.contextvars.merge_contextvars,
            # 2. Adiciona o campo "level"
            structlog.processors.add_log_level,
            # 3. Timestamp ISO 8601 em UTC
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            # 4. Captura informações de stack se solicitado via stack_info=True
            structlog.processors.StackInfoRenderer(),
            # 5. Formata exc_info=True em traceback legível
            structlog.processors.format_exc_info,
            # 6. Renderiza como JSON (uma linha por evento)
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger().bind(service=name)


def bind_correlation_id(correlation_id: str) -> None:
    """Adiciona correlation_id ao contexto do logger atual.

    Tudo que for logado depois dessa chamada (no mesmo contexto async) vai
    automaticamente incluir `correlation_id` no JSON, sem precisar passar
    como argumento em cada chamada.

    Parameters
    ----------
    correlation_id : str
        Identificador correlacional do request (ex: "q-7af3a2b1", "i-abc123").
    """
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)


def clear_correlation_id() -> None:
    """Limpa as variáveis de contexto do logger.

    Chamar ao final do processamento de um request para evitar vazamento de
    contexto entre requests subsequentes (sobretudo importante em workers que
    consomem mensagens em loop).
    """
    structlog.contextvars.clear_contextvars()
