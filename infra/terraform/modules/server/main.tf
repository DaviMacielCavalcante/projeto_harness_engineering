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

variable "enable_vllm" {
  type        = bool
  default     = false
  description = "Exp 3 (bônus): sobe o vLLM e move o Ollama para CPU (libera a GPU de 8GB)."
}

variable "vllm_model" {
  type        = string
  default     = "Qwen/Qwen2.5-7B-Instruct-AWQ"
  description = "Id do modelo servido pelo vLLM; precisa casar com VLLM_MODEL do query-worker."
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
    name    = var.network_name
    aliases = ["rabbitmq"]
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
    name    = var.network_name
    aliases = ["qdrant"]
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
    name    = var.network_name
    aliases = ["redis"]
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
    name    = var.network_name
    aliases = ["ollama"]
  }
  ports {
    internal = 11434
    external = 11434
  }
  volumes {
    volume_name    = docker_volume.ollama_models.name
    container_path = "/root/.ollama"
  }

  # Exp 3: quando o vLLM sobe (enable_vllm), o Ollama cede a GPU de 8GB inteira
  # ao vLLM e roda em CPU. Embeddings (nomic, pequeno) aguentam bem em CPU, e a
  # geração nessa fase vai para o vLLM — o Ollama só serve embed.
  gpus    = var.enable_vllm ? null : "all"
  runtime = var.enable_vllm ? null : "nvidia"

  restart = "unless-stopped"
}

# ---------------------------------------------------------------------------
# vLLM — gerador alternativo do Exp 3 (CONDICIONAL: só com enable_vllm=true).
# Flags de 8GB validados em 2026-06-07 na RTX 4060 Ti; ver
# infra/docker/vllm-compose.override.yml para o racional de cada um.
# ---------------------------------------------------------------------------
resource "docker_image" "vllm" {
  count = var.enable_vllm ? 1 : 0
  name  = "vllm/vllm-openai:latest"
}

resource "docker_volume" "vllm_models" {
  count = var.enable_vllm ? 1 : 0
  name  = "vllm_models"
}

resource "docker_container" "vllm" {
  count = var.enable_vllm ? 1 : 0
  name  = "rag-vllm"
  image = docker_image.vllm[0].image_id
  env = [
    "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True",
  ]
  command = [
    "--model=${var.vllm_model}",
    "--quantization=awq",
    "--max-model-len=4096",
    "--gpu-memory-utilization=0.85",
    "--kv-cache-dtype=fp8",
    "--enforce-eager",
    "--max-num-seqs=32",
  ]
  networks_advanced {
    name    = var.network_name
    aliases = ["vllm"]
  }
  ports {
    internal = 8000
    external = 8002
  }
  volumes {
    volume_name    = docker_volume.vllm_models[0].name
    container_path = "/root/.cache/huggingface"
  }
  gpus    = "all"
  runtime = "nvidia"
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
    name    = var.network_name
    aliases = ["gateway"]
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
    name    = var.network_name
    aliases = ["rerank-service"]
  }
  ports {
    internal = 8081
    external = 8081
  }
  restart = "unless-stopped"
}
