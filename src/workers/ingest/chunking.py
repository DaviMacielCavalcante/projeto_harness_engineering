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


def chunk_text(text: str, target_tokens: int, overlap_tokens: int) -> list[str]:
    """Divide texto em chunks recursivamente respeitando fronteiras semânticas.

    Estratégia em três fases:

    1. Atalho — se o texto inteiro já cabe em `target_tokens`, devolve
       ``[text]`` sem dividir.
    2. Acumulação — `_split_with_separators` quebra o texto em peças;
       acumula-se peças num buffer até que adicionar a próxima estoure
       `target_chars`. Quando estoura, fecha o buffer como chunk e começa
       um novo.
    3. Overlap — após formar os chunks, prepend dos últimos `overlap_chars`
       do chunk anterior no começo do próximo (exceto o primeiro).

    Caso especial: se uma única peça já é maior que `target_chars`, força
    corte hard por caractere com passos de ``target_chars - overlap_chars``.

    Parameters
    ----------
    text : str
        Texto a dividir.
    target_tokens : int
        Tamanho alvo de cada chunk em tokens (aprox. 4 chars/token).
    overlap_tokens : int
        Quantidade de tokens repetidos entre chunks adjacentes.

    Returns
    -------
    list of str
        Chunks na ordem original. Tolerância: até 25% acima de
        `target_tokens` por chunk para acomodar fronteira semântica.
    """
    target_chars = target_tokens * 4
    overlap_chars = overlap_tokens * 4

    if count_tokens_approx(text=text) <= target_tokens:
        return [text]

    splitted_text = _split_with_separators(text=text, separators=_SEPARATORS)

    chunks: list[str] = []
    buffer = ""

    for piece in splitted_text:
        if piece == "":
            continue
        if len(piece) > target_chars:
            if buffer != "":
                chunks.append(buffer)
                buffer = ""
            for i in range(0, len(piece), target_chars - overlap_chars):
                chunks.append(piece[i : i + target_chars])
            continue
        if (len(buffer) + len(piece)) <= target_chars:
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
