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
}

module "worker" {
  count  = var.host_role == "worker" ? 1 : 0
  source = "./modules/worker"

  network_name = docker_network.rag_net.name
  rabbit_url   = var.rabbit_url
  ollama_url   = var.ollama_url
  qdrant_url   = var.qdrant_url
  redis_url    = var.redis_url
  rerank_url   = var.rerank_url
  image_tag    = var.image_tag
}
