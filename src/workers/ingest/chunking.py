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
    # TODO 1: implementar. Dica: len(text) // 4, com piso de 1 (use max).
    raise NotImplementedError


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
    # TODO 2.1: caso-base — se text vazio, retornar lista vazia.
    # TODO 2.2: pegar o separador da posição 0. Se for "" (sentinela),
    #           devolver [text] — quem corta hard é o caller (chunk_text).
    # TODO 2.3: se o separador NÃO está no texto, recursão com separators[1:].
    # TODO 2.4: text.split(sep) divide. Mas perde os separadores no meio.
    #           Itere as parts e, em todas exceto a última, reanexe `sep` no
    #           fim. Assim "".join(out) reconstitui o texto original.
    raise NotImplementedError


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
    # TODO 3.1: converter tokens em chars (multiplica por 4) para
    #           `target_chars` e `overlap_chars`.

    # TODO 3.2: atalho — se count_tokens_approx(text) <= target_tokens,
    #           retorne [text] direto.

    # TODO 3.3: chame `_split_with_separators(text, _SEPARATORS)` para obter
    #           a lista `pieces`. Inicialize `chunks: list[str] = []` e um
    #           `buffer = ""`.

    # TODO 3.4: iterar as `pieces`. Para cada `piece`:
    #     a) se piece é "", continue (separador puxou string vazia, ignora).
    #     b) se len(piece) > target_chars: a peça já estoura sozinha.
    #        - se há buffer pendente, dê push em chunks e zere o buffer.
    #        - faça hard split por chars com passo (target_chars - overlap_chars)
    #          chamando chunks.append(piece[i : i + target_chars]) em loop.
    #        - continue para a próxima piece.
    #     c) se len(buffer) + len(piece) <= target_chars:
    #        - buffer += piece (acumula).
    #     d) senão:
    #        - se buffer não vazio, chunks.append(buffer).
    #        - buffer = piece (começa novo).

    # TODO 3.5: fim do loop — se buffer ainda tem conteúdo, chunks.append(buffer).

    # TODO 3.6: aplicar overlap. Se overlap_chars > 0 e len(chunks) > 1:
    #           construa with_overlap começando com chunks[0] inalterado;
    #           para cada i >= 1, prepend dos últimos overlap_chars do
    #           chunks[i-1] no começo de chunks[i].
    #           Substitua `chunks = with_overlap` no fim.

    # TODO 3.7: return chunks.
    raise NotImplementedError
