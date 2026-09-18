# Continua

Plataforma de análise e previsão de risco de interrupção de energia elétrica, construída sobre os dados públicos de interrupções da ANEEL — desenvolvida como desafio técnico do processo seletivo da Zeki.

> Transforma os despejos anuais e brutos da ANEEL em um ranking mensal de risco por município, com a previsão do mês seguinte, o histórico real e as causas que mais pesam — para priorizar fiscalização e manutenção preventiva antes do problema acontecer.

## O problema

A ANEEL disponibiliza dados públicos de interrupções de energia, mas em arquivos anuais brutos (Parquet de até ~260 MB por ano, colunas com siglas pouco autoexplicativas, sem duração calculada e sem identificar o município diretamente — só o conjunto de unidades consumidoras) e sem nenhuma API de consulta. Quem precisa entender e priorizar risco de interrupção — um analista de fiscalização da ANEEL, um gestor de manutenção de uma distribuidora — só enxerga indicadores históricos, medidos depois do problema já ter acontecido.

## A solução

O Continua ingere os dados da ANEEL mensalmente, calcula indicadores de continuidade por município, e usa um modelo de aprendizado de máquina para prever o risco de interrupção do mês seguinte — expondo tudo isso por uma API e um painel simples, com a explicação (causas dominantes) por trás de cada previsão.

A análise completa de problema, público, escopo e decisões está em [`docs/REQUISITOS.md`](docs/REQUISITOS.md), e a arquitetura técnica em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).

## Como rodar do zero

> Esta seção é mantida honesta durante o desenvolvimento: só documenta o que já funciona hoje. O objetivo final é `docker compose up` subir tudo (banco, API e frontend) com os dados de amostra já carregados.

Pré-requisitos: Docker e Docker Compose, Python 3.11+.

```bash
git clone https://github.com/vitorvmpontes/desafio-zeki.git
cd desafio-zeki
cp .env.example .env
docker compose up -d db

# pipeline de dados (make calcula os anos sozinho: 2024 ate o ano corrente --
# ver "Atualização recorrente" abaixo. Sem make, troque $(ANOS) por uma lista
# explicita, ex.: --anos 2024,2025,2026)
pip install -r etl/requirements.txt -r ml/requirements.txt -r requirements-dev.txt
make download    # = python -m etl.download --anos <2024..ano corrente> -- precisa de internet ate dadosabertos.aneel.gov.br
make ingest      # = python -m etl.pipeline --anos <2024..ano corrente> -- gera data/processed/municipio_mes.parquet
pytest           # roda a suite de testes (nao depende de rede)

# analise exploratoria + baseline + modelagem (notebooks ja executados e
# commitados em ml/notebooks/ -- so precisa rodar de novo se o dado mudar)
python3 -m ipykernel install --user --name python3
python ml/scripts/build_01_eda_notebook.py
python ml/scripts/build_02_baseline_notebook.py
python ml/scripts/build_03_features_notebook.py
python ml/scripts/build_04_modelagem_notebook.py

# treina e salva o modelo final (ml/artifacts/modelo_final.joblib) que a API vai consumir
make train                # = python -m ml.train
make exportar-artefatos   # = importancia de features + mapa de clusters (KML), ver ml/README.md

# API (Dia 5): carrega o banco e sobe o servico
make load-db              # carrega data/processed/municipio_mes.parquet no Postgres (ja de pe, ver "docker compose up -d db" acima)
docker compose up -d api  # builda e sobe a API -- http://localhost:8000/docs
pytest tests/test_api.py -v    # testes de integracao dos endpoints (nao dependem de Postgres, ver api/README.md)

# Frontend (Dia 6): sobe o painel consumindo a API acima
docker compose up -d --build web   # builda e sobe o frontend -- http://localhost:3000

# Chatbot text-to-SQL (Dia 8, opcional -- ver api/README.md): sem isso, o
# resto do projeto funciona normalmente e /chat responde 503.
psql -h localhost -U continua -d continua -f db/readonly_role.sql   # cria o role somente-leitura continua_readonly (uma vez)
# defina DATABASE_URL_READONLY e GEMINI_API_KEY no .env (ver .env.example --
# chave gratuita em https://aistudio.google.com/apikey), depois reinicie a API
```

