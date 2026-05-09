# Declaração de uso de IA

> **Atendimento ao requisito do enunciado:** *"TODA ferramenta ou IA utilizada deve ser justificada."*
>
> Esta seção documenta de forma transparente o uso de ferramentas de IA na construção deste projeto, em conformidade com a instrução acima e com as melhores práticas acadêmicas de divulgação.

## 1. Ferramentas de IA utilizadas

### 1.1 Claude Code (Anthropic) — assistente de engenharia

- **Produto:** Claude Code, CLI oficial da Anthropic para desenvolvimento assistido por IA.
- **Modelo principal:** Claude Opus 4.7 (`claude-opus-4-7`), com effort `high`.
- **Período de uso:** a partir de 2026-05-09.
- **Onde acessar:** https://claude.com/claude-code

### 1.2 Skills/plugins ativados

Foi utilizada a coleção de skills `superpowers` (oficial Anthropic), em especial:
- `superpowers:brainstorming` — estrutura de diálogo socrático para refinar ideias e gerar especificações.
- `superpowers:writing-plans` — estrutura para gerar planos de implementação detalhados a partir de uma spec aprovada.
- `superpowers:writing-skills`, `superpowers:test-driven-development` (referência indireta).

## 2. O que a IA fez

A IA foi utilizada como **co-piloto técnico** nas seguintes etapas, sob direção e revisão humana contínua:

### 2.1 Brainstorming e design (sessão de 2026-05-09)
- Leitura do PDF do enunciado (`Engenharia de Contexto e Harness.pdf`) e síntese dos requisitos mínimos.
- Diálogo estruturado de perguntas socráticas (uma de cada vez) para esclarecer:
  - Tema escolhido (Tema 5).
  - Domínio do corpus (engenharia de software).
  - Hardware disponível dos integrantes.
  - Topologia desejada (3 PCs via Tailscale).
  - Escala da demo, abordagem de IaC, escolha de mensageria, escolha de servidor de inferência.
- Proposição de **3 abordagens arquiteturais** com trade-offs (A pragmática, B mensageria clássica, C bônus máximo via vLLM); a equipe escolheu uma combinação informada.
- Geração da spec consolidada em [`docs/superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md`](superpowers/specs/2026-05-09-rag-distribuido-tema5-design.md), incluindo arquitetura, componentes, fluxos, engenharia de contexto, métricas, tolerância a falhas, IaC, plano experimental, divisão de trabalho, cronograma, mapeamento de entregáveis e riscos.

### 2.2 Geração dos planos de implementação
- Plano detalhado por bloco do cronograma (`docs/superpowers/plans/`), em formato TDD onde aplicável, com:
  - Estrutura de arquivos a criar/modificar.
  - Código de testes e implementação.
  - Comandos com saída esperada.
  - Cortes pré-definidos caso o cronograma aperte.

### 2.3 Geração de código boilerplate (a partir de B1)
- Esqueletos de FastAPI, configurações `pydantic-settings`, wrappers HTTP `httpx`, helpers `aio-pika`, Dockerfiles, `docker-compose.yml`, `Makefile`, prompts versionados.
- A IA escreveu **código de partida**; a equipe revisa, ajusta, corrige bugs, integra entre máquinas reais, escreve testes complementares, executa, mede e documenta os resultados.

### 2.4 Apoio à documentação
- Esqueleto do documento técnico final (8.2).
- Esqueleto dos slides da apresentação (8.3).

## 3. O que os integrantes da equipe fazem

A equipe é responsável por:

