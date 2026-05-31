variable "host_role" {
  type        = string
  description = "Papel do host: server ou worker"
  validation {
    condition     = contains(["server", "worker"], var.host_role)
    error_message = "host_role deve ser 'server' ou 'worker'."
  }
}

variable "tailscale_pc1" {
  type        = string
  description = "Tailscale IP do PC1 (servidor)"
  default     = ""
}

variable "rabbit_url" {
  type    = string
  default = ""
}

variable "ollama_url" {
  type    = string
  default = ""
}

variable "qdrant_url" {
  type    = string
  default = ""
}

variable "redis_url" {
  type    = string
  default = ""
}

variable "rerank_url" {
  type    = string
  default = ""
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "chunk_worker_count" {
  type        = number
  default     = 1
  description = "Réplicas do ingest-worker-chunk neste host worker (Exp 1 varia para medir speedup)."
}
