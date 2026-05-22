from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)


class OllamaClient:
    """Cliente assíncrono para Ollama (embeddings + generate)."""

    def __init__(self, base_url: str, timeout: float = 60.0) -> None:

        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def _post_with_retry(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        """POST genérico com retry exponencial+jitter.

        Parameters
        ----------
        path : str
            Caminho relativo da API (ex: "/api/embeddings").
        json : dict
            Payload JSON a enviar no body.

        Returns
        -------
        dict
            Resposta JSON parseada.
        """
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
        """Gera embedding de um texto.

        Parameters
        ----------
        text : str
            Texto a embedar.
        model : str
            Nome do modelo no Ollama (ex: "nomic-embed-text").

        Returns
        -------
        list of float
            Vetor de embedding (768d para nomic-embed-text).
        """
        payload = {"model": model, "prompt": text}

        response = await self._post_with_retry(path="/api/embeddings", json=payload)

        vector: list[float] = response["embedding"]

        return vector

    async def generate(
        self,
        prompt: str,
        model: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Gera texto a partir de um prompt.

        Parameters
        ----------
        prompt : str
            Prompt completo (já montado pelo caller).
        model : str
            Nome do modelo no Ollama (ex: "qwen2.5:7b-instruct").
        options : dict, optional
            Opções de inferência (temperature, num_ctx, etc.).

        Returns
        -------
        dict
            Dict com chaves "text", "tokens_in", "tokens_out".
        """
        payload = {"model": model, "prompt": prompt, "stream": False}

        if options is not None:
            payload["options"] = options

        response = await self._post_with_retry(path="/api/generate", json=payload)

        mapped_response: dict[str, Any] = {
            "text": response.get("response", ""),
            "tokens_in": response.get("prompt_eval_count", 0),
            "tokens_out": response.get("eval_count", 0),
        }

        return mapped_response

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Gera resposta via ``/api/chat``, com suporte a function calling.

        Diferente de :meth:`generate` (``/api/generate``, prompt único), o
        ``/api/chat`` recebe uma lista de ``messages`` e, opcionalmente,
        ``tools`` — e pode devolver ``tool_calls`` (pedidos estruturados de
        chamada de função) junto com/no lugar do texto. O query-worker converte
        esses ``tool_calls`` em :class:`Citation`.

        Parameters
        ----------
        messages : list of dict
            Mensagens no formato Ollama (ex: ``[{"role": "user", "content": ...}]``).
        model : str
            Nome do modelo (ex: ``"qwen2.5:7b-instruct"``).
        tools : list of dict, optional
            Definições de ferramentas (ex: ``[cite_source]``). Só vai no payload
            se não-``None``.
        options : dict, optional
            Opções de inferência (temperature, num_ctx, etc.).

        Returns
        -------
        dict
            ``"text"`` (``message.content``), ``"tokens_in"``, ``"tokens_out"``
            e ``"tool_calls"`` (lista crua; ``[]`` se o modelo não chamou tool).
        """
        payload = {"model": model, "messages": messages, "stream": False}

        if tools:
            payload["tools"] = tools

        if options:
            payload["options"] = options

        response = await self._post_with_retry(path="/api/chat", json=payload)

        msg = response["message"]

        tool_calls = msg.get("tool_calls", [])

        return {
            "text": msg["content"],
            "tokens_in": response.get("prompt_eval_count", 0),
            "tokens_out": response.get("eval_count", 0),
            "tool_calls": tool_calls,
        }
