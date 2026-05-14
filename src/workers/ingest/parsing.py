"""Parser de documentos para o worker de ingestão.

Responsável por transformar o payload base64 que chega via fila em uma lista de
páginas extraíveis. PDFs entram pelo `pypdf`; markdown e HTML são tratados como
texto bruto nesta fase (parsing rico de HTML com `trafilatura` fica para B2).

A unidade devolvida é sempre uma lista de tuplas `(page_number, text)`. Para
formatos sem paginação (md, html), `page_number` é `None` e a lista tem um
único elemento com o documento inteiro.
"""

import base64
import io

from pypdf import PdfReader

from src.shared.schemas import SourceType


def parse_document(
    content_b64: str,
    source_type: SourceType,
) -> list[tuple[int | None, str]]:
    """Decodifica o payload e roteia para o parser apropriado por tipo.

    Parameters
    ----------
    content_b64 : str
        Conteúdo do documento codificado em base64 (como chega da fila).
    source_type : SourceType
        Tipo da fonte: ``"pdf"``, ``"md"`` ou ``"html"``.

    Returns
    -------
    list of tuple of (int or None, str)
        Lista de páginas. Para PDF, ``page_number`` começa em 1. Para md/html,
        a lista tem um único item com ``page_number = None``.

    Raises
    ------
    ValueError
        Se ``source_type`` não for um dos valores suportados.
    """
    
    # TODO 1: decodificar content_b64 com base64.b64decode → bytes (raw).
    raw: bytes = base64.b64decode(content_b64)
    
    if source_type == "pdf":
        return _parse_pdf(raw=raw)
    
    if source_type == "md":
        return ([None, raw.decode("utf-8", errors="replace")])
    
    if source_type == "html":
        return ([None, raw.decode("utf-8", errors="replace")])

    raise ValueError("Formato de origem não suportado!")


def _parse_pdf(raw: bytes) -> list[tuple[int | None, str]]:
    """Extrai texto de cada página do PDF preservando o número de página.

    Parameters
    ----------
    raw : bytes
        Bytes do arquivo PDF.

    Returns
    -------
    list of tuple of (int or None, str)
        Uma tupla por página com texto não-vazio. ``page_number`` começa em 1.
        Páginas em branco (texto vazio após `extract_text`) são descartadas.
    """
    
    pdf_reader = PdfReader(io.BytesIO(raw))
    
    pdf_text = []
    
    for i, page in enumerate(pdf_reader.pages, start=1):
        
        page_text = page.extract_text()
        if page_text.strip() != "":
            pdf_text.append((i, page_text))
        
    return pdf_text
