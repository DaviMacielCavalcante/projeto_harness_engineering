terraform {
  required_version = ">= 1.9.0"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {
  host = "unix:///var/run/docker.sock"
}

resource "docker_network" "rag_net" {
  name   = "rag-network"
  driver = "bridge"
}

module "server" {
  count  = var.host_role == "server" ? 1 : 0
  source = "./modules/server"

  network_name = docker_network.rag_net.name
  image_tag    = var.image_tag
  enable_vllm  = var.enable_vllm
  vllm_model   = var.vllm_model
}

# Observabilidade vive junto do server (PC1). Prometheus/Grafana/Loki são
# centrais; Promtail roda em todo host (server + worker) lendo o
# /var/run/docker.sock local — quando os workers tiverem seu próprio módulo
# Promtail no host deles, este aqui só cobre o PC1.
module "observability" {
  count  = var.host_role == "server" ? 1 : 0
  source = "./modules/observability"

  network_name = docker_network.rag_net.name
}

module "worker" {
  count  = var.host_role == "worker" ? 1 : 0
  source = "./modules/worker"

  network_name       = docker_network.rag_net.name
  rabbit_url         = var.rabbit_url
  ollama_url         = var.ollama_url
  qdrant_url         = var.qdrant_url
  redis_url          = var.redis_url
  rerank_url         = var.rerank_url
  image_tag          = var.image_tag
  chunk_worker_count = var.chunk_worker_count
  inference_backend  = var.inference_backend
  vllm_url           = var.vllm_url
  vllm_model         = var.vllm_model
}
