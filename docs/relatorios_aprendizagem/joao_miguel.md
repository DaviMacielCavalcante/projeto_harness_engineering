# Relatório de aprendizagem — João Miguel

> **Status:** rascunho gerado a partir das atividades da sessão de 2026-05-23. João Miguel precisa revisar, ajustar a voz, complementar com o que ficou de fora e assumir a autoria antes da entrega.

- **Disciplina:** Engenharia de Contexto e Harness Engineering aplicada à Programação Distribuída e Paralela
- **Tema:** 5 — Sistema RAG distribuído em 3 PCs físicos via Tailscale
- **Período relatado:** 2026-05-23 (sessão de onboarding + IaC — Bloco B3, Trilha C)
- **Instituição:** CESUPA, 2º bimestre de 2026

---

## 1. O que eu contribuí até este ponto

Na sessão de hoje entrei no projeto como integrante da Trilha C (colega 2, PC3), com o Bloco B1 já concluído pelo autor (Davi) e parte do B2 encaminhada. Meu foco foi compreender o sistema como um todo e assumir as responsabilidades da Trilha C a partir do B3.

Concretamente, produzi:

- **Leitura e entendimento da arquitetura completa** — percorri o `CLAUDE.md`, o `TODO.md`, os planos B1–B5 e o código-fonte dos workers de ingestão, mapeando como cada peça se encaixa.
- **Entendimento do pipeline de ingestão** — compreendi as três etapas (`parsing.py` → `chunking.py` → `main.py`) e por que o sistema usa chunking recursivo com overlap antes de embedar.
- **Exploração do Docker Compose** — entendi como subir apenas os serviços necessários para o worker de ingestão (sem gateway, sem query worker, sem Redis).
- **`infra/terraform/variables.tf`** — variáveis tipadas do módulo: `host_role`, IPs Tailscale, URLs dos serviços, `image_tag`.
- **`infra/terraform/main.tf`** — provider `kreuzwerker/docker`, rede `rag-network` e instanciação condicional dos módulos `server`/`worker` com base em `host_role`.
- **`infra/terraform/outputs.tf`** — outputs básicos do root module.
- **`infra/terraform/modules/server/main.tf`** — descrição declarativa dos containers do PC1: RabbitMQ (com healthcheck e plugin Prometheus), Qdrant, Redis, Ollama e Gateway, cada um com volumes nomeados e portas.
- **`infra/terraform/modules/worker/main.tf`** — containers dos PC2/PC3: `ingest-worker-doc`, `ingest-worker-chunk` e `query-worker`, com `INGEST_ROLE` e `METRICS_PORT` por container.
- **`infra/terraform/envs/pc1.tfvars`**, **`pc2.tfvars`**, **`pc3.tfvars`** — configuração por host, com placeholders Tailscale nos workers.
- **`infra/ansible/inventory.yml`** — inventário dos 3 hosts com variáveis de papel (`host_role`, `gpu_enabled`).
- **`infra/ansible/ansible.cfg`** — configuração básica (sem verificação de host key, callback yaml).
- **`infra/ansible/playbook-bootstrap.yml`** — instala Docker e Tailscale em todos os hosts; NVIDIA Container Toolkit só no PC1.
- **`infra/ansible/playbook-deploy.yml`** — sincroniza o repositório via rsync, gera `.env.local` a partir do template Jinja2 e executa `terraform apply` em cada host.
- **`infra/ansible/roles/docker/tasks/main.yml`** — role que instala `docker-ce` + `docker-compose-plugin` via apt.
- **`infra/ansible/roles/tailscale/tasks/main.yml`** — role que adiciona repositório e instala `tailscale`.
- **`infra/ansible/roles/nvidia/tasks/main.yml`** — role exclusiva do PC1 que instala `nvidia-container-toolkit` e reconfigura o runtime do Docker.
- **`infra/ansible/env.j2`** — template Jinja2 que gera o `.env.local` em cada host com os IPs Tailscale do PC1.
- **`scripts/deploy.sh`** — wrapper shell que chama os dois playbooks em sequência.

---

## 2. Aprendizados técnicos

### 2.1 Entender o que o worker de ingestão faz (e por quê)

Antes de codar qualquer coisa, precisei entender o que o sistema faz. O pipeline de ingestão percorre três etapas:

