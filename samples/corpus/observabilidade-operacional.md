# Observabilidade Operacional

Observabilidade é a capacidade de entender o estado interno de um sistema a
partir de sinais externos. Em produção, os sinais principais são métricas, logs
e traces.

## Métricas

Métricas respondem perguntas agregadas no tempo: taxa de erro, latência p95,
throughput, tokens processados e cache hit ratio. Prometheus é adequado para
raspar endpoints `/metrics` e armazenar séries temporais.

## Logs estruturados

Logs estruturados registram eventos específicos com campos consistentes, como
`service`, `level` e `correlation_id`. Eles ajudam a reconstruir uma falha
individual depois que uma métrica mostrou anomalia.

## Dashboards

Dashboards não substituem investigação, mas organizam sinais críticos para
operação e demonstração. Um bom dashboard separa unidades diferentes em painéis
diferentes para evitar leituras enganosas.
