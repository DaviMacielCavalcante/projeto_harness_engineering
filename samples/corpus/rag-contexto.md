# RAG e Engenharia de Contexto

Retrieval-Augmented Generation combina recuperação de informação com geração de
texto. O sistema primeiro recupera trechos relevantes de um corpus e depois
entrega esses trechos ao modelo de linguagem para produzir uma resposta
fundamentada.

## Chunking

Chunking divide documentos em blocos menores. Bons chunks preservam fronteiras
semânticas, como parágrafos e frases, para que o embedding represente uma ideia
coerente em vez de uma mistura de assuntos.

## Retrieval e rerank

Retrieval por embedding encontra candidatos semanticamente próximos. Um
re-ranker pode ordenar esses candidatos com mais precisão porque compara a
pergunta e cada trecho em conjunto.

## Citações

Citações tornam a resposta auditável. Cada afirmação importante deve apontar
para uma fonte, página ou trecho do corpus.