**parse → chunk → embed → upsert**

O `parsing.py` recebe o documento em base64 e devolve uma lista de `(página, texto)`. O PDF é lido página a página com `pypdf`; Markdown e HTML entram como texto bruto. A saída é uniforme — qualquer formato vira o mesmo tipo, e o chunker não precisa saber de onde veio.

O `chunking.py` parte o texto em pedaços menores. Antes de entrar neste projeto, eu associava "dividir texto" a um `split(" ")` ou similar. Aqui aprendi dois motivos reais para o chunking existir:

**Granularidade do retrieval.** Se eu indexasse uma página inteira como um vetor só, o Qdrant conseguiria dizer "este documento é relevante" — mas o LLM receberia a página inteira no contexto, consumindo tokens sem precisão. Com chunks de \~800 tokens, o retrieval traz o parágrafo certo. É a diferença entre "este livro fala sobre X" e "este parágrafo responde X".

**Qualidade do embedding.** O `nomic-embed-text` gera um vetor de 768 dimensões. Quanto maior o texto, mais o vetor representa a "média" do conteúdo e perde os detalhes específicos. Chunks menores produzem vetores mais focados semanticamente, que casam melhor com perguntas específicas.

O overlap de 120 tokens (repetir o final do chunk anterior no começo do próximo) existe porque uma frase importante que cai exatamente na fronteira entre dois chunks seria cortada — nenhum dos dois ficaria com ela inteira, e o retrieval poderia perdê-la. O overlap é uma redundância barata que paga em recall.

O `main.py` é o worker que consome a fila RabbitMQ `ingest.documents`, orquestra as três etapas e faz `upsert` no Qdrant. O id de cada ponto é derivado de `sha256(doc_id:chunk_index)` — isso torna o upsert **idempotente**: reenviar o mesmo documento sobrescreve os mesmos pontos em vez de duplicar o corpus.

### 2.2 Docker Compose: profiles vs nomeação explícita

Quando quis subir só o worker de ingestão e suas dependências sem subir o sistema todo, deparei com o conceito de **profiles** no Compose. Os serviços do projeto estão distribuídos em três profiles: `all`, `server` e `worker`.

A confusão inicial foi: se o `ingest-worker` está no profile `worker` e o `rabbitmq` está no profile `server`, como subo só esses dois? A resposta é que **nomear um serviço explicitamente na linha de comando anula a restrição de profile**:

```bash
docker compose up -d --build rabbitmq qdrant ollama ingest-worker
```

Este comando sobe exatamente esses quatro, independente dos profiles. O Compose respeita o `depends_on` normalmente — se eu tivesse nomeado só `ingest-worker`, as dependências teriam sido puxadas automaticamente.

Aprendi também que o container de `ingest-worker` só usa `nomic-embed-text` (embeddings), não o modelo de geração (`qwen2.5:7b-instruct`). Isso é importante para economizar tempo e VRAM quando só se quer testar a ingestão.

### 2.3 Terraform com provider Docker — IaC sem cloud

A minha experiência anterior com Terraform era superficial e sempre associada à AWS. Este projeto usa o provider `kreuzwerker/docker`, que gerencia **containers Docker locais** em vez de recursos de cloud.

O conceito fundamental que ficou claro: **Terraform descreve o estado desejado, não os passos para chegar lá**. Eu declaro "quero um container chamado `rag-rabbitmq`, com esta imagem, estas variáveis de ambiente, estas portas" — e o Terraform calcula o que precisa criar, modificar ou destruir para chegar nesse estado. É declarativo, não imperativo.

A estrutura de módulos que criei — `modules/server` e `modules/worker` — reflete a topologia distribuída:

- O módulo `server` descreve o que roda no PC1: a infraestrutura toda (RabbitMQ, Qdrant, Redis, Ollama) e o gateway.
- O módulo `worker` descreve o que roda nos PC2/PC3: os workers de ingestão e de query, apontando para os serviços do PC1 via IPs Tailscale.

O `main.tf` instancia esses módulos condicionalmente com base na variável `host_role`:

```hcl
module "server" {
  count  = var.host_role == "server" ? 1 : 0
  source = "./modules/server"
  ...
}
```

Se `host_role = "worker"`, o count do módulo `server` é zero — nada é criado. Isso permite usar o **mesmo código Terraform** nos três PCs, diferenciado só pelo `.tfvars` de cada host.