> Nota sobre o download: além dos Parquet anuais, `etl.download` também baixa o de-para conjunto→município da ANEEL ("IndQual Município", `data/raw/indqual_municipio.csv`), necessário para resolver o município de cada interrupção. Ver `etl/README.md`.

> Para rodar só o frontend em modo de desenvolvimento (sem rebuildar a imagem a cada mudança): `cd web && npm install && cp .env.example .env && npm run dev` (com a API já de pé em `http://localhost:8000` — ajuste `VITE_API_URL` em `web/.env` se for outro endereço). Ver `web/README.md`.

## Atualização recorrente (dados mensais)

A ANEEL republica o Parquet do ano corrente com dados novos todo mês -- o Continua foi pensado desde o Dia 1 para reprocessar isso sem intervenção manual, não só para a carga inicial:

- **`make atualizar-mensal`** roda a sequência inteira de novo (`download` → `ingest` → `test` → `load-db` → `train` → `exportar-artefatos`), sempre com os anos calculados automaticamente (2024 até o ano corrente, sem precisar editar nada quando o ano vira). Todo passo é idempotente -- rodar de novo num mês sem publicação nova da ANEEL não muda nada.
- **`.github/workflows/atualizacao-mensal.yml`** roda essa mesma sequência (via `make atualizar-mensal`, a mesma fonte de verdade) no dia 5 de cada mês, ou a qualquer momento via disparo manual ("Run workflow" na aba Actions do GitHub). Sem servidor pago rodando continuamente para "reimplantar" durante a avaliação do desafio, republicar significa: sobe a API de verdade contra os artefatos novos e roda um smoke test antes de publicar; os artefatos grandes (dado processado + modelo treinado) viram assets de uma [GitHub Release](../../releases) mensal (tag `dados-AAAA-MM`); os artefatos pequenos e já versionados (`ml/artifacts/importancia_features.json`, `mapa_clusters.kml`, `modelo_final_metadata.json`) são commitados de volta em `main`. Detalhes e decisões em `docs/ARQUITETURA.md` e `docs/REQUISITOS.md` ("Dia 7").
- **Para pular o reprocessamento completo** (que baixa e processa os Parquet anuais inteiros da ANEEL): baixe os assets da Release mensal mais recente em vez de rodar `make download`/`make ingest` -- é o mesmo `municipio_mes.parquet`/`modelo_final.joblib` que o workflow acabou de gerar e validar.

## Estrutura do repositório

```
desafio-zeki/
├── .github/workflows/  CI (lint + testes) e a automação mensal (atualizacao-mensal.yml)
├── docs/            análise de requisitos, arquitetura e log de desenvolvimento
├── etl/             ingestão, limpeza e agregação dos dados da ANEEL
├── ml/              exploração de dados e treino do modelo de risco
├── api/             backend (FastAPI) — indicadores, ranking, previsão e o chatbot text-to-SQL (chat_sql.py)
├── db/              readonly_role.sql -- role Postgres somente-leitura usado pelo chatbot
├── web/             frontend (tema escuro) — ranking, detalhe do município, priorização, tendências, geografia e chat
├── tests/           testes automatizados (fixtures sintéticas, sem dependência de rede)
├── Makefile         atalhos para os passos do pipeline, inclusive a atualização mensal completa
└── data/            dados (raw/processed ignorados pelo git; reference e sample versionadas)
```

## Fonte de dados

[Interrupções de Energia Elétrica nas Redes de Distribuição](https://dadosabertos.aneel.gov.br/dataset/interrupcoes-de-energia-eletrica-nas-redes-de-distribuicao) — Portal de Dados Abertos da ANEEL.

## Uso de IA no desenvolvimento

Ferramentas de IA (Claude) foram usadas como apoio ao desenvolvimento — aceleração de boilerplate e documentação. As decisões de produto, modelagem de dados e arquitetura são registradas e justificadas em `docs/`.