1. **Decisões de escopo e priorização** — todas as escolhas técnicas (Tema 5, RabbitMQ vs Redis Streams, Ollama + experimento vLLM, topologia de 3 PCs) foram tomadas pela equipe a partir das opções apresentadas pela IA, com justificativa registrada nas perguntas e respostas.
2. **Validação técnica** — toda recomendação da IA foi confrontada com o enunciado e com a viabilidade prática (hardware disponível, prazo, conhecimento da equipe).
3. **Implementação e debugging em ambiente real** — subir os containers, configurar Tailscale entre os 3 PCs reais, lidar com problemas específicos da rede, rodar os experimentos, interpretar métricas, ajustar prompts a partir dos resultados.
4. **Escrita do documento técnico final, dos slides e dos relatórios individuais** — a IA fornece esqueletos; a redação final, a análise dos resultados experimentais e a interpretação são de autoria da equipe.
5. **Apresentação ao vivo** — demo + defesa pública é responsabilidade exclusiva dos integrantes.
6. **Aprendizado dos conceitos** — cada integrante é responsável por compreender o que está implementando, ao ponto de defender suas escolhas em arguição.

## 4. Limites e princípios adotados

- **Sem "ghost writing":** o uso da IA é declarado, não escondido. Esta seção e a equivalente no documento técnico tornam explícito o que veio de IA.
- **Revisão humana obrigatória:** nenhum trecho de código gerado por IA entra no projeto sem ser lido, compreendido e validado por pelo menos um integrante.
- **Decisões críticas com humanos no comando:** escopo, arquitetura, prioridades, divisão de trabalho e prazo são decididos pela equipe; a IA propõe, a equipe dispõe.
- **Aprendizado prioritário sobre velocidade:** quando há trade-off entre velocidade e compreensão, a equipe escolhe entender antes de prosseguir, mesmo que isso signifique reescrever trechos sugeridos pela IA.

## 5. Justificativa pedagógica

O uso de assistentes de IA está sendo incorporado ao currículo de engenharia de software como ferramenta de produtividade legítima — exatamente como, em décadas passadas, IDEs com auto-completion, depuradores integrados e sistemas de versionamento foram absorvidos. A própria disciplina ("Engenharia de Contexto e Harness Engineering aplicada à Programação Distribuída e Paralela") tem como objeto de estudo os sistemas que orquestram modelos de linguagem, o que torna o uso assistido por IA tematicamente coerente.

A equipe entende que o valor educacional desta atividade está em:
- compreender os conceitos de paralelismo, distribuição, mensageria, tolerância a falhas;
- praticar engenharia de contexto explícita;
- analisar empiricamente os trade-offs;
- documentar decisões técnicas.

Nenhum desses objetivos é prejudicado pelo uso de IA como co-piloto — pelo contrário, o uso responsável libera tempo para focar em validação, experimentação e análise, que são precisamente os pontos com maior peso na avaliação.

## 6. Outras ferramentas e bibliotecas open-source utilizadas

Para completude, o projeto usa também (sem componente de IA generativa):

| Ferramenta | Função |
|---|---|
| Python 3.12 + `uv` | runtime e gerenciamento de dependências |
| FastAPI + Uvicorn | API gateway HTTP |
| RabbitMQ | mensageria |
| Qdrant | vector database |
| Redis | cache distribuído |
| Ollama | servidor de SLM (linha-base) |
| vLLM | servidor de SLM com continuous batching (experimento) |
| Prometheus + Grafana + Loki | observabilidade |
| Terraform (provider `kreuzwerker/docker`) | IaC dos containers |
| Ansible | provisionamento dos hosts |
| Tailscale | rede privada virtual entre os 3 PCs |
| pytest, ruff | testes e lint |

Os modelos de linguagem hospedados (`qwen2.5:7b-instruct`, `nomic-embed-text`, `BAAI/bge-reranker-v2-m3`) também são ferramentas de IA, porém **objeto da pesquisa** — eles são o que estamos orquestrando, não quem nos ajuda a orquestrar. O experimento Ollama vs vLLM analisa empiricamente o comportamento dessas ferramentas sob carga.

---

**Última atualização:** 2026-05-09. Este documento será atualizado se o padrão de uso da IA mudar significativamente ao longo do desenvolvimento.
