# Engenharia de Software para Corpus de Demonstração

## Arquitetura de software

Arquitetura de software descreve as decisões estruturais de um sistema:
componentes, responsabilidades, contratos, comunicação e restrições de
implantação. Em sistemas distribuídos, a arquitetura também precisa explicitar
latência, tolerância a falhas, observabilidade e isolamento entre serviços.

## Padrões de projeto

Padrões de projeto são soluções recorrentes para problemas de desenho de
software. Strategy permite trocar algoritmos em tempo de execução; Adapter
integra interfaces incompatíveis; Factory centraliza a criação de objetos; e
Observer desacopla produtores de eventos de seus consumidores.

## Testes e qualidade

Qualidade de software combina corretude, manutenibilidade, desempenho,
segurança e experiência operacional. Testes unitários validam regras locais,
testes de integração validam contratos entre serviços, e testes de fumaça
confirmam que o fluxo ponta a ponta segue funcionando em ambiente real.

## RAG e engenharia de contexto

Um sistema RAG recupera trechos relevantes de um corpus e injeta esses trechos
no prompt do modelo gerador. A qualidade depende de chunking coerente,
retrieval com bons embeddings, re-ranking quando necessário, prompts claros e
citações rastreáveis para reduzir alucinação.
