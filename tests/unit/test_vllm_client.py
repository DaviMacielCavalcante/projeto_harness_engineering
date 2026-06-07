"""Testes do cliente HTTP do vLLM (gerador alternativo do Exp 3).

Mockam o HTTP via `respx` — não precisam do vLLM rodando. Cobrem o mapeamento
do formato OpenAI (`/v1/chat/completions`) para o contrato interno e as
simplificações da "opção B": tools/model ignorados, embeddings indisponíveis.
"""

import httpx
import pytest
import respx

from src.shared.vllm_client import VllmClient

BASE = "http://vllm:8000"
MODEL = "Qwen/Qwen2.5-7B-Instruct-AWQ"


def _ok_response(
    content: str = "resposta", tokens_in: int = 80, tokens_out: int = 20
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
        },
    )


# ---------------------------------------------------------------------------
# chat — mapeia o formato OpenAI para o contrato interno
# ---------------------------------------------------------------------------


@respx.mock
async def test_chat_maps_openai_response() -> None:
    """O vLLM aninha em choices[0].message.content e usage.{prompt,completion}_tokens.

    O client expõe a mesma abstração do Ollama: text/tokens_in/tokens_out, e
    tool_calls SEMPRE [] (opção B, sem function calling).
    """
    respx.post(f"{BASE}/v1/chat/completions").mock(
        return_value=_ok_response("A EAP estrutura o escopo.", 80, 20)
    )

    client = VllmClient(base_url=BASE, model=MODEL)
    out = await client.chat(
        messages=[{"role": "user", "content": "O que é EAP?"}],
        model="qwen2.5:7b-instruct",
    )

    assert out["text"] == "A EAP estrutura o escopo."
    assert out["tokens_in"] == 80
    assert out["tokens_out"] == 20
    assert out["tool_calls"] == []


# ---------------------------------------------------------------------------
# chat — ignora `model` do argumento e usa o modelo configurado
# ---------------------------------------------------------------------------


@respx.mock
async def test_chat_uses_configured_model_not_arg() -> None:
    """O id no payload tem que casar com o modelo servido pelo vLLM.

    O worker passa `settings.generation_model` (nome do Ollama); o client deve
    sobrescrever pelo modelo do __init__, senão a API rejeita.
    """
    route = respx.post(f"{BASE}/v1/chat/completions").mock(return_value=_ok_response())

    client = VllmClient(base_url=BASE, model=MODEL)
    await client.chat(
        messages=[{"role": "user", "content": "?"}],
        model="qwen2.5:7b-instruct",  # nome do Ollama — deve ser ignorado
    )

    sent = route.calls.last.request.read()
    assert MODEL.encode() in sent
    assert b"qwen2.5:7b-instruct" not in sent


# ---------------------------------------------------------------------------
# chat — não envia tools (opção B) e propaga temperature
# ---------------------------------------------------------------------------


@respx.mock
async def test_chat_ignores_tools_and_passes_temperature() -> None:
    """tools é descartado (servidor sem auto-tool-choice); temperature vai no payload."""
    route = respx.post(f"{BASE}/v1/chat/completions").mock(return_value=_ok_response())

    client = VllmClient(base_url=BASE, model=MODEL)
    await client.chat(
        messages=[{"role": "user", "content": "?"}],
        model=MODEL,
        tools=[{"type": "function", "function": {"name": "cite_source"}}],
        options={"temperature": 0.5, "num_ctx": 4096},
    )

    sent = route.calls.last.request.read()
    assert b"cite_source" not in sent
    assert b"temperature" in sent
    assert b"0.5" in sent


# ---------------------------------------------------------------------------
# embed — indisponível por design
# ---------------------------------------------------------------------------


async def test_embed_raises_not_implemented() -> None:
    """O vLLM serve geração, não embeddings — embed fica sempre no Ollama."""
    client = VllmClient(base_url=BASE, model=MODEL)
    with pytest.raises(NotImplementedError):
        await client.embed("x", model="nomic-embed-text")


# ---------------------------------------------------------------------------
# retry com tenacity
# ---------------------------------------------------------------------------


@respx.mock
async def test_chat_retries_on_500_then_succeeds() -> None:
    """Em 5xx o client tenta de novo (mesma política do Ollama)."""
    respx.post(f"{BASE}/v1/chat/completions").mock(
        side_effect=[httpx.Response(500), _ok_response("ok", 1, 1)]
    )

    client = VllmClient(base_url=BASE, model=MODEL)
    out = await client.chat(messages=[{"role": "user", "content": "x"}], model=MODEL)

    assert out["text"] == "ok"
