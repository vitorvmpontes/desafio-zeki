"""Importância por permutação do gradient boosting, fatorada para reuso.

O notebook `04-modelagem.ipynb` computa isso inline (seção 3) contra o
modelo validado por corte temporal (treinado até 2024, testado em 2025,
restrito aos municípios com histórico completo -- a mesma população do
baseline do Dia 3) -- é essa versão, com held-out de verdade, que faz
sentido interpretar, não o `modelo_final.joblib` servido pela API (esse é
treinado com TODO o histórico disponível, sem held-out, de propósito, para
ser o melhor modelo possível para prever o próximo mês real -- ver
`ml/train.py`).

Este módulo fatora essa mesma lógica (usa `sklearn.inspection.permutation_importance`
com os mesmos parâmetros do notebook: `n_repeats=5`, `random_state=42`,
`scoring="neg_mean_absolute_error"`) para ser reaproveitada por
`ml/scripts/exportar_importancia.py`, que gera
`ml/artifacts/importancia_features.json` -- os números por trás do gráfico
`importancia_features.png` do Dia 4. É esse JSON que a API lê na
inicialização para explicar "o que mais pesa" nas previsões, sem recalcular
nada por requisição (e sem reintroduzir a instabilidade do SHAP documentada
no Dia 4, ver `docs/DEVLOG.md`).
"""
from __future__ import annotations

import pandas as pd
from sklearn.inspection import permutation_importance

from ml.features import FEATURES_CATEGORICAS, FEATURES_NUMERICAS


def importancia_por_permutacao(
    modelo, df_teste: pd.DataFrame, n_repeticoes: int = 5, seed: int = 42
) -> pd.DataFrame:
    """Reproduz a análise de `04-modelagem.ipynb`: embaralha cada feature
    (uma de cada vez) e mede o quanto o MAE do modelo piora -- quanto maior
    a piora, mais o modelo depende daquela feature."""
    X = df_teste[FEATURES_NUMERICAS + FEATURES_CATEGORICAS].copy()
    for col in FEATURES_CATEGORICAS:
        X[col] = X[col].astype("category")

    r = permutation_importance(
        modelo,
        X,
        df_teste["alvo"],
        n_repeats=n_repeticoes,
        random_state=seed,
        scoring="neg_mean_absolute_error",
    )

    resultado = pd.DataFrame(
        {
            "feature": X.columns,
            "aumento_mae_medio": r.importances_mean,
            "aumento_mae_desvio": r.importances_std,
        }
    ).sort_values("aumento_mae_medio", ascending=False).reset_index(drop=True)

    soma = resultado["aumento_mae_medio"].clip(lower=0).sum()
    resultado["importancia_relativa"] = (
        resultado["aumento_mae_medio"].clip(lower=0) / soma if soma > 0 else 0.0
    )
    return resultado
