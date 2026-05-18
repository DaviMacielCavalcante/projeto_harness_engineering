"""Recursive character splitter para o worker de ingestão.

Divide textos longos em chunks respeitando fronteiras semânticas (parágrafo,
linha, frase, palavra, caractere) e aplica overlap entre chunks adjacentes
para preservar contexto na hora do retrieval.

A aproximação de tokens é deliberadamente simples (1 token ≈ 4 caracteres):
suficiente pra dimensionar chunks sem dependência de tiktoken nesta fase.
Se necessário, B2 pode trocar `count_tokens_approx` por uma contagem real.
"""

# Ordem de tentativa: parágrafo → linha → frase → palavra → caractere.
# O último separador ("") é o sentinela de "corte hard por caractere".
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def count_tokens_approx(text: str) -> int:
    """Aproxima a contagem de tokens assumindo 1 token ≈ 4 caracteres.

    Parameters
    ----------
    text : str
        Texto a medir.

    Returns
    -------
    int
        Quantidade aproximada de tokens. Mínimo de 1 mesmo para string vazia
        (evita dividir por zero em cálculos a jusante).
    """
    tokens = len(text) // 4

    return max(1, tokens)


def _split_with_separators(text: str, separators: list[str]) -> list[str]:
    """Divide o texto pelo primeiro separador disponível, recursivamente.

    A função tenta o separador da posição 0; se não estiver presente no texto,
    recursivamente tenta o próximo. O separador vazio (`""`) é o caso-base:
    devolve o texto como uma única peça (corte hard por caractere acontece
    depois, em `chunk_text`).

    Parameters
    ----------
    text : str
        Texto a dividir.
    separators : list of str
        Separadores em ordem de prioridade (mais semântico primeiro).

    Returns
    -------
    list of str
        Pedaços do texto. Cada pedaço (exceto o último) preserva o separador
        anexado ao fim — assim a reconstituição via ``"".join(parts)`` é
        lossless.
    """
    if text == "":
        return []

    sep = separators[0]

    if sep == "":
        text_list = []

        text_list.append(text)

        return text_list

    if sep not in text:
        return _split_with_separators(text=text, separators=separators[1:])

    splitted_text = text.split(sep=sep)

    remaded_text = []

    for index, char in enumerate(splitted_text):
        if index == len(splitted_text) - 1:
            remaded_text.append(char)
        else:
            remaded_text.append(char + sep)

    return remaded_text


def chunk_text(text: str, target_tokens: int, overlap_tokens: int, max_tokens: int) -> list[str]:
    """Divide texto em chunks com teto duro garantido pós-overlap.

    Parameters
    ----------
    text : str
        Texto a dividir.
    target_tokens : int
        Tamanho-alvo de cada chunk (mira, não garantia).
    overlap_tokens : int
        Tokens repetidos entre chunks adjacentes.
    max_tokens : int
        Teto duro do modelo de embedding (ex.: 2048 p/ nomic-v1.5).

    Returns
    -------
    list of str
        Chunks na ordem original. **Invariante**: para todo chunk ``c``
        devolvido (já com overlap aplicado),
        ``count_tokens_approx(c) <= max_tokens // 2 - overlap_tokens``.
        O ``// 2`` é fator de segurança da aproximação chars/4 para
        PT + extração de PDF + WordPiece. Garantia, não mira.
    """
    overlap_chars = overlap_tokens * 4

    content_budget = (max_tokens // 2 - overlap_tokens) - overlap_tokens
    effective_target = min(target_tokens, content_budget)

    budget_chars = effective_target * 4

    if count_tokens_approx(text=text) <= effective_target:
        return [text]

    splitted_text = _split_with_separators(text=text, separators=_SEPARATORS)

    chunks: list[str] = []
    buffer = ""

    for piece in splitted_text:
        if piece == "":
            continue
        if len(piece) > budget_chars:
            if buffer != "":
                chunks.append(buffer)
                buffer = ""
            for i in range(0, len(piece), budget_chars):
                chunks.append(piece[i : i + budget_chars])
            continue
        if (len(buffer) + len(piece)) <= budget_chars:
            buffer += piece
        else:
            if buffer != "":
                chunks.append(buffer)
                buffer = piece

    if buffer != "":
        chunks.append(buffer)

    if overlap_chars > 0 and len(chunks) > 1:
        with_overlap = [chunks[0]]

        for i in range(1, len(chunks)):
            text_tail = chunks[i - 1][-overlap_chars:]
            overlapped_chunks = text_tail + chunks[i]
            with_overlap.append(overlapped_chunks)

        chunks = with_overlap

    return chunks
