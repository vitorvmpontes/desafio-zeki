.PHONY: help db-up db-down lint test ingest

help:
	@echo "Alvos disponiveis:"
	@echo "  make db-up     - sobe o Postgres (docker compose)"
	@echo "  make db-down   - derruba os containers"
	@echo "  make lint      - roda o linter (ruff)"
	@echo "  make test      - roda os testes (pytest)"
	@echo "  make ingest    - roda o pipeline de ingestao (TODO: dia 2)"

db-up:
	docker compose up -d db

db-down:
	docker compose down

lint:
	ruff check .

test:
	pytest

ingest:
	@echo "TODO: implementado no dia 2 (etl/)"