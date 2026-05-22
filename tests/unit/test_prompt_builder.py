import pytest

from src.workers.query.prompt_builder import ContextBlock, build_messages, build_prompt

# Marcadores estáveis dos system prompts versionados (prompts/system_qa_*.md).
# Se o conteúdo dos prompts mudar, ajuste só estas constantes.
_PT_MARKER = "assistente especializado em engenharia de software"
_EN_MARKER = "software engineering assistant"


def test_build_prompt_includes_question_and_blocks() -> None:
    blocks = [
        ContextBlock(source="paper.pdf", page=2, text="Arquitetura hexagonal separa domínio."),
        ContextBlock(source="livro.md", page=None, text="Camadas de adaptadores."),
    ]
    prompt = build_prompt(question="O que é arquitetura hexagonal?", blocks=blocks, lang="pt")

    # A pergunta entra no prompt (case-insensitive: o template não força caixa).
    assert "arquitetura hexagonal" in prompt.lower()
    # Cada fonte é rastreável (base da citação que o modelo deve emitir).
    assert "paper.pdf" in prompt
    assert "livro.md" in prompt
    # Nenhum contexto é perdido quando há orçamento de sobra: texto íntegro.
    assert "Arquitetura hexagonal separa domínio." in prompt
    assert "Camadas de adaptadores." in prompt


def test_build_prompt_truncates_when_over_budget() -> None:
    blocks = [ContextBlock(source="x", page=1, text="x" * 50_000)]
    prompt = build_prompt(question="?", blocks=blocks, lang="pt", max_chars=8_000)

    # 50k chars de bloco, orçamento 8k: o prompt final cabe em max_chars mais
    # uma folga pequena do wrapper (system + template). Não pode vazar os 50k.
    assert len(prompt) <= 9_000


def test_build_prompt_preserves_head_drops_tail_when_over_budget() -> None:
    head = ContextBlock(source="head.pdf", page=1, text="BLOCO_DA_CABECA_RELEVANTE")
    tail = ContextBlock(source="tail.pdf", page=2, text="z" * 50_000)
    prompt = build_prompt(question="?", blocks=[head, tail], lang="pt", max_chars=4_000)

    # Retrieval devolve o mais relevante primeiro; truncamento é pela cauda:
    # o primeiro bloco sobrevive inteiro, a cauda gigante é cortada.
    assert "BLOCO_DA_CABECA_RELEVANTE" in prompt
    assert "z" * 50_000 not in prompt
    assert len(prompt) <= 5_000


@pytest.mark.parametrize(
    ("lang", "expected_marker"),
    [
        ("pt", _PT_MARKER),
        ("en", _EN_MARKER),
        ("fr", _PT_MARKER),  # idioma sem system próprio cai no pt
        ("", _PT_MARKER),  # idioma vazio também cai no pt
    ],
)
def test_build_prompt_selects_system_prompt_by_lang(lang: str, expected_marker: str) -> None:
    blocks = [ContextBlock(source="d.md", page=None, text="conteúdo qualquer")]
    prompt = build_prompt(question="pergunta", blocks=blocks, lang=lang)
    assert expected_marker in prompt


def test_build_messages_returns_system_then_user() -> None:
    blocks = [ContextBlock(source="paper.pdf", page=2, text="conteúdo", doc_id="ap")]
    messages = build_messages(question="pergunta", blocks=blocks, lang="pt")

    # /api/chat espera uma lista de mensagens com role; a política precisa estar
    # isolada num system message próprio (é a hipótese da alavanca 2), e a
    # pergunta+contexto no user. Ordem importa: system primeiro.
    assert [m["role"] for m in messages] == ["system", "user"]
    assert _PT_MARKER in messages[0]["content"]
    assert "pergunta" in messages[1]["content"]
    assert "[doc_id: ap" in messages[1]["content"]


def test_build_messages_equivalent_to_build_prompt() -> None:
    blocks = [
        ContextBlock(source="paper.pdf", page=2, text="Arquitetura hexagonal.", doc_id="ap"),
        ContextBlock(source="livro.md", page=None, text="Camadas de adaptadores.", doc_id="lv"),
    ]
    question = "O que é arquitetura hexagonal?"

    prompt = build_prompt(question=question, blocks=blocks, lang="pt")
    messages = build_messages(question=question, blocks=blocks, lang="pt")

    # Invariante do extract-method: as duas saídas vêm do mesmo _render, então
    # colar as mensagens reproduz exatamente o prompt monolítico. Se alguém
    # quebrar um dos lados (ex: truncar diferente), este teste pega.
    assert prompt == messages[0]["content"] + "\n\n" + messages[1]["content"]


def test_build_prompt_renders_doc_id_header() -> None:
    blocks = [
        ContextBlock(source="paper.pdf", page=51, text="conteúdo", doc_id="ap_es_v1"),
    ]
    prompt = build_prompt(question="?", blocks=blocks, lang="pt")

    # O cabeçalho de cada bloco precisa expor o doc_id no formato [doc_id: ...]:
    # é dele que o modelo copia o valor pra chamar cite_source (coerência
    # ponta-a-ponta com prompts/tools/cite_source.json). Checa o início do
    # cabeçalho (não o separador) pra não acoplar o teste ao layout exato.
    assert "[doc_id: ap_es_v1" in prompt
