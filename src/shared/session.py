"""Histórico de sessão com sumarização adaptativa (estratégia injetável).

Guarda, por `session_id`, as trocas (pergunta/resposta) recentes em Redis e
um "resumo" acumulado dos turnos mais antigos. Mesmo padrão de DI do
`cache.py`: um `Protocol` mínimo (`get`/`setex`) em vez de acoplar a
`redis.asyncio`, então dá pra testar com um fake em memória.

Estratégia adaptativa:
- Mantém até `max_turns` trocas mais recentes em texto puro (`KEY_HIST`).
- Ao exceder `max_turns`, o turno mais antigo é *despejado* e passado ao
  `summarizer`, cujo retorno vira o novo resumo (`KEY_SUM`).
- No B2 o `summarizer` default (`concat_summarizer`) só concatena texto. No
  B3 injeta-se um que chama o LLM — sem tocar nesta classe (Strategy/DI).
"""

import json
from collections.abc import Callable
from typing import Any, Protocol

# (resumo_atual, turno_despejado) -> novo_resumo.
# turno_despejado é um dict {"q": ..., "a": ...}; o retorno substitui KEY_SUM.
Summarizer = Callable[[str, dict[str, str]], str]


def concat_summarizer(current: str, evicted: dict[str, str]) -> str:
    """Estratégia default do B2: anexa o turno despejado ao resumo (sem LLM).

    Parameters
    ----------
    current : str
        Resumo acumulado até agora ("" se ainda não houver).
    evicted : dict of str
        Turno mais antigo saindo da janela, com chaves ``"q"`` e ``"a"``.

    Returns
    -------
    str
        Novo resumo, com o turno despejado anexado ao final.
    """
    new_line = f"Q: {evicted['q']} | A: {evicted['a']}"

    if not current:
        return new_line

    current += " | " + new_line

    return current.strip()


class _RedisLike(Protocol):
    """Interface mínima exigida do client Redis (mesma forma do `cache.py`)."""

    async def get(self, k: str) -> str | bytes | None: ...

    async def setex(self, k: str, ttl: int, v: str) -> Any: ...


class SessionStore:
    """Histórico de conversação (janela recente) + resumo dos turnos antigos."""

    HISTORY_TTL = 60 * 60 * 6  # 6h, em segundos
    KEY_HIST = "session:{sid}:history"
    KEY_SUM = "session:{sid}:summary"

    def __init__(
        self,
        client: _RedisLike,
        max_turns: int = 3,
        summarizer: Summarizer = concat_summarizer,
    ) -> None:
        self._r = client
        self.max_turns = max_turns
        self._summarize = summarizer

    async def get_history(self, sid: str) -> list[dict[str, str]]:
        """Lê a janela recente de turnos, ou ``[]`` se a sessão não existe.

        Returns
        -------
        list of dict
            Turnos ``{"q": ..., "a": ...}`` em ordem cronológica.
        """
        key_history = self.KEY_HIST.format(sid=sid)

        history = await self._r.get(key_history)

        if not history:
            return []

        history_json: list[dict[str, str]] = json.loads(history)

        return history_json

    async def get_summary(self, sid: str) -> str | None:
        """Lê o resumo acumulado dos turnos antigos, ou ``None`` se não houver."""
        # TODO: ler KEY_SUM.format(sid=sid); decode se vier bytes; "" ou None -> None.

        key = self.KEY_SUM.format(sid=sid)

        key_summary = await self._r.get(key)

        if isinstance(key_summary, str):
            if not key_summary:
                return None

            return key_summary

        decoded_key_summary = key_summary.decode() if isinstance(key_summary, bytes) else None

        return decoded_key_summary

    async def append(self, sid: str, question: str, answer: str) -> None:
        """Registra um turno; ao estourar max_turns, despeja o mais antigo no resumo.

        Parameters
        ----------
        sid : str
            Identificador da sessão.
        question, answer : str
            Pergunta do usuário e resposta gerada nesse turno.
        """
        history = await self.get_history(sid=sid)

        history.append({"q": question, "a": answer})

        if len(history) > self.max_turns:
            oldest = history.pop(0)

            new_summary = self._summarize(await self.get_summary(sid=sid) or "", oldest)

            await self._r.setex(self.KEY_SUM.format(sid=sid), self.HISTORY_TTL, new_summary)

        await self._r.setex(self.KEY_HIST.format(sid=sid), self.HISTORY_TTL, json.dumps(history))
