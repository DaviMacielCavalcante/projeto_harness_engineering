"""Testes do cliente HTTP do Ollama.

Estes testes mockam o HTTP via `respx`, então não precisam de Ollama rodando.
São rápidos e determinísticos.
"""

import httpx
import respx

from src.shared.ollama_client import OllamaClient

# ---------------------------------------------------------------------------
# embed — caminho feliz
# ---------------------------------------------------------------------------


@respx.mock
async def test_embed_returns_vector() -> None:
    """O client deve devolver o array de floats do campo 'embedding' da resposta."""
    route = respx.post("http://ollama:11434/api/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={"embedding": [0.1, 0.2, 0.3, 0.4]},
        )
    )

    client = OllamaClient(base_url="http://ollama:11434")
    vec = await client.embed("hello", model="nomic-embed-text")

    assert vec == [0.1, 0.2, 0.3, 0.4]
    assert route.called

    # O payload deve conter model e prompt
    sent = route.calls.last.request.read()
    assert b"nomic-embed-text" in sent
    assert b"hello" in sent


# ---------------------------------------------------------------------------
# generate — caminho feliz + tradução de campos
# ---------------------------------------------------------------------------


@respx.mock
async def test_generate_returns_text_and_token_counts() -> None:
    """A API do Ollama usa 'response', 'prompt_eval_count', 'eval_count'.

    O client expõe 'text', 'tokens_in', 'tokens_out' — abstração estável
    contra mudança de vendor (B4 traz vLLM com outros nomes).
    """
    respx.post("http://ollama:11434/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": "Resposta gerada",
                "prompt_eval_count": 50,
                "eval_count": 12,
            },
        )
    )

    client = OllamaClient(base_url="http://ollama:11434")
    out = await client.generate(
        prompt="Pergunta?",
        model="qwen2.5:7b-instruct",
    )

    assert out["text"] == "Resposta gerada"
    assert out["tokens_in"] == 50
    assert out["tokens_out"] == 12


# ---------------------------------------------------------------------------
# generate — payload inclui options
# ---------------------------------------------------------------------------


@respx.mock
async def test_generate_passes_options_in_payload() -> None:
    """`options` deve ir no body (Ollama lê temperature, num_ctx, etc. dali)."""
    route = respx.post("http://ollama:11434/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={"response": "ok", "prompt_eval_count": 1, "eval_count": 1},
        )
    )

    client = OllamaClient(base_url="http://ollama:11434")
    await client.generate(
        prompt="?",
        model="qwen2.5:7b-instruct",
        options={"temperature": 0.5, "num_ctx": 4096},
    )

    sent = route.calls.last.request.read()
    assert b"temperature" in sent
    assert b"0.5" in sent
    assert b"num_ctx" in sent


# ---------------------------------------------------------------------------
# retry com tenacity
# ---------------------------------------------------------------------------


@respx.mock
async def test_embed_retries_on_500_then_succeeds() -> None:
    """Em caso de 5xx, o client deve tentar novamente e ter sucesso na 2ª chamada.

    side_effect aceita uma lista — cada chamada consome o próximo item.
    Se houver mais chamadas que itens, respx repete o último.
    """
    respx.post("http://ollama:11434/api/embeddings").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"embedding": [0.42]}),
        ]
    )

    client = OllamaClient(base_url="http://ollama:11434")
    vec = await client.embed("x", model="nomic-embed-text")

    assert vec == [0.42]
