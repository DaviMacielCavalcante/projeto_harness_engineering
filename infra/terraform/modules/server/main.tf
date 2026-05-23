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

variable "image_tag" {
  type = string
}

# ---------------------------------------------------------------------------
# RabbitMQ
# ---------------------------------------------------------------------------
resource "docker_image" "rabbitmq" {
  name = "rabbitmq:3-management"
}

resource "docker_volume" "rabbitmq_data" {
  name = "rabbitmq_data"
}

resource "docker_container" "rabbitmq" {
  name  = "rag-rabbitmq"
  image = docker_image.rabbitmq.image_id
  env = [
    "RABBITMQ_PLUGINS=rabbitmq_management rabbitmq_prometheus",
  ]
  networks_advanced {
    name = var.network_name
  }
  ports {
    internal = 5672
    external = 5672
  }
  ports {
    internal = 15672
    external = 15672
  }
  ports {
    internal = 15692
    external = 15692
  }
  volumes {
    volume_name    = docker_volume.rabbitmq_data.name
    container_path = "/var/lib/rabbitmq"
  }
  restart = "unless-stopped"
  healthcheck {
    test     = ["CMD", "rabbitmq-diagnostics", "ping"]
    interval = "10s"
    timeout  = "5s"
    retries  = 10
  }
}

# ---------------------------------------------------------------------------
# Qdrant
# ---------------------------------------------------------------------------
resource "docker_image" "qdrant" {
  name = "qdrant/qdrant:v1.12.4"
}

resource "docker_volume" "qdrant_storage" {
  name = "qdrant_storage"
}

resource "docker_container" "qdrant" {
  name  = "rag-qdrant"
  image = docker_image.qdrant.image_id
  networks_advanced {
    name = var.network_name
  }
  ports {
    internal = 6333
    external = 6333
  }
  volumes {
    volume_name    = docker_volume.qdrant_storage.name
    container_path = "/qdrant/storage"
  }
  restart = "unless-stopped"
}

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
resource "docker_image" "redis" {
  name = "redis:7-alpine"
}

resource "docker_volume" "redis_data" {
  name = "redis_data"
}

resource "docker_container" "redis" {
  name  = "rag-redis"
  image = docker_image.redis.image_id
  networks_advanced {
    name = var.network_name
  }
  ports {
    internal = 6379
    external = 6379
  }
  volumes {
    volume_name    = docker_volume.redis_data.name
    container_path = "/data"
  }
  restart = "unless-stopped"
}

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
resource "docker_image" "ollama" {
  name = "ollama/ollama:0.23.2"
}

resource "docker_volume" "ollama_models" {
  name = "ollama_models"
}

resource "docker_container" "ollama" {
  name  = "rag-ollama"
  image = docker_image.ollama.image_id
  networks_advanced {
    name = var.network_name
  }
  ports {
    internal = 11434
    external = 11434
  }
  volumes {
    volume_name    = docker_volume.ollama_models.name
    container_path = "/root/.ollama"
  }
  restart = "unless-stopped"
}

# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------
resource "docker_image" "gateway" {
  name         = "rag-gateway:${var.image_tag}"
  keep_locally = true
  build {
    context    = "${path.root}/../.."
    dockerfile = "infra/docker/gateway.Dockerfile"
  }
}

resource "docker_container" "gateway" {
  name  = "rag-gateway"
  image = docker_image.gateway.image_id
  env = [
    "SERVICE_NAME=gateway",
    "RABBITMQ_URL=amqp://guest:guest@rag-rabbitmq:5672/",
    "QDRANT_URL=http://rag-qdrant:6333",
    "REDIS_URL=redis://rag-redis:6379/0",
    "OLLAMA_URL=http://rag-ollama:11434",
    "RERANK_URL=http://rag-rerank:8081",
  ]
  networks_advanced {
    name = var.network_name
  }
  ports {
    internal = 8000
    external = 8000
  }
  restart    = "unless-stopped"
  depends_on = [docker_container.rabbitmq]
}

# ---------------------------------------------------------------------------
# Rerank service
# ---------------------------------------------------------------------------
resource "docker_image" "rerank" {
  name         = "rag-rerank:${var.image_tag}"
  keep_locally = true
  build {
    context    = "${path.root}/../.."
    dockerfile = "infra/docker/rerank.Dockerfile"
  }
}

resource "docker_container" "rerank" {
  name  = "rag-rerank"
  image = docker_image.rerank.image_id
  env = [
    "SERVICE_NAME=rerank-service",
  ]
  networks_advanced {
    name = var.network_name
  }
  ports {
    internal = 8081
    external = 8081
  }
  restart = "unless-stopped"
}
