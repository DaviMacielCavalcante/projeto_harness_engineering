# Testes e Qualidade de Software

Qualidade de software envolve corretude, manutenibilidade, segurança,
desempenho, observabilidade e capacidade de evolução. Testes automatizados são
um mecanismo para proteger esses atributos.

## Testes unitários

Testes unitários validam unidades pequenas de comportamento, como funções puras,
schemas e regras de transformação. Eles devem ser rápidos, determinísticos e
independentes de serviços externos.

## Testes de integração

Testes de integração validam contratos entre componentes reais, como gateway,
RabbitMQ, Redis, Qdrant e workers. Eles são mais caros, mas encontram falhas que
testes unitários não enxergam.

## Smoke tests

Smoke tests validam o caminho principal ponta a ponta. Em um RAG, isso significa
enviar documento, aguardar indexação e executar uma pergunta com citações.
