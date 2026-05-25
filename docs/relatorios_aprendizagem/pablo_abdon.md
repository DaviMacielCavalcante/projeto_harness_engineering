# Relatório de aprendizagem - Pablo Abdon

> Status: rascunho didático para revisão do Pablo antes da entrega.

- **Disciplina:** Engenharia de Contexto e Harness Engineering aplicada à Programação Distribuída e Paralela
- **Tema:** 5 - Sistema RAG distribuído em PCs físicos via Tailscale
- **Período relatado:** fechamento do B3/B4/B5
- **Trilha:** workers, operação local, observabilidade, corpus e scripts operacionais

## 1. Visão geral do projeto

O projeto é um sistema de perguntas e respostas usando RAG, que significa
Retrieval-Augmented Generation. Em termos simples, o sistema não tenta responder
só com o que o modelo de IA "sabe". Ele primeiro procura trechos relevantes em
um conjunto de documentos, coloca esses trechos no contexto do modelo e só então
pede uma resposta.

A ideia é evitar respostas inventadas. Se o sistema encontra um trecho bom no
corpus, ele usa esse trecho para responder e citar a fonte. Se não encontra, a
resposta correta deveria ser dizer que a informação não está no corpus.

O projeto também é distribuído. Isso quer dizer que ele foi pensado para rodar
em mais de uma máquina física, conectadas por Tailscale. Uma máquina concentra
serviços principais, como gateway, banco vetorial, mensageria e modelo local. As
outras máquinas podem rodar workers, que são processos que pegam tarefas em
filas e executam trabalho pesado.

## 2. Como o sistema funciona

O sistema tem duas jornadas principais: ingestão de documentos e resposta a
perguntas.

Na ingestão, um documento é enviado para o gateway pelo endpoint `POST /ingest`.
O gateway não processa tudo diretamente. Ele publica uma mensagem no RabbitMQ,
que é o sistema de filas. Depois, os workers de ingestão pegam essa mensagem.

O primeiro worker de ingestão lê o documento, extrai o texto e quebra esse texto
em pedaços menores, chamados chunks. Essa etapa é importante porque um documento
inteiro costuma ser grande demais e pouco preciso para busca semântica.

O segundo worker pega cada chunk, pede ao Ollama um embedding e grava esse vetor
no Qdrant. Um embedding é uma representação numérica do significado do texto. O
Qdrant guarda esses vetores para permitir buscar trechos parecidos com uma
pergunta.

Na jornada de pergunta, o usuário chama `POST /query`. O gateway publica a
pergunta em outra fila do RabbitMQ. O query-worker consome essa pergunta,
transforma a pergunta em embedding, busca chunks parecidos no Qdrant, passa os
melhores candidatos pelo rerank-service e monta o prompt final para o modelo de
linguagem.

O modelo usado localmente roda no Ollama. No ambiente leve desta máquina, usamos
`llama3.2:1b` para geração e `nomic-embed-text` para embeddings. Em uma máquina
com GPU NVIDIA, o projeto pode usar um modelo maior, como `qwen2.5:7b-instruct`.

## 3. Componentes principais

O **gateway** é a porta de entrada HTTP do sistema. Ele recebe documentos e
perguntas, mas delega o processamento para filas e workers.

O **RabbitMQ** é a mensageria. Ele organiza as filas de documentos, chunks,
queries e DLQs. DLQ significa Dead Letter Queue: é onde caem mensagens que
falharam repetidas vezes e precisam de inspeção.

O **Qdrant** é o banco vetorial. Ele guarda os embeddings dos chunks e permite
buscar os trechos mais parecidos com uma pergunta.

O **Redis** é usado para cache e sessão. O cache evita repetir trabalho caro,
como embedding de perguntas ou respostas já calculadas.

O **Ollama** serve os modelos locais. Ele gera embeddings e respostas.

O **rerank-service** melhora a ordem dos trechos recuperados. Primeiro o Qdrant
busca candidatos de forma rápida; depois o reranker tenta escolher os mais
relevantes com mais precisão.

