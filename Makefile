.PHONY: dev down logs smoke pull-models test lint clean

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
