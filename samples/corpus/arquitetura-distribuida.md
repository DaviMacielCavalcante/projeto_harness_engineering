# Arquitetura Distribuída

Um sistema distribuído divide responsabilidades entre processos que podem rodar
em máquinas diferentes. Essa divisão permite escalar partes específicas do
sistema, mas também introduz latência de rede, falhas parciais e necessidade de
observabilidade.

## Comunicação

Comunicação síncrona, como HTTP, é simples para clientes externos. Comunicação
assíncrona, como filas RabbitMQ, desacopla produtores e consumidores e permite
absorver picos de carga. Em pipelines de dados, filas também ajudam a separar
estágios com custos diferentes.

## Falhas parciais

Em sistemas distribuídos, uma dependência pode falhar enquanto outras continuam
saudáveis. Por isso, retries, timeouts, DLQs e modos degradados são mecanismos
fundamentais para manter o sistema operável.
