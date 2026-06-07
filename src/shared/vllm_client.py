"""Cliente de geração para vLLM (servidor OpenAI-compatible), usado no Exp 3.

O vLLM é um backend de inferência ALTERNATIVO ao Ollama, ativado apenas durante
o Experimento 3 (Ollama vs vLLM, spec §10.3) via ``INFERENCE_BACKEND=vllm``.
Expõe a API no padrão OpenAI (``/v1/chat/completions``), diferente do Ollama
(``/api/chat``).

Escopo deliberadamente enxuto ("opção B" do plano B4): este client NÃO faz
function calling (citações estruturadas). O experimento mede throughput/latência
de geração, não qualidade de citação — e o pipeline já cai num fallback
estrutural de citações quando ``tool_calls`` vem vazio (ver FASE 7 do
query-worker). Embeddings continuam no Ollama: o modelo AWQ servido pelo vLLM é
um gerador, não um encoder.
"""

from typing import Any, Protocol

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)


class ChatGenerator(Protocol):
    """Interface mínima de geração consumida pelo query-worker (FASE 6).

    Tanto :class:`~src.shared.ollama_client.OllamaClient` quanto
    :class:`VllmClient` a satisfazem estruturalmente; o worker escolhe um ou
    outro em runtime via ``settings.inference_backend``.
    """

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Gera resposta a partir de ``messages``; retorna text/tokens/tool_calls."""
        ...


class VllmClient:
    """Cliente assíncrono de geração via API OpenAI-compatible do vLLM."""

    def __init__(
        self,
        base_url: str,
        model: str,
        max_tokens: int = 1024,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout

    async def _post_with_retry(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        """POST genérico com retry exponencial+jitter (mesma política do Ollama)."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1, max=8),
            retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url=f"{self._base_url}{path}", json=json)

                    response.raise_for_status()

                    r_json: dict[str, Any] = response.json()

                    return r_json

        raise RuntimeError("Unreachable")

    async def embed(self, text: str, model: str) -> list[float]:
        """Não suportado: durante o Exp 3 os embeddings ficam no Ollama.

        Existe só para deixar explícita a fronteira — o vLLM serve um gerador
        (Qwen2.5-AWQ), não um encoder de embeddings. Manter embeddings no Ollama
        é intencional (plano B4, Task 5).
        """
        raise NotImplementedError(
            "VllmClient não serve embeddings; use OllamaClient para embed no Exp 3."
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Gera resposta via ``/v1/chat/completions`` (sem function calling).

        Mantém o mesmo contrato de retorno de :meth:`OllamaClient.chat` para ser
        um drop-in no query-worker, MAS com três simplificações da opção B:

        - ``tools`` é IGNORADO: o servidor não sobe com
          ``--enable-auto-tool-choice``, então ``tool_calls`` volta sempre
          ``[]`` e o worker usa o fallback estrutural de citações.
        - ``model`` (argumento) é IGNORADO: o vLLM serve um único modelo, fixado
          no ``__init__`` (``self._model``); o id no payload precisa casar com
          ele, senão a API rejeita.
        - de ``options`` só aproveitamos ``temperature``; ``num_ctx`` é
          configuração de servidor (``--max-model-len``), não de request.

        Returns
        -------
        dict
            ``"text"``, ``"tokens_in"``, ``"tokens_out"`` e ``"tool_calls"``
            (este último sempre ``[]``).
        """
        opts = options or {}

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
            "temperature": opts.get("temperature", 0.2),
            "stream": False,
        }

        response = await self._post_with_retry(path="/v1/chat/completions", json=payload)

        message = response["choices"][0]["message"]
        usage = response.get("usage", {})

        return {
            "text": message.get("content") or "",
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "tool_calls": [],
        }
