# Como executar o Continua

Guia único e direto pra rodar o projeto do zero, do jeito mais rápido possível. Para o detalhamento de arquitetura e decisões, ver [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) e [`docs/DEVLOG.md`](docs/DEVLOG.md).

## Requisitos

- Docker e Docker Compose
- Python 3.11 ou mais recente
- Node.js 20 ou mais recente (só necessário para rodar o frontend em modo desenvolvimento; o `docker compose up` do frontend não precisa de Node instalado na máquina)
- Acesso à internet até `dadosabertos.aneel.gov.br` (só para `make download`; pode ser pulado — ver "Atalho" abaixo)
- Opcional, só para o chat: uma chave gratuita do Google Gemini em https://aistudio.google.com/apikey

## 1. Clonar e configurar

```bash
git clone https://github.com/vitorvmpontes/desafio-zeki.git
cd desafio-zeki
cp .env.example .env
```

Os valores padrão do `.env.example` já funcionam com o `docker-compose.yml` deste repositório — não é necessário editar nada nesta etapa.

## 2. Banco de dados

```bash
docker compose up -d db
```

## 3. Dados e modelo

Duas opções — escolha uma.

### Opção A — atalho recomendado (sem baixar da ANEEL)

Baixe os artefatos já processados e validados na [Release mensal mais recente](../../releases) deste repositório (tag `dados-AAAA-MM`): `municipio_mes.parquet` e `modelo_final.joblib`. Coloque-os em:

```
data/processed/municipio_mes.parquet
ml/artifacts/modelo_final.joblib
```

Depois siga direto para a etapa 4 (carregar o banco).

### Opção B — pipeline completo, do dado bruto da ANEEL

```bash
pip install -r etl/requirements.txt -r ml/requirements.txt -r requirements-dev.txt

# o Makefile calcula os anos sozinho (2024 até o ano corrente); sem make,
# troque $(ANOS) por uma lista explícita, ex.: --anos 2024,2025,2026
make download    # baixa os Parquet da ANEEL -- precisa de internet
make ingest       # limpeza + agregação -- gera data/processed/municipio_mes.parquet
make train        # treina o modelo final -- gera ml/artifacts/modelo_final.joblib
make exportar-artefatos   # importância de features + mapa de clusters (KML)
```

## 4. Carregar o banco e subir a API

```bash
make load-db              # carrega data/processed/municipio_mes.parquet no Postgres
docker compose up -d api  # builda e sobe a API
```

A API sobe em http://localhost:8000 — documentação interativa em http://localhost:8000/docs.

## 5. Frontend

```bash
docker compose up -d --build web
```

O painel sobe em http://localhost:3000.

Alternativa, para rodar em modo desenvolvimento sem rebuildar a imagem a cada mudança (requer Node.js e a API já de pé):

```bash
cd web
npm install
cp .env.example .env
npm run dev
```

## 6. Chatbot (opcional)

Sem esta etapa, o resto do projeto funciona normalmente — o endpoint `POST /chat` só responde 503 ("Chat não configurado").

```bash
# cria o role Postgres somente-leitura usado pelo chat (uma vez só)
docker compose exec -T db psql -U continua -d continua < db/readonly_role.sql
```

Depois, no `.env`, preencha:

```
DATABASE_URL_READONLY=postgresql://continua_readonly:continua_readonly@localhost:5432/continua
GEMINI_API_KEY=<sua chave, gratuita em https://aistudio.google.com/apikey>
```

E reinicie a API:

```bash
docker compose up -d --build api
```

## Testes

```bash
python -m pytest
```

(sempre com `python -m pytest`, nunca `pytest` sem prefixo — ver nota no `Makefile`)

Os testes de API (`tests/test_api.py`) usam dados sintéticos e não dependem de rede; alguns pulam automaticamente (`SKIPPED`, não erro) se o modelo treinado ou o Postgres somente-leitura ainda não estiverem disponíveis no seu ambiente.

## Checagem rápida

Depois dos passos acima, tudo funcionando:

- http://localhost:8000/docs — API respondendo
- http://localhost:8000/health — status geral
- http://localhost:3000 — painel carregando o ranking

## Problemas comuns

- **API não sobe / erro ao carregar o modelo**: confirme que `ml/artifacts/modelo_final.joblib` existe (etapa 3) antes de subir a API — ela só lê, nunca treina.
- **`/chat` responde 503**: `GEMINI_API_KEY` ou `DATABASE_URL_READONLY` não configurados — funcionamento esperado sem a etapa 6, o resto do produto não é afetado.
- **Frontend não encontra a API**: se você não estiver usando `localhost:8000`, ajuste `VITE_API_URL` (em `web/.env`, no modo desenvolvimento, ou como argumento de build no `docker-compose.yml`).
