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
  name  = "rag-ingest-worker-chunk"
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
  ports {
    internal = 9100
    external = 9101
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
