terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

variable "network_name" {
  type = string
}

variable "rabbit_url" {
  type = string
}

variable "ollama_url" {
  type = string
}

variable "qdrant_url" {
  type = string
}

variable "redis_url" {
  type = string
}

variable "rerank_url" {
  type = string
}

variable "image_tag" {
  type = string
}

variable "chunk_worker_count" {
  type        = number
  default     = 1
  description = "Réplicas do ingest-worker-chunk. Exp 1 varia este valor para medir speedup de indexação."
}

resource "docker_image" "worker" {
  name         = "rag-worker:${var.image_tag}"
  keep_locally = true
  build {
    context    = "${path.root}/../.."
    dockerfile = "infra/docker/worker.Dockerfile"
  }
}

locals {
  worker_envs = [
    "RABBITMQ_URL=${var.rabbit_url}",
    "OLLAMA_URL=${var.ollama_url}",
    "QDRANT_URL=${var.qdrant_url}",
    "REDIS_URL=${var.redis_url}",
    "RERANK_URL=${var.rerank_url}",
    "PYTHONPATH=/app",
  ]
}

resource "docker_container" "ingest_worker_doc" {
  name  = "rag-ingest-worker-doc"
  image = docker_image.worker.image_id
  env = concat(local.worker_envs, [
    "WORKER_KIND=ingest",
    "INGEST_ROLE=documents",
    "SERVICE_NAME=ingest-worker-doc",
    "METRICS_PORT=9100",
  ])
  networks_advanced {
    name = var.network_name
  }
  ports {
    internal = 9100
    external = 9100
  }
  restart = "unless-stopped"
}

resource "docker_container" "ingest_worker_chunk" {
  count = var.chunk_worker_count
  # 1ª réplica mantém o nome canônico (alvo do Prometheus, default do chaos test);
  # réplicas extras (Exp 1, N>1) ganham sufixo -2, -3, ...
  name  = count.index == 0 ? "rag-ingest-worker-chunk" : "rag-ingest-worker-chunk-${count.index + 1}"
  image = docker_image.worker.image_id
  env = concat(local.worker_envs, [
    "WORKER_KIND=ingest",
    "INGEST_ROLE=chunks",
    "SERVICE_NAME=ingest-worker-chunk",
    "METRICS_PORT=9100",
  ])
  networks_advanced {
    name = var.network_name
  }
  # Só a 1ª réplica publica a porta de métricas no host (9101) — preserva o alvo
  # do Prometheus. Réplicas extras não expõem host port para evitar colisão;
  # consomem da fila e upsertam no Qdrant normalmente (a indexação não depende
  # de host port, só do acesso à rede).
  dynamic "ports" {
    for_each = count.index == 0 ? [1] : []
    content {
      internal = 9100
      external = 9101
    }
  }
  restart = "unless-stopped"
}

resource "docker_container" "query_worker" {
  name  = "rag-query-worker"
  image = docker_image.worker.image_id
  env = concat(local.worker_envs, [
    "WORKER_KIND=query",
    "SERVICE_NAME=query-worker",
    "METRICS_PORT=9100",
  ])
  networks_advanced {
    name = var.network_name
  }
  ports {
    internal = 9100
    external = 9102
  }
  restart = "unless-stopped"
}
