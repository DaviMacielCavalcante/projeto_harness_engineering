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

# --- Exp 3 (bônus): Ollama vs vLLM ---------------------------------------

variable "enable_vllm" {
  type        = bool
  default     = false
  description = "PC1 (server): sobe o vLLM e move o Ollama p/ CPU. Só tem efeito no host server."
}

variable "inference_backend" {
  type        = string
  default     = "ollama"
  description = "query-worker (host worker): backend de geração — 'ollama' (linha-base) ou 'vllm'."
  validation {
    condition     = contains(["ollama", "vllm"], var.inference_backend)
    error_message = "inference_backend deve ser 'ollama' ou 'vllm'."
  }
}

variable "vllm_url" {
  type        = string
  default     = ""
  description = "URL do vLLM vista pelo worker (ex: http://<tailscale-pc1>:8002). Vazio = não usado."
}

variable "vllm_model" {
  type        = string
  default     = "Qwen/Qwen2.5-7B-Instruct-AWQ"
  description = "Id do modelo do vLLM; precisa casar nos dois lados (server e worker)."
}