Os **workers** são processos que ficam escutando filas. Eles não recebem HTTP do
usuário diretamente. Por isso, para o Prometheus conseguir monitorá-los, foi
necessário adicionar um pequeno servidor HTTP de métricas dentro deles.

## 4. O papel da minha parte

A minha parte entrou principalmente no fechamento operacional do projeto. O
sistema já tinha pipeline, filas, prompts, cache, observabilidade parcial e
documentação técnica. O que faltava era destravar pontos práticos para validar a
demo e o dashboard.

O item mais importante foi implementar `/metrics` nos workers. Antes disso, o
Prometheus tentava raspar os workers, mas eles não tinham endpoint HTTP. Por
isso o job `workers` ficava `DOWN` no Prometheus e alguns painéis do Grafana não
tinham dados.

Foi criado o arquivo `src/shared/workers_metrics_server.py`, usando `aiohttp`.
Esse arquivo sobe um servidor HTTP pequeno com a rota `/metrics`. Ele reutiliza
o registro Prometheus já existente em `src/shared/metrics.py`, então não foi
preciso inventar métricas novas. O trabalho foi expor as métricas no processo
certo.

Depois, esse servidor foi ligado no bootstrap dos workers:

- `src/workers/ingest/main.py`;
- `src/workers/query/main.py`.

Também foram expostas portas diferentes no `docker-compose.yml`:

- `9100` para `ingest-worker-doc`;
- `9101` para `ingest-worker-chunk`;
- `9102` para `query-worker`.

Com isso, validamos que:

- `http://localhost:9100/metrics` retorna métricas `rag_*`;
- `http://localhost:9101/metrics` retorna métricas `rag_*`;
- `http://localhost:9102/metrics` retorna métricas `rag_*`;
- no Prometheus, os três workers aparecem como `UP`.

## 5. Scripts operacionais criados

Também foram criados scripts para facilitar a operação do sistema.

O `scripts/seed_corpus.py` envia arquivos de uma pasta para o endpoint
`POST /ingest`. Ele lê PDFs, Markdown e HTML, converte o conteúdo para base64 e
registra quantos arquivos foram enviados e quantos falharam. Isso serve para
popular o Qdrant de forma repetível.

O `scripts/dlq_inspector.py` permite inspecionar filas de erro. Ele tem três
comandos:

- `list <queue.dlq>` para listar mensagens na DLQ;
- `replay <queue.dlq> --limit N` para reenviar mensagens para a fila original;
- `purge <queue.dlq> --yes` para limpar a DLQ.

O `scripts/chaos_test.sh` e o `scripts/chaos_test.ps1` executam cenários simples
de falha:

- parar e religar o worker de chunks;
- parar e religar o Ollama;
- enviar uma rajada de queries concorrentes.

Esses scripts ajudam a mostrar que o sistema não é só código feliz. Ele também
tem ferramentas para observar e testar comportamento em falha.

## 6. Corpus e avaliação

Foi criado um corpus mínimo em `samples/corpus/` com documentos Markdown
originais sobre engenharia de software, arquitetura distribuída, testes,
observabilidade, padrões de projeto e RAG.

Esse corpus não substitui um corpus grande de escala, como dezenas de PDFs, mas
serve para validar o funcionamento local sem commitar arquivos pesados ou de
terceiros.

Também foi criado `data/eval_queries.jsonl` com 30 perguntas em português e
inglês. Esse arquivo serve como base para testes de avaliação e experimentos.

Na validação local, o seed enviou 6 documentos com `falhas=0`, e o Qdrant ficou
com `points_count=6`.

## 7. Tecnologias usadas

Usei e validei as seguintes tecnologias:

