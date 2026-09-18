# api/

Backend em FastAPI: expõe os indicadores históricos, o ranking de risco previsto (gradient boosting, `ml/artifacts/modelo_final.joblib`) e a explicação por trás de cada previsão, lendo do Postgres carregado pelo ETL.

**Status:** Dia 5 concluído — endpoints implementados, testados (`tests/test_api.py`) e validados contra dado real. Ver [`docs/DEVLOG.md`](../docs/DEVLOG.md).

## Endpoints

- `GET /municipios?busca=&limite=200` — lista de municípios cobertos (código IBGE, nome, UF, região, consumidores ativos estimados). `busca` filtra por nome (contém, case-insensitive).
- `GET /municipios/{codigo_ibge}/historico` — série histórica mensal (`fec_aprox`, `n_eventos_validos`, `consumidores_ativos_max`) do município.
- `GET /municipios/{codigo_ibge}/previsao` — previsão de `fec_aprox` do mês seguinte pelo modelo (gradient boosting) **e** pelo baseline oficial do Dia 3 (persistência t-1 + t-12, mantido como referência — ver `docs/REQUISITOS.md`), os valores de entrada (features) usados nessa previsão específica, as causas dominantes recentes do município e a importância por permutação **global** do modelo (`ml/artifacts/importancia_features.json`).
- `GET /ranking?limite=50` — **ranking previsto**: todos os municípios ordenados pela previsão do modelo para o mês seguinte ao último dado disponível (2026-01, no dado atual).
- `GET /ranking?ano=&mes=&limite=50` — **ranking histórico**: municípios ordenados pelo `fec_aprox` real observado naquele ano/mês (os dois parâmetros são obrigatórios juntos — só um deles retorna 400).
- `GET /priorizacao?limite=20` — visão de apoio à decisão para o gestor de manutenção da distribuidora (substitui o antigo `/analises`, ver `docs/DEVLOG.md`, pivot "Priorização"): ranking dos `limite` municípios com maior **impacto esperado** (`previsao_modelo x consumidores_ativos_max`, não só a taxa isolada do `/ranking`), com uma ação recomendada por município a partir do mix de causas recentes (ou uma mensagem honesta quando a causa é majoritariamente genérica); os municípios com maior alta e maior queda de risco nos últimos 3 meses vs. os 3 anteriores; um calendário sazonal apontando os meses historicamente mais críticos para antecipar a preparação; e um bloco de **desempenho geográfico e qualidade regional** -- mapeamento de hotspots por município (`fec_aprox`/`dec_aprox_horas` médios, normalizados por consumidor, últimos 12 meses) e tempo médio de reparo (MTTR, horas por evento) por região.
- `GET /mapa` — mapa real de clusters de qualidade de serviço por município (pedido do usuário: "criar um mapa mesmo, usando um arquivo KML gerado a partir de alguma clusterização nos dados"): clusteriza (KMeans, `ml/mapa.py`) sobre as mesmas métricas normalizadas de `desempenho_geografico.hotspots`, retorna cada município com coordenada (latitude/longitude da sede) e rótulo de severidade (`critico`/`alto`/`moderado`/`baixo`, atribuído pelo centroide real do cluster, não pelo id arbitrário do KMeans), mais um resumo por cluster -- pronto para o frontend desenhar os marcadores direto, sem parsear KML.
- `GET /mapa/kml` — o mesmo mapa, servido como um arquivo KML de verdade (`application/vnd.google-earth.kml+xml`, com Placemarks agrupados em pastas por severidade) -- para abrir num visualizador GIS externo (Google Earth/Maps, QGIS) ou embutir num mapa. Também existe como artefato committed em `ml/artifacts/mapa_clusters.kml` (`ml/scripts/exportar_mapa_kml.py`). Tendência, calendário e desempenho geográfico são pré-computados uma vez na inicialização (`ml/priorizacao.py`); o ranking por impacto e a ação recomendada são calculados a cada requisição, limitados ao `limite` pedido.

Documentação interativa (Swagger) em `/docs` assim que a API subir; `/health` para checagem simples de vida.

## Decisões de design

