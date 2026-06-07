.PHONY: dev down logs smoke pull-models test lint clean tf-init tf-plan tf-apply tf-destroy _tf-check \
        vllm-smoke exp3-up exp3-down exp3-backend-vllm exp3-backend-ollama exp3-run exp3-plot

TF_DIR := infra/terraform
HOST   ?= pc1

# Modo 1 — sobe tudo
dev:
	docker compose --profile all up -d --build
	@echo ""
	@echo "Serviços de pé:"
	@echo "  Gateway:        http://localhost:8000/docs"
	@echo "  RabbitMQ UI:    http://localhost:15672 (guest/guest)"
	@echo "  Qdrant:         http://localhost:6333/dashboard"
	@echo ""
	@echo "Próximo passo: make pull-models"

down:
	docker compose --profile all down

logs:
	docker compose --profile all logs -f --tail=200

# Puxa modelos no Ollama. Use MODEL=llama3.2:1b para CPU.
MODEL ?= qwen2.5:7b-instruct
pull-models:
	docker exec rag-ollama ollama pull nomic-embed-text
	docker exec rag-ollama ollama pull $(MODEL)

smoke:
	uv run python scripts/smoke_test.py

test:
	uv run pytest tests/unit -v

lint:
	uv run ruff check src tests

clean:
	docker compose --profile all down -v
	rm -rf .venv .pytest_cache .ruff_cache

# Terraform (Modo 2 / IaC). Use HOST=pc1|pc2|pc3 para escolher o env.
# Os módulos criam containers com os mesmos nomes do compose (rag-*), então
# `_tf-check` aborta se o compose estiver de pé pra evitar colisão.
tf-init:
	terraform -chdir=$(TF_DIR) init

tf-plan: _tf-check
	terraform -chdir=$(TF_DIR) plan -var-file=envs/$(HOST).tfvars

tf-apply: _tf-check
	terraform -chdir=$(TF_DIR) apply -var-file=envs/$(HOST).tfvars

tf-destroy:
	terraform -chdir=$(TF_DIR) destroy -var-file=envs/$(HOST).tfvars

_tf-check:
	@if [ ! -f "$(TF_DIR)/envs/$(HOST).tfvars" ]; then \
		echo "ERRO: $(TF_DIR)/envs/$(HOST).tfvars não existe."; \
		echo "Disponíveis:"; \
		ls $(TF_DIR)/envs/*.tfvars 2>/dev/null | sed 's|.*/|  |' || echo "  (nenhum — copie um .tfvars.example)"; \
		exit 1; \
	fi
	@if docker compose ps -q 2>/dev/null | grep -q .; then \
		echo "ERRO: stack do compose está de pé — containers rag-* colidiriam."; \
		echo "Rode 'make down' antes de aplicar o Terraform."; \
		exit 1; \
	fi

# Exp 3 (bônus): Ollama vs vLLM. Ver infra/docker/vllm-compose.override.yml e
# scripts/run_exp3_ollama_vs_vllm.py. Para trocar de modelo (ex: 3B), mude o
# default de vllm_model em infra/terraform/variables.tf (fonte única dos 2 lados).

# Smoke local do vLLM, sem stack: valida que o modelo sobe na GPU de 8GB.
# Roda em foreground; Ctrl+C para derrubar (--rm limpa o container).
vllm-smoke:
	docker run --gpus all --rm -p 8002:8000 \
		-e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
		-v vllm_models:/root/.cache/huggingface \
		vllm/vllm-openai:latest \
		--model Qwen/Qwen2.5-7B-Instruct-AWQ --quantization awq \
		--max-model-len 4096 --gpu-memory-utilization 0.85 \
		--kv-cache-dtype fp8 --enforce-eager --max-num-seqs 32

# PC1 (HOST=pc1): sobe o vLLM e move o Ollama p/ CPU (libera a GPU).
exp3-up: _tf-check
	terraform -chdir=$(TF_DIR) apply -var-file=envs/$(HOST).tfvars -var enable_vllm=true

# PC1 (HOST=pc1): derruba o vLLM e devolve a GPU ao Ollama (volta à baseline).
exp3-down: _tf-check
	terraform -chdir=$(TF_DIR) apply -var-file=envs/$(HOST).tfvars -var enable_vllm=false

# PC2/PC3 (HOST=pc2): aponta a geração do query-worker p/ o vLLM no PC1.
# Requer VLLM_URL=http://<tailscale-pc1>:8002.
exp3-backend-vllm: _tf-check
	@[ -n "$(VLLM_URL)" ] || { echo "ERRO: passe VLLM_URL=http://<tailscale-pc1>:8002"; exit 1; }
	terraform -chdir=$(TF_DIR) apply -var-file=envs/$(HOST).tfvars \
		-var inference_backend=vllm -var vllm_url=$(VLLM_URL)

# PC2/PC3 (HOST=pc2): volta a geração p/ o Ollama (baseline).
exp3-backend-ollama: _tf-check
	terraform -chdir=$(TF_DIR) apply -var-file=envs/$(HOST).tfvars -var inference_backend=ollama

# Roda as 2 rodadas do experimento. HOST_IP = Tailscale do PC1 (gateway).
exp3-run:
	@[ -n "$(HOST_IP)" ] || { echo "ERRO: passe HOST_IP=<tailscale-pc1>"; exit 1; }
	uv run python scripts/run_exp3_ollama_vs_vllm.py --host $(HOST_IP)

exp3-plot:
	uv run python scripts/plot_exp3.py
