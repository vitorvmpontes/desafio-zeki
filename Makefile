.PHONY: help setup db-up db-down lint test reference download ingest load-db train exportar-artefatos atualizar-mensal api-up

# 2024 e o primeiro ano coberto pelo dataset; o teto e sempre o ano corrente,
# nunca hardcoded -- assim "make download"/"make ingest"/"make atualizar-mensal"
# continuam pegando o ano novo sozinhos, sem precisar editar o Makefile toda
# virada de ano (ver docs/DEVLOG.md, "Dia 7 -- automacao mensal"). Pode ser
# sobrescrito (ex.: `make ingest ANOS=2024,2025` para reprocessar so parte do
# historico).
ANO_CORRENTE := $(shell date +%Y)
ANOS ?= $(shell seq -s, 2024 $(ANO_CORRENTE))

help:
	@echo "Alvos disponiveis:"
	@echo "  make setup             - instala as dependencias (etl + ml + api + dev)"
	@echo "  make db-up             - sobe o Postgres (docker compose)"
	@echo "  make db-down           - derruba os containers"
	@echo "  make lint              - roda o linter (ruff)"
	@echo "  make test              - roda os testes (pytest)"
	@echo "  make reference         - reconstroi data/reference/municipios.csv (raramente necessario)"
	@echo "  make download          - baixa os Parquet da ANEEL (ANOS=$(ANOS) por padrao, 2024 ate o ano corrente)"
	@echo "  make ingest            - roda o pipeline completo (limpeza + agregacao) sobre os anos baixados"
	@echo "  make load-db           - carrega data/processed/municipio_mes.parquet no Postgres"
	@echo "  make train             - retreina o modelo final (ml/artifacts/modelo_final.joblib)"
	@echo "  make exportar-artefatos - regenera importancia de features e o mapa de clusters (KML)"
	@echo "  make atualizar-mensal  - sequencia completa (download+ingest+test+load-db+train+exportar-artefatos), ver docs/ARQUITETURA.md"
	@echo "  make api-up            - sobe db + api via docker compose (http://localhost:8000/docs)"

setup:
	pip install -r etl/requirements.txt -r ml/requirements.txt -r api/requirements.txt -r requirements-dev.txt

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

load-db:
	python -m etl.load_db

train:
	python -m ml.train

exportar-artefatos:
	python3 ml/scripts/exportar_importancia.py
	python3 ml/scripts/exportar_mapa_kml.py

# Sequencia completa da atualizacao recorrente (ver docs/ARQUITETURA.md,
# "Automacao"): mesmos alvos que um humano rodaria manualmente, na mesma
# ordem, reaproveitados pelo workflow do GitHub Actions
# (.github/workflows/atualizacao-mensal.yml) -- uma unica fonte de verdade
# para a sequencia, testavel localmente sem precisar disparar o workflow.
atualizar-mensal: download ingest test load-db train exportar-artefatos
	@echo "Atualizacao mensal concluida (anos processados: $(ANOS))."

api-up:
	docker compose up -d db api