- **O painel inteiro é lido do Postgres UMA VEZ, na inicialização**, e as consultas são resolvidas em memória com pandas (`api/database.py`). O dataset tem ~132 mil linhas (~60 MB) — pequeno demais para justificar uma query SQL por requisição; o Postgres continua sendo a fonte de verdade e o jeito de outros consumidores (ex.: a automação mensal, `.github/workflows/atualizacao-mensal.yml`) lerem os dados sem depender da API. Consequência aceita: atualizar o dado exige reiniciar a API (sem endpoint de reload por ora — fora do escopo do desafio) -- é exatamente o que a automação mensal faz (`docker compose up -d --build api` contra o Postgres recém-recarregado e o modelo recém-retreinado, com um smoke test antes de publicar), ver `docs/ARQUITETURA.md`.
- **`GET /ranking` sem parâmetros é sempre a previsão do próximo mês**, calculada uma vez na inicialização (última linha de histórico de cada município, alimentada no gradient boosting) — não uma query "ano/mês futuro" arbitrária, porque o modelo só prevê 1 passo à frente.
- **O baseline do Dia 3 é recalculado (não hardcoded) a cada inicialização**, via `ml/baseline.py` — generaliza a mesma regra (`persistência t-1` + `persistência t-12`, com fallback para o que estiver disponível) para o mês-alvo real de cada município, não só para os 12 meses de 2025 usados na validação original.
- **`importancia_features_modelo` é sempre a mesma para todos os municípios** (importância GLOBAL, calculada uma vez offline por `ml/scripts/exportar_importancia.py`, contra o modelo validado por corte temporal do Dia 4) — a API deixa isso explícito na resposta (`nota_metodologica`) para não sugerir que é uma explicação SHAP por instância, que o Dia 4 documentou como instável.
- **`/priorizacao` prioriza por impacto absoluto, não por taxa isolada** — `impacto_esperado = previsao_modelo x consumidores_ativos_max` (`ml/priorizacao.py`). Um município com risco por consumidor menor mas muitos mais consumidores pode gerar mais interrupções-consumidor no total do que um município pequeno com risco altíssimo; o `/ranking` (taxa isolada) continua existindo ao lado, para quem quer essa outra métrica.
- **A ação recomendada usa uma taxonomia de causa mais granular que `_causas_dominantes`** (ambiental / equipamento / terceiros / operacional / genérica-sem-detalhe, ver `ml/priorizacao.py`), com limiares de confiança (40% = alta, 15% = média) calibrados para não fabricar certeza que o dado não sustenta — ~91% dos municípios reais recebem a mensagem honesta de causa genérica em vez de uma ação específica, o que é o retrato real da limitação de dado já documentada no Dia 3, não um defeito deste cálculo.
- **Tendência (piorando/melhorando), calendário sazonal e desempenho geográfico são pré-computados uma vez em `montar_estado`** (não dependem do `limite` da requisição); o ranking por impacto e a ação recomendada, que dependem do `limite`, são recalculados a cada chamada, mas só para o subconjunto pedido — calcular o mix de causas dos ~5.500 municípios a cada requisição seria desperdício.
- **Hotspots usam `fec_aprox`/`dec_aprox_horas` médios (normalizados por consumidor), não volume bruto de eventos** — volume bruto só refletiria o tamanho do município (mesmo achado da disparidade regional do Dia 3) e seria redundante com o ranking por impacto; normalizado, o hotspot identifica má qualidade de serviço, não apenas escala. Granularidade é por município: o dataset público da ANEEL usado aqui não identifica subestação/alimentador. MTTR (`duracao_total_horas / n_eventos_validos`) é, propositalmente, a única métrica desta seção não normalizada por consumidor — é por definição uma medida por evento. A comparação regional de MTTR usa região/UF, não urbano/rural (classificação que não existe nos dados atuais).
- **O mapa (`/mapa`, `/mapa/kml`) clusteriza via KMeans padronizado por z-score** (`fec_aprox`/`dec_aprox_horas` médios têm escalas bem diferentes — sem padronizar, a duração dominaria a distância euclidiana sozinha). O rótulo de severidade é atribuído ordenando os **centroides** do cluster do pior para o melhor, nunca o id que o KMeans atribui — esse id é arbitrário (depende só da inicialização aleatória), então usar direto marcaria clusters diferentes como "crítico" em execuções diferentes. Coordenada é da SEDE do município (fonte: `kelvins/municipios-brasileiros`, mesma tabela de referência usada para região/UF em todo o projeto, estendida em `etl/build_reference.py` para carregar também latitude/longitude) — mesma limitação de granularidade dos hotspots (dado da ANEEL não identifica subestação/alimentador). O mapa é recalculado em memória a cada inicialização da API (igual a `desempenho_geografico`); também existe como artefato committed e inspecionável em `ml/artifacts/mapa_clusters.kml` (`ml/scripts/exportar_mapa_kml.py`), útil para abrir direto num visualizador GIS sem precisar subir a API.

## Como rodar

```bash
docker compose up -d db                 # sobe o Postgres
python -m etl.load_db                   # carrega data/processed/municipio_mes.parquet no Postgres (precisa ter rodado etl.pipeline + ml.train antes -- ver README.md da raiz)
docker compose up -d api                # builda e sobe a API -- http://localhost:8000/docs
```

Ou sem Docker, rodando a API diretamente (precisa de `DATABASE_URL` no ambiente/`.env` apontando para um Postgres acessível):

```bash
pip install -r api/requirements.txt
uvicorn api.main:app --reload
```

```bash
pytest tests/test_api.py -v   # testes de integracao dos endpoints -- NAO dependem de Postgres (usam um painel sintetico + o modelo real, ver docstring do arquivo)
```

## Nota sobre a validação neste ambiente

O sandbox usado para desenvolver a API não tem acesso ao Docker Hub (política de rede do ambiente — `docker compose build` falha ao baixar `python:3.11-slim`/`postgres:16-alpine`). A validação de ponta a ponta foi feita mesmo assim, sem Docker: contra uma instância Postgres real (não containerizada) carregada via `etl.load_db` com os 131.793 dados reais, e com a API rodando de verdade via `uvicorn` (não só o `TestClient` em processo) recebendo requisições HTTP de verdade (`curl`) nos 4 endpoints + casos de erro (404/400). `docker-compose.yml`/`Dockerfile` foram revisados manualmente nesse processo — e um bug real foi pego assim: o `DATABASE_URL` do `.env` aponta para `localhost` (certo para rodar `etl.load_db` do host), mas dentro da rede do `docker compose` o Postgres só é alcançável pelo nome do serviço, `db` — corrigido com um `environment:` que sobrescreve `DATABASE_URL` só para o container da API.

Rodar `docker compose up -d db api` numa máquina com acesso normal ao Docker Hub (a máquina do usuário) pegou um **segundo bug real** que só existe dentro da imagem: `api/requirements.txt` não tinha `statsmodels`, então o container morria com `ModuleNotFoundError` (`ml/modelos.py` importa `statsmodels` no topo do arquivo, para o GLM — mesmo a API só usando a parte de gradient boosting desse módulo). Corrigido adicionando a dependência e validado criando um virtualenv limpo só com `api/requirements.txt` e confirmando que `import api.main` funciona. Ver `docs/DEVLOG.md`, Dia 5 (atualização).
