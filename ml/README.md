# ml/

Exploração de dados e treino do modelo de previsão de risco de interrupção por município/mês.

**Status:** Dia 4 concluído (features + GLM Poisson/binomial negativa + gradient boosting, todos validados contra os dados reais e comparados ao baseline do Dia 3). A API (Dia 5, `api/`) já consome `artifacts/modelo_final.joblib`, `baseline.py` e `artifacts/importancia_features.json` — ver [`docs/DEVLOG.md`](../docs/DEVLOG.md).

## Conteúdo

- `notebooks/01-eda.ipynb` — análise exploratória: sazonalidade, distribuição regional, mix de causas, ranking histórico de risco por município, correlação entre indicadores.
- `notebooks/02-baseline.ipynb` — define e avalia o baseline ingênuo (persistência do mês anterior + persistência sazonal, combinadas) — o piso de comparação para os modelos reais.
- `notebooks/03-features.ipynb` — constrói e valida o dataset supervisionado (uma linha por município x mês, alvo = `fec_aprox` do mês seguinte); documenta um bug real de off-by-one e de buracos no meio do histórico encontrado e corrigido nesta etapa (ver `docs/DEVLOG.md`, Dia 4).
- `notebooks/04-modelagem.ipynb` — treina GLM Poisson, GLM binomial negativa e gradient boosting, compara todos contra o baseline do Dia 3 com as mesmas métricas, analisa interpretabilidade (importância por permutação; SHAP também tentado, com uma limitação real documentada), e registra a escolha do modelo final.
- `features.py` — engenharia de features (defasagens, médias móveis, sazonalidade cíclica, mix de causas agregado, exposição) — reaproveitado pelos notebooks e por `train.py`. Ver o docstring do módulo para a justificativa de cada feature.
- `metricas.py` — as métricas de avaliação (MAE, RMSE, Spearman do ranking, precisão no top 10%) num único lugar, reaproveitadas pelo baseline, pelos modelos e por `train.py`.
- `modelos.py` — os três modelos (`ModeloContagemGLM` para Poisson/binomial negativa via `statsmodels`, `treinar_gbm`/`prever_gbm` para o gradient boosting via `sklearn`).
- `baseline.py` — o baseline oficial do Dia 3 (persistência t-1 + t-12) reescrito como função reutilizável (`prever_baseline`), capaz de prever para um mês-alvo qualquer, não só os 12 meses de 2025 usados na validação original — é o que a API (Dia 5) usa para mostrar o baseline ao lado da previsão do modelo.
- `interpretabilidade.py` — fatora a importância por permutação (usada em `04-modelagem.ipynb`) numa função reutilizável (`importancia_por_permutacao`), consumida por `scripts/exportar_importancia.py`.
- `train.py` — treina o modelo final (gradient boosting) com TODO o histórico disponível (diferente da validação por corte temporal dos notebooks) e salva `artifacts/modelo_final.joblib` + `artifacts/modelo_final_metadata.json`, consumidos pela API do Dia 5.
- `scripts/build_*.py` — geram os notebooks acima programaticamente (nbformat monta as células, nbclient executa de verdade com um kernel Jupyter) e os salvam já com saídas reais. Use para reproduzir os notebooks — ver "Como rodar" abaixo.
- `scripts/exportar_importancia.py` — gera `artifacts/importancia_features.json` (os números por trás do gráfico `importancia_features.png` do Dia 4), para a API explicar as previsões sem recalcular nada por requisição.
- `priorizacao.py` — priorização de ação para o gestor de manutenção (impacto real, ação recomendada, tendência, calendário sazonal, hotspots geográficos e MTTR regional) -- ver `api/README.md`, endpoint `/priorizacao`.
- `mapa.py` — mapa de clusters de qualidade de serviço por município: clusteriza (KMeans, sobre as mesmas métricas normalizadas de `priorizacao.py::hotspots_geograficos`) e gera um arquivo KML real (pedido do usuário: "criar um mapa mesmo, usando um arquivo KML gerado a partir de alguma clusterização") -- servido pela API em `GET /mapa` e `GET /mapa/kml`, ver `api/README.md`.
- `scripts/exportar_mapa_kml.py` — gera `artifacts/mapa_clusters.kml` (o arquivo KML committed, mesmo padrão de `exportar_importancia.py`) -- a API também recalcula o mesmo mapa em memória a cada inicialização, este script só deixa um artefato inspecionável fora da API.
- `artifacts/` — gráficos (`.png`), `baseline_metricas.json` (Dia 3), `modelagem_metricas.json` (Dia 4, comparação completa dos 3 modelos + baseline), `importancia_features.json` (Dia 5), `mapa_clusters.kml` (mapa de clusters geográficos) e `modelo_final.joblib`/`modelo_final_metadata.json` (modelo servido pela API).

## Principais conclusões (ver os notebooks para o detalhe)

**Do Dia 3:** sazonalidade nacional real e consistente entre 2024 e 2025; `fec_aprox` (normalizado por consumidor) é o alvo certo, não a contagem bruta de eventos; causa é majoritariamente genérica (~95% sem detalhe); o risco por município é persistente mês a mês, e o baseline de persistência combinada acerta ~80% do top 10% de risco em 2025.

