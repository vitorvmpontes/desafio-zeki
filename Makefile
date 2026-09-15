.PHONY: help setup db-up db-down lint test reference download ingest

ANOS ?= 2024,2025

help:
	@echo "Alvos disponiveis:"
	@echo "  make setup       - instala as dependencias (etl + dev)"
	@echo "  make db-up       - sobe o Postgres (docker compose)"
	@echo "  make db-down     - derruba os containers"
	@echo "  make lint        - roda o linter (ruff)"
	@echo "  make test        - roda os testes (pytest)"
	@echo "  make reference   - reconstroi data/reference/municipios.csv (raramente necessario)"
	@echo "  make download    - baixa os Parquet da ANEEL (ANOS=2024,2025 por padrao)"
	@echo "  make ingest      - roda o pipeline completo (limpeza + agregacao) sobre os anos baixados"

setup:
	pip install -r etl/requirements.txt -r requirements-dev.txt

db-up:
	docker compose up -d db

db-down:
	docker compose down

lint:
	ruff check .

test:
	pytest

reference:
	python -m etl.build_reference

download:
	python -m etl.download --anos $(ANOS)

ingest:
	python -m etl.pipeline --anos $(ANOS)