Uma distinção importante que aprendi: **`terraform plan` é seguro, `terraform apply` é destrutivo**. O `plan` mostra o que *seria* feito sem fazer nada. É o comando que vale mostrar no doc técnico como prova de que o IaC está correto — não preciso aplicar de verdade para demonstrar.

Outra armadilha que o plano do projeto documenta: **Terraform e Docker Compose não devem gerenciar o mesmo daemon ao mesmo tempo**. Os dois lêem e escrevem no Docker como fonte de verdade, e concorrência entre eles cria estado inconsistente. Em desenvolvimento local (Modo 1), usa-se o Compose; em produção distribuída (Modo 2), usa-se o Terraform. Os dois caminhos existem, mas não ao mesmo tempo no mesmo host.

### 2.4 Ansible: bootstrap vs deploy, e a divisão de responsabilidades

A separação entre os dois playbooks foi o conceito central do Ansible que aprendi hoje.

**`playbook-bootstrap.yml`** prepara o **host** — instala Docker, Tailscale e (só no PC1) o NVIDIA Container Toolkit. Essa é uma operação de "primeiro dia", que você raramente repete. Corre como `become: true` (root) porque instalar pacotes de sistema requer privilégio.

**`playbook-deploy.yml`** implanta a **aplicação** — copia o repositório, gera o `.env.local` e executa o Terraform. Corre como `become: false` (utilizador `rag`) porque o Terraform e o Docker não precisam de root.

A separação faz sentido operacionalmente: se precisar reimplantar uma nova versão, corro só o deploy — o bootstrap não precisa rodar de novo. Misturar os dois num só playbook tornaria cada reimplantação desnecessariamente lenta.

As **roles** são o mecanismo de reutilização do Ansible. Em vez de copiar os tasks de instalação do Docker para cada playbook, crio a role `docker` uma vez e referencio onde precisar. A role `nvidia` existe mas só é chamada no play que aponta para `hosts: pc1` — os outros hosts nunca a executam.

O template `env.j2` foi o detalhe mais elegante que entendi: em vez de copiar um `.env.local` fixo para cada host, o Ansible **renderiza** o template com os valores do inventário em tempo de deploy. O resultado é que `pc1.ansible_host` (o IP Tailscale real do PC1) entra automaticamente nas URLs de todos os workers — sem edição manual em cada máquina.

### 2.5 A fronteira entre Terraform e Ansible

Uma dúvida que tive durante a implementação: se o Ansible já consegue rodar comandos em hosts remotos, por que precisar do Terraform também?

A resposta está nas responsabilidades diferentes:

- **Ansible** é bom em **configurar hosts**: instalar pacotes, gerir utilizadores, copiar ficheiros, executar comandos. É orientado a tasks.
- **Terraform** é bom em **descrever e gerir recursos**: containers, redes, volumes, imagens. É orientado a estado declarativo.

Neste projeto, o Ansible **prepara o terreno** (Docker instalado, utilizador `rag` no grupo docker, Tailscale ativo) e depois **dispara o Terraform** em cada host. O Terraform é quem de facto cria os containers. Os dois juntos constroem a cadeia `host pronto → containers declarados → aplicação rodando`.

---

## 3. Aprendizados de processo e metodologia

### 3.1 Entrar num projeto a meio é diferente de começar do zero

Esta foi a primeira sessão em que trabalhei neste repositório, com o Bloco B1 já concluído pelo autor. A experiência de onboarding foi diferente do que eu esperava: o projeto tem documentação densa (`CLAUDE.md`, `TODO.md`, spec, planos de bloco), e ler esses documentos antes de tocar no código poupou tempo.

A parte mais útil foi o `TODO.md`: ele mostra não só o que está feito, mas também **quem fez** (trilha), **quando** (bloco) e **qual foi o marco de validação** (`make smoke`). Sem esse mapa, eu ficaria a tentar perceber a arquitetura só pelo código — possível, mas muito mais lento.

### 3.2 Trilhas e blocos — organização do trabalho em equipa

Um ponto que me confundiu no início foi a diferença entre "Trilha A/B/C" e "Bloco B1/B2/B3". São duas dimensões ortogonais:

- **Blocos** são o **quando**: fases cronológicas do projeto (B1 = setup, B2 = pipeline completo, B3 = tolerância a falhas + IaC, etc.).
- **Trilhas** são o **quem**: cada membro da equipa tem uma trilha. Trilha A = autor (PC1, GPU), Trilha B = colega 1 (PC2), Trilha C = eu (PC3).

Cada bloco distribui tarefas pelas trilhas com a notação `[A]`, `[B]`, `[C]` no `TODO.md`. Perceber isso cedo foi essencial para saber exatamente o que me competia fazer, sem entrar em colisão com o trabalho dos colegas.

### 3.3 IaC como documentação executável da topologia

Antes deste projeto, eu via IaC como "automação para não ter de clicar na consola". Depois de escrever o Terraform e o Ansible, percebi que a utilidade maior é outra: **o código descreve a topologia do sistema de forma executável e versionada**.

Quando alguém lê o `modules/worker/main.tf`, percebe imediatamente que os PC2/PC3 precisam de três containers (ingest-doc, ingest-chunk, query-worker), que expõem `/metrics` nas portas 9100/9101/9102, e que as suas URLs apontam para o PC1. Essa informação estava implícita no `docker-compose.yml` — o Terraform tornou-a explícita e testável com `terraform plan`.

A mesma lógica vale para o Ansible: o `inventory.yml` é a fonte de verdade da topologia de hosts. Se os IPs Tailscale mudarem, atualizo o inventário num lugar — todos os playbooks e templates ficam correctos automaticamente.

### 3.4 Cortes pré-definidos como decisão de design

O spec do projeto define uma lista de cortes em ordem prioritária caso o cronograma aperte. O Terraform está **no último lugar** dessa lista — significa que é o primeiro a cair se o tempo não chegar. Entender isso antes de começar a escrever o Terraform mudou a minha abordagem: fiz o suficiente para o entregável académico (estrutura correcta, `terraform plan` funciona), sem over-engineering.

Aprendi que definir o que **não** se vai fazer, e em que ordem cortar, é parte do design — não é desistência. É a diferença entre entregar algo incompleto de forma imprevisível e entregar algo deliberadamente reduzido com os trade-offs documentados.

---

## 4. O que ainda falta fazer (B3 → B5, Trilha C)

- **Preencher os IPs Tailscale reais** no `inventory.yml` e nos `pc2.tfvars` / `pc3.tfvars` — prerequisito para qualquer execução real.
- **Validar o Terraform** com `terraform init && terraform plan -var-file=envs/pc1.tfvars` no PC1.
- **Rodar o Ansible bootstrap** nos 3 PCs (requer utilizador `rag` com SSH configurado).
- **Experimento 1** — speedup da indexação variando N workers de chunk (`data/exp1/exp1.png`).
- **Experimento 2** — throughput de queries vs concorrência (`data/exp2/exp2.png`).
- **Experimento 4** — chaos test automatizado (`data/exp4/exp4.png`).
- **§7 do doc técnico** — resultados experimentais com gráficos e análise.
- **§8 do doc técnico** — discussão e limitações.
- **Lint final** — `uv run ruff check . && uv run mypy .` zerado.
- **Relatório individual** — esta secção, revista e expandida.

---

## 5. Conclusão

Entrei no projeto num momento crítico — dois dias antes da entrega, com a infraestrutura distribuída por fazer. Em vez de procurar atalhos, a sessão de onboarding forçou-me a entender o sistema antes de escrever uma linha. Isso custou tempo no início mas poupou muito mais tempo depois: quando comecei o Terraform, já sabia exactamente o que cada container precisava, porque tinha percorrido o `docker-compose.yml` e o código dos workers.

O que ficou como aprendizado mais duradouro não é a sintaxe do Terraform nem os módulos do Ansible — é a ideia de que **IaC é documentação da topologia, não só automação**. O código que escrevi hoje é a resposta executável à pergunta "como é que este sistema distribuído está organizado nos três PCs?". Qualquer colega que clonar o repositório e ler o `modules/server/main.tf` sabe o que corre no PC1 — sem precisar perguntar.

Os próximos dois dias vão ser a parte mais densa: rodar os experimentos, interpretar os resultados e escrever as secções do documento técnico. É onde a infraestrutura que configurei hoje serve de palco para o que o sistema realmente faz.