**Do Dia 4:**
- Um bug real de off-by-one (e outro de buracos no meio do histórico de 543 dos 5.509 municípios) foi encontrado construindo o dataset de features, comparando contra o baseline do Dia 3 — corrigido e fixado em testes (`tests/test_ml_features.py`).
- Com só 24 meses de histórico, o treino cobre apenas ~10 meses-alvo (mar/2024 a dez/2024) — não há profundidade suficiente para uma defasagem sazonal individual por município (mesmo mês do ano anterior) aparecer no treino. Por isso a sazonalidade entra via `mes_sin`/`mes_cos`, não via lag de 12 meses.
- Os três modelos treinados (GLM Poisson, GLM binomial negativa, gradient boosting) batem claramente a persistência simples, mas **nenhum supera o baseline combinado do Dia 3** na precisão do top 10% — o gradient boosting chega perto (Spearman 0.906 vs. 0.907 do baseline). A explicação é concreta: o baseline usa a persistência sazonal *individual* de cada município, um sinal que exige mais de 2 anos de histórico para ser aprendido de forma confiável por um modelo treinado com corte temporal honesto.
- `lag_1` (valor do próprio mês mais recente) e a média histórica expandida dominam a importância por permutação; causa e número de distribuidoras contribuem muito pouco — consistente com o Dia 3.
- Modelo escolhido para a API (Dia 5): **gradient boosting**, com o baseline do Dia 3 mantido como referência exposta ao lado da previsão.

**Do Dia 5:** `ml/baseline.py` e `ml/interpretabilidade.py` fatoraram a lógica que antes só existia inline nos notebooks 02/04, para a API (`api/`) reusar sem duplicar código nem recalcular por requisição. A API expõe tudo isso via `GET /municipios/{codigo}/previsao` e `GET /ranking` — ver `api/README.md`.

## Como rodar

```bash
pip install -r ml/requirements.txt
python3 -m ipykernel install --user --name python3   # uma vez só, se ainda não tiver um kernel "python3"

# reconstroi os notebooks a partir do zero, executando de verdade contra
# data/processed/municipio_mes.parquet (rodar etl/pipeline.py antes, ver
# README.md da raiz do repositorio)
python3 ml/scripts/build_01_eda_notebook.py
python3 ml/scripts/build_02_baseline_notebook.py
python3 ml/scripts/build_03_features_notebook.py
python3 ml/scripts/build_04_modelagem_notebook.py

# treina e salva o modelo final consumido pela API
python -m ml.train

# gera artifacts/importancia_features.json (interpretabilidade consumida pela API)
python3 ml/scripts/exportar_importancia.py

# gera artifacts/mapa_clusters.kml (mapa de clusters geograficos consumido pela API)
python3 ml/scripts/exportar_mapa_kml.py
```

Os notebooks já vêm executados e commitados em `ml/notebooks/` — não é necessário rodar os scripts acima só para ler os resultados; eles servem para reproduzir ou atualizar os notebooks/modelo quando o dado processado mudar.

```bash
pytest tests/test_ml_features.py tests/test_ml_baseline.py -v   # testes de ml/ (nao dependem de rede nem do parquet real)
```

## Princípios de modelagem (ver `docs/REQUISITOS.md` e `docs/ARQUITETURA.md`)

- Validação sempre por corte temporal — nunca embaralhar meses entre treino e teste.
- Todo modelo é comparado contra o baseline ingênuo salvo em `artifacts/baseline_metricas.json` antes de ser considerado válido — a comparação completa do Dia 4 está em `artifacts/modelagem_metricas.json`.
- Clima real nunca entra como feature de previsão (vazamento de informação); só normais climatológicas históricas, se houver tempo.

## Pontos em aberto para o Dia 6+

- Estratégia de fallback para municípios sem histórico completo (~7% dos municípios reais).
- Reavaliar a inclusão de mais anos de dados da ANEEL: permitiria uma defasagem sazonal individual por município como feature de treino de verdade (não só como baseline à parte), o que provavelmente fecharia a diferença para o baseline combinado.
- Simplificar o conjunto de defasagens (`lag_1`/`lag_2`/`lag_3`/médias móveis são fortemente colineares) para tornar a interpretabilidade (SHAP) mais estável — ver `04-modelagem.ipynb`, seção 3.
- `ml/modelos.py` importa `statsmodels` no topo do arquivo (para `ModeloContagemGLM`), mas `prever_gbm`/`treinar_gbm` (o que a API de fato usa) não precisam disso — acoplamento que já causou um `ModuleNotFoundError` real na imagem Docker da API (ver `docs/DEVLOG.md`, Dia 5, "terceiro bug"). O fix mínimo (adicionar `statsmodels` a `api/requirements.txt`) foi feito; o fix estrutural (import tardio de `statsmodels` só dentro de `ModeloContagemGLM`, ou separar os dois modelos em módulos distintos) ainda não.
