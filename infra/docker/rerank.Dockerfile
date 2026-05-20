# Dockerfile do rerank-service (FastAPI + sentence-transformers).
# Stack: python:3.12-slim + uv. Sem multi-stage (mesmo padrão do gateway).
#
# Decisão de build que importa: pré-baixar o modelo dentro da imagem.
# Sem isso, o primeiro request em produção paga ~1 min de download
# (~600MB de pesos) — inaceitável pra um serviço que o query-worker
# chama em cada query. Embalando o modelo na imagem, o container sobe
# em ~3s e o primeiro /rerank responde em ms.

FROM python:3.12-slim

WORKDIR /app

# build-essential e git: algumas wheels de torch / sentence-transformers
# podem precisar compilar nativos durante o `uv sync`. Limpamos o cache
# do apt no fim pra não inflar a imagem.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git \
    && rm -rf /var/lib/apt/lists/*

RUN ["pip", "install", "--no-cache-dir", "uv==0.4.27"]

COPY pyproject.toml .

COPY uv.lock* .

RUN ["uv", "sync", "--frozen", "--no-dev", "--no-install-project"]

COPY src/ ./src/

# Pre-download do CrossEncoder no build, com nome do modelo parametrizado:
#
# - MODEL_NAME vem como ARG (default no Dockerfile, override com
#   `docker build --build-arg MODEL_NAME=outro/repo`) e é exportado como
#   ENV pra que tanto o `RUN` do build quanto o `lifespan` em runtime
#   leiam o mesmo valor. Single source of truth do nome — trocar de
#   modelo é mudar UM lugar (a ARG aqui).
# - HF_HOME é env OFICIAL do `huggingface_hub` (e respeitada por
#   transitividade pela `sentence-transformers`, `transformers`, etc.).
#   Setando aqui pra /models, todo download e leitura de pesos passa
#   por esse diretório, sem precisar passar `cache_folder` explícito no
#   CrossEncoder (esse argumento é ignorado quando o modelo não tem
#   `modules.json` — caso do bge-reranker-v2-m3).
# - O `python -c` abaixo lê MODEL_NAME e instancia o CrossEncoder uma
#   vez; o huggingface_hub consulta HF_HOME=/models e salva ali.
#   Quando o container subir, o `lifespan` instancia de novo e a mesma
#   env HF_HOME aponta pro cache populado — não baixa de novo.
# - Em dev local (sem HF_HOME setada), o stack cai no default
#   ~/.cache/huggingface/ e o `uv run uvicorn ...` continua funcionando.
# Layer caching: este layer só é invalidado se ARG MODEL_NAME ou o
# conteúdo de src/ mudar (não pelo conteúdo de pyproject.toml/uv.lock,
# que vêm em layers anteriores).
ARG MODEL_NAME="BAAI/bge-reranker-v2-m3"
ENV MODEL_NAME=${MODEL_NAME}
ENV HF_HOME=/models
RUN mkdir -p /models && \
    uv run python -c "import os; from sentence_transformers import CrossEncoder; CrossEncoder(os.environ['MODEL_NAME'])"

# Modo offline em runtime: a imagem JÁ embarca o modelo no layer acima
# (cache populado em /models/hub/models--<owner>--<name>/). Setando essas
# envs APÓS o RUN do pre-download, o stack em runtime usa só o cache
# local — zero validação ETag, zero HTTP request a huggingface.co. Vira
# startup sub-segundo. Postura: a imagem é a fonte de verdade; se o
# cache faltar, o `lifespan` estoura (LocalEntryNotFoundError) e o
# container entra em crashloop — sinal visível de bug de build, em vez
# de download silencioso em runtime mascarando o problema.
# Ordem importa: não setar essas envs antes do RUN do pre-download,
# senão o próprio download falha.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

ENV PYTHONPATH=/app

EXPOSE 8081

CMD ["uv", "run", "uvicorn", "src.rerank_service.main:app", "--host", "0.0.0.0", "--port", "8081"]
