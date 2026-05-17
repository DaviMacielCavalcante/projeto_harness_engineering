"""Montagem do prompt final do query-worker a partir de chunks recuperados.

Junta o system prompt versionado (``prompts/system_qa_{lang}.md``) com o
template Jinja2 do usuário (``prompts/user_qa_template.md``), respeitando um
orçamento de caracteres: se os blocos de contexto estourarem o orçamento,
trunca pela cauda (mantém os primeiros, que vêm mais relevantes do retrieval)
em vez de quebrar o template ou estourar o ``num_ctx`` do modelo.

Módulo isolado e de lógica não-trivial → TDD canônico
(ver ``tests/unit/test_prompt_builder.py``).
"""

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Template

# src/workers/query/prompt_builder.py -> parents[3] == raiz do repo
_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


@dataclass
class ContextBlock:
    """Um chunk recuperado do Qdrant, pronto para entrar no prompt."""

    source: str
    page: int | None
    text: str


def _load(name: str) -> str:
    """Lê um prompt de ``prompts/`` removendo o frontmatter YAML.

    Parameters
    ----------
    name : str
        Nome do arquivo dentro de ``prompts/`` (ex: ``system_qa_pt.md``).

    Returns
    -------
    str
        Conteúdo do prompt já sem o bloco de frontmatter entre os dois
        primeiros ``---`` (o frontmatter é metadado de versão, não vai pro
        modelo).
    """
    prompt = (_PROMPTS_DIR / name).read_text(encoding="utf-8")

    if prompt.startswith("---"):
        second_formatter_index = prompt.find("---", 3)
        if second_formatter_index != -1:
            prompt = prompt[second_formatter_index + 3 :]
            prompt = prompt.lstrip("\n")
            return prompt
        else:
            return prompt
    else:
        return prompt


def build_prompt(
    question: str,
    blocks: list[ContextBlock],
    lang: str,
    max_chars: int = 24_000,
) -> str:
    """Monta o prompt completo (system + user) com orçamento de caracteres.

    Parameters
    ----------
    question : str
        Pergunta do usuário.
    blocks : list of ContextBlock
        Chunks recuperados, na ordem de relevância do retrieval (mais
        relevante primeiro).
    lang : str
        Idioma detectado da pergunta. Só ``"pt"`` e ``"en"`` têm system
        prompt próprio; qualquer outro cai no ``pt``.
    max_chars : int, default 24_000
        Orçamento total aproximado de caracteres. Se os blocos estourarem,
        trunca pela cauda preservando os primeiros.

    Returns
    -------
    str
        Prompt final: o ``system``, uma linha em branco e o ``user``,
        nessa ordem (system + duas quebras de linha + user).
    """
    policy_prompt = f"system_qa_{lang}.md" if lang in ("en", "pt") else "system_qa_pt.md"

    system = _load(name=policy_prompt)

    user_template = Template(_load(name="user_qa_template.md"))

    tokens_budget = max_chars - len(question) - len(system) - 500

    truncated_blocks = []

    budget_used = 0

    for block in blocks:
        remaining_budget = tokens_budget - budget_used
        if remaining_budget <= 0:
            break
        if len(block.text) <= remaining_budget:
            truncated_blocks.append(block)
            budget_used += len(block.text)
        else:
            chars_that_can_be_used: ContextBlock = ContextBlock(
                text=block.text[:remaining_budget], source=block.source, page=block.page
            )
            truncated_blocks.append(chars_that_can_be_used)
            break

    user = user_template.render(question=question, context_blocks=truncated_blocks)

    user_prompt = system + "\n\n" + user

    return user_prompt
