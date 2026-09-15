# ml/

Exploração de dados e treino do modelo de previsão de risco de interrupção por município/mês.

**Status:** planejado para os dias 3 e 4 — ver [`docs/DEVLOG.md`](../docs/DEVLOG.md).

## O que vai entrar aqui

- `notebooks/01-eda.ipynb` — análise exploratória: sazonalidade, causas, distribuição geográfica.
- `notebooks/02-features.ipynb` — engenharia de features (defasagens, médias móveis, mix de causas).
- `notebooks/03-modelagem.ipynb` — baseline ingênuo, GLM Poisson/binomial negativa, gradient boosting, validação temporal, interpretabilidade (SHAP).
- `train.py` — versão em script do pipeline de treino final, gerando o artefato consumido pela API.

## Princípios de modelagem (ver `docs/REQUISITOS.md` e `docs/ARQUITETURA.md`)

- Validação sempre por corte temporal — nunca embaralhar meses entre treino e teste.
- Todo modelo é comparado contra um baseline ingênuo (persistência sazonal) antes de ser considerado válido.
- Clima real nunca entra como feature de previsão (vazamento de informação); só normais climatológicas históricas, se houver tempo.
