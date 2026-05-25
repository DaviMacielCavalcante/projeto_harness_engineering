.PHONY: dev down logs smoke pull-models test lint clean tf-init tf-plan tf-apply tf-destroy _tf-check

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
