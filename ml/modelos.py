"""Modelos de previsão de risco -- GLM Poisson, GLM binomial negativa
(ambos via `statsmodels`, com exposição/offset nativo) e gradient boosting
(`sklearn.HistGradientBoostingRegressor`, via o truque padrão de modelar a
taxa com `sample_weight=exposição` -- `statsmodels` tem offset nativo,
`sklearn` não, então os dois mecanismos são diferentes mas equivalentes em
espírito: ambos ponderam o ajuste pela exposição em vez de tratar todo
município x mês como igualmente informativo).

Os dois GLMs modelam a CONTAGEM (`alvo_contagem` = n_eventos_validos do mês
seguinte) com `exposure` = consumidores ativos conhecidos no mês t (ver
`ml/features.py`) -- é a forma estatisticamente correta de modelar uma taxa
tipo FEC (ver docs/DEVLOG.md, Dia 4). A previsão final em taxa
(`fec_aprox` prevista) é sempre `contagem_prevista / exposicao`.

O gradient boosting modela a taxa (`alvo` = fec_aprox do mês seguinte)
diretamente, com `loss="poisson"` e `sample_weight=exposicao`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.ensemble import HistGradientBoostingRegressor

from ml.features import FEATURES_CATEGORICAS, FEATURES_NUMERICAS

# Para os GLMs usamos so `regiao` (5 niveis) como categorica, nao
# `uf_sigla` (27 niveis) -- toda UF pertence a exatamente uma regiao, entao
# incluir as duas juntas deixa a matriz de design deficiente em posto
# (colinearidade perfeita entre as dummies de UF e as de regiao), o que
# tornou o ajuste da binomial negativa instavel (estourou memoria na
# primeira tentativa -- ver docs/DEVLOG.md, Dia 4). O gradient boosting
# (arvore) nao tem esse problema e usa as duas (`FEATURES_CATEGORICAS`).
FEATURES_CATEGORICAS_GLM = ["regiao"]


def _design_matrix_glm(df: pd.DataFrame, imputacao: pd.Series | None = None):
    """Monta a matriz de design para os GLMs: features numéricas (com NaN
    imputado pela mediana do TREINO, nunca do teste) + dummies de `regiao`
    + constante. Retorna (X, imputacao) -- `imputacao` é reaproveitada ao
    montar a matriz do conjunto de teste."""
    numericas = df[FEATURES_NUMERICAS].copy()
    if imputacao is None:
        imputacao = numericas.median()
    numericas = numericas.fillna(imputacao)

    dummies = pd.get_dummies(df[FEATURES_CATEGORICAS_GLM].astype(str), drop_first=True)
    X = pd.concat([numericas, dummies], axis=1)
    X = sm.add_constant(X, has_constant="add")
    return X.astype(float), imputacao


class ModeloContagemGLM:
    """Encapsula um GLM (Poisson ou binomial negativa) de `statsmodels`
    treinado sobre a contagem de eventos válidos do mês seguinte, com
    exposição, e exposto com uma interface `fit`/`predict` (retorna TAXA
    prevista, não contagem) parecida com a dos modelos do sklearn."""

    def __init__(self, familia: str = "poisson", alpha_nb: float | None = None):
        if familia not in ("poisson", "binomial_negativa"):
            raise ValueError("familia deve ser 'poisson' ou 'binomial_negativa'")
        self.familia = familia
        self.alpha_nb = alpha_nb
        self._resultado = None
        self._imputacao = None
        self._colunas_treino = None

    def fit(self, df_treino: pd.DataFrame) -> ModeloContagemGLM:
        X, self._imputacao = _design_matrix_glm(df_treino)
        self._colunas_treino = X.columns
        y = df_treino["alvo_contagem"].to_numpy()
        exposicao = df_treino["exposicao"].to_numpy()

        if self.familia == "poisson":
            modelo = sm.GLM(y, X, family=sm.families.Poisson(), exposure=exposicao)
            self._resultado = modelo.fit()
        else:
            # Ajusta alpha (dispersao) por Poisson auxiliar se nao fornecido,
            # depois roda a binomial negativa (NB2) com esse alpha -- a
            # abordagem em duas etapas classica quando nao se quer usar o
            # NegativeBinomial de discrete_model (que reestima alpha via MLE
            # mas exige exog sem colinearidade perfeita das dummies).
            if self.alpha_nb is None:
                aux = sm.GLM(y, X, family=sm.families.Poisson(), exposure=exposicao).fit()
                mu = aux.mu
                resid = (y - mu) ** 2 - mu
                alpha_estimado = (resid / mu**2).mean()
                self.alpha_nb = max(alpha_estimado, 1e-4)
            modelo = sm.GLM(y, X, family=sm.families.NegativeBinomial(alpha=self.alpha_nb), exposure=exposicao)
            self._resultado = modelo.fit()
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        X, _ = _design_matrix_glm(df, imputacao=self._imputacao)
        X = X.reindex(columns=self._colunas_treino, fill_value=0.0)
        contagem_prevista = self._resultado.predict(X, exposure=df["exposicao"].to_numpy())
        return contagem_prevista / df["exposicao"].to_numpy()

    def resumo(self) -> str:
        return self._resultado.summary().as_text()


def treinar_gbm(df_treino: pd.DataFrame, **kwargs) -> HistGradientBoostingRegressor:
    """Treina o gradient boosting sobre a TAXA (fec_aprox do mes seguinte),
    ponderado pela exposicao. Regiao/UF entram como categoricas nativas do
    HistGradientBoostingRegressor (sem precisar de one-hot)."""
    X = df_treino[FEATURES_NUMERICAS + FEATURES_CATEGORICAS].copy()
    for col in FEATURES_CATEGORICAS:
        X[col] = X[col].astype("category")

    parametros = {
        "loss": "poisson",
        "max_iter": 300,
        "learning_rate": 0.05,
        "max_depth": 4,
        "min_samples_leaf": 50,
        "categorical_features": FEATURES_CATEGORICAS,
        "random_state": 42,
    }
    parametros.update(kwargs)
    modelo = HistGradientBoostingRegressor(**parametros)
    modelo.fit(X, df_treino["alvo"], sample_weight=df_treino["exposicao"])
    return modelo


def prever_gbm(modelo: HistGradientBoostingRegressor, df: pd.DataFrame) -> np.ndarray:
    X = df[FEATURES_NUMERICAS + FEATURES_CATEGORICAS].copy()
    for col in FEATURES_CATEGORICAS:
        X[col] = X[col].astype("category")
    return modelo.predict(X)