- **Python 3.12** para o código da aplicação e scripts.
- **uv** para executar comandos no ambiente Python do projeto.
- **FastAPI** no gateway e no rerank-service.
- **aiohttp** para criar o servidor `/metrics` dos workers.
- **RabbitMQ** para filas e DLQs.
- **aio-pika** para acessar RabbitMQ nos scripts e workers.
- **Qdrant** como banco vetorial.
- **Redis** para cache e sessão.
- **Ollama** para rodar modelos locais.
- **Prometheus** para coletar métricas.
- **Grafana** para visualizar métricas em dashboard.
- **Loki/Promtail** para logs estruturados.
- **Docker Compose** para subir a stack local.
- **Tailscale** para conectar máquinas físicas em rede privada.

## 8. O que foi validado na prática

Nesta máquina, que agora é a máquina real prevista para rodar o worker, a stack
subiu localmente com Docker Compose. Como ela tem GPU AMD e não NVIDIA, o
serviço do Ollama falhou inicialmente por causa da reserva de GPU NVIDIA no
Compose. Isso não era bug da aplicação. A solução local foi criar um
`docker-compose.override.yml` ignorado pelo Git para remover a reserva de GPU
apenas neste ambiente.

Depois disso, os containers subiram, os modelos leves foram baixados, o seed do
corpus funcionou e o smoke test passou.

Também foi validado:

- `ruff` sem erros;
- `mypy` sem erros;
- testes unitários com `62 passed`;
- Prometheus com workers `UP`;
- DLQ inspector listando `ingest.chunks.dlq`;
- chaos test gerando evidência em `data/exp4/chaos.txt` e `data/b3-chaos.txt`.

## 9. Sobre a `abdon-workstation` e o Tailscale

Inicialmente, a documentação tratava a `abdon-workstation` como o host oficial
da minha trilha. Na prática, ela não será usada para rodar o worker final. Ela
servirá apenas como máquina de teste para validar o funcionamento do Tailscale.

A máquina que realmente vai conectar ao ambiente distribuído e subir o worker é
esta máquina atual. O Tailscale já foi instalado e esta máquina já entrou na
tailnet; também já é possível enxergar as outras máquinas na rede. O que ainda
falta é validar, com o Davi disponível, se esta máquina consegue acessar os
serviços do PC1 pela tailnet:

- RabbitMQ na porta `5672`;
- Ollama na porta `11434`;
- Qdrant na porta `6333`;
- Redis na porta `6379`;
- rerank-service na porta `8081`.

## 10. O que eu aprendi

O principal aprendizado foi entender que, em um sistema distribuído, fazer a
funcionalidade funcionar não é suficiente. Também é preciso conseguir operar o
sistema: ver métricas, testar falhas, popular dados, inspecionar filas e saber
quando uma falha é do código ou do ambiente.

Também aprendi que workers de fila são diferentes de serviços HTTP. Eles fazem
trabalho em background, mas ainda precisam expor sinais para observabilidade. O
endpoint `/metrics` nos workers foi importante justamente por isso: ele conectou
o trabalho interno dos consumidores ao dashboard do Grafana.

Outro aprendizado foi sobre ambiente local. O Compose principal estava preparado
para GPU NVIDIA, mas esta máquina usa AMD. A falha do Ollama mostrou que nem
toda falha de container é erro da aplicação. Às vezes é uma incompatibilidade
entre a configuração de infraestrutura e o hardware disponível.

Por fim, entendi melhor o papel do Tailscale. Ele não é parte da lógica de RAG,
mas é o que permite transformar PCs separados em uma rede privada onde os
workers conseguem acessar os serviços centrais com segurança.

## 11. Próximos passos

Os próximos passos não são mais de implementação principal no workspace. Eles
são principalmente de ambiente:

- confirmar/anotar o IP da tailnet;
- validar conectividade com o PC1;
- subir esta máquina como worker no modo distribuído;
- usar a `abdon-workstation` apenas como teste simples de Tailscale;
- se houver tempo, rodar experimentos com corpus maior.

Com isso, minha parte deixa de ser só "escrever código" e passa a ser garantir
que a máquina realmente participa do sistema distribuído.
