"""Engenharia de features para o modelo de previsão de risco município x mês.

Ideia central: cada linha de `data/processed/municipio_mes.parquet` vira uma
linha "(município, mês t)" com features calculadas usando SÓ o que já era
conhecido até o mês t (nunca o próprio mês t+1) -- e o alvo é `fec_aprox`
observado no mês t+1. Isso é o que permite treinar/validar por corte
temporal (nunca embaralhar meses, ver `docs/REQUISITOS.md`).

Decisões de feature engineering (ver `ml/notebooks/03-features.ipynb` para a
análise que embasa cada uma):

- Sazonalidade entra via `mes_sin`/`mes_cos` (codificação cíclica), não via
  uma defasagem de 12 meses por município -- com só 24 meses de histórico
  (2024+2025), uma defasagem sazonal individual (t-12) só existe a partir do
  13º mês de cada município, o que deixa quase nenhum dado de TREINO
  disponível antes do início da janela de teste (2025). A codificação de mês
  captura o efeito sazonal agregado (todos os municípios sobem/descem no
  mesmo mês) a partir de qualquer ponto do histórico, sem precisar de um ano
  inteiro de profundidade por município. Ver `docs/DEVLOG.md` (Dia 4).
- Persistência de curto prazo entra via `lag_1`/`lag_2`/`lag_3` e médias
  móveis -- captura o sinal autoregressivo que já mostrou ser forte no
  baseline do Dia 3.
- Causa entra de forma agregada e grosseira (proporção de causa genérica vs.
  ambiental), não como as ~46 colunas de causa originais -- a EDA do Dia 3
  mostrou que ~95% dos eventos só têm causa genérica, então causa detalhada
  por município x mês é majoritariamente ruído/esparsidade.
- `regiao`/`uf_sigla` entram como categóricas (estrutural, não muda mês a
  mês); `consumidores_ativos_max` entra como exposição (peso do modelo) e
  como log-feature de porte.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COL_ID = "codigo_ibge_resolvido"
COL_ANO = "ano"
COL_MES = "mes"
TARGET = "fec_aprox"
EXPOSURE = "consumidores_ativos_max"

FEATURES_NUMERICAS = [
    "lag_1",
    "lag_2",
    "lag_3",
    "media_movel_3",
    "media_movel_expandida",
    "mes_sin",
    "mes_cos",
    "log_consumidores",
    "log_n_eventos_lag_1",
    "prop_causa_generica_lag_1",
    "prop_causa_ambiental_lag_1",
    "n_distribuidoras_lag_1",
]
FEATURES_CATEGORICAS = ["regiao", "uf_sigla"]
TODAS_FEATURES = FEATURES_NUMERICAS + FEATURES_CATEGORICAS

COLUNAS_SAIDA = [
    COL_ID,
    "nome_municipio",
    COL_ANO,
    COL_MES,
    "periodo",
    "alvo",
    "alvo_contagem",
    "exposicao",
] + TODAS_FEATURES  # inclui "regiao"/"uf_sigla" (via FEATURES_CATEGORICAS) uma unica vez


def _periodo(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime({"year": df[COL_ANO], "month": df[COL_MES], "day": 1}).dt.to_period("M")


def construir_dataset(df_municipio_mes: pd.DataFrame) -> pd.DataFrame:
    """Constrói o dataset supervisionado a partir do município x mês agregado.

    Uma linha por (município, mês t) com features calculadas a partir do
    histórico até t (inclusive) e `alvo` = `fec_aprox` em t+1. Municípios sem
    correspondência na bridge (`nome_municipio` nulo) são excluídos -- não são
    município geográficos de verdade, e não têm região/UF para as features
    categóricas (mesma decisão do baseline, `ml/notebooks/02-baseline.ipynb`).

    Linhas sem `lag_1` (primeiro mês de histórico de cada município) ou sem
    `alvo` (último mês -- não existe "mês seguinte" observado ainda) são
    mantidas no dataframe retornado, mas devem ser descartadas por quem for
    treinar/avaliar um modelo (ver `filtrar_utilizaveis`) -- feature de mais
    longo prazo (lag_2, lag_3, médias móveis) pode ficar NaN mesmo em linhas
    utilizáveis; modelos baseados em árvore (`HistGradientBoostingRegressor`)
    lidam com isso nativamente, GLMs precisam de imputação (ver `ml/modelos.py`).
    """
    df = df_municipio_mes.dropna(subset=["nome_municipio"]).copy()
    df["periodo"] = _periodo(df)
    df = df.sort_values([COL_ID, "periodo"]).reset_index(drop=True)

    causa_cols = [c for c in df.columns if c.startswith("causa_")]
    causa_generica = [c for c in causa_cols if c in ("causa_interna", "causa_interno")]
    causa_ambiental = [c for c in causa_cols if "meio_ambiente" in c]

    n_validos_seguro = df["n_eventos_validos"].replace(0, np.nan)
    df["_prop_causa_generica"] = (df[causa_generica].sum(axis=1) / n_validos_seguro).fillna(0.0)
    df["_prop_causa_ambiental"] = (df[causa_ambiental].sum(axis=1) / n_validos_seguro).fillna(0.0)
    df["_linha_real"] = True

    # Reindexa cada municipio para o calendario COMPLETO do painel (do
    # primeiro ao ultimo mes observado em qualquer municipio), preenchendo
    # com NaN os meses sem dado. Sem isso, um municipio com um buraco no
    # MEIO do historico (543 dos 5509 municipios reais tem pelo menos um --
    # verificado contra o dado real, nao e caso de borda raro) faria o
    # `.shift()` por posicao "pular" o buraco silenciosamente e tratar dois
    # meses NAO consecutivos como se fossem vizinhos -- um bug pego so
    # depois de notar que ele nao aparecia na fixture sintetica original de
    # teste (sempre contigua). Ver docs/DEVLOG.md, Dia 4.
    calendario = pd.period_range(df["periodo"].min(), df["periodo"].max(), freq="M")
    indice_completo = pd.MultiIndex.from_product(
        [df[COL_ID].unique(), calendario], names=[COL_ID, "periodo"]
    )
    df = df.set_index([COL_ID, "periodo"]).reindex(indice_completo)
    df["_linha_real"] = df["_linha_real"].fillna(False)
    df = df.reset_index()
    df[COL_ANO] = df["periodo"].dt.year
    df[COL_MES] = df["periodo"].dt.month

    g = df.groupby(COL_ID, sort=False)

    # IMPORTANTE: o alvo e o mes t+1, entao o "mes mais recente conhecido"
    # na hora de prever e o proprio mes t (a linha atual) -- lag_1 e
    # shift(0) (o valor do proprio t), NAO shift(1). Uma tentativa anterior
    # usou shift(1)/shift(2)/shift(3) aqui, o que fazia "lag_1" apontar na
    # verdade para t-1 (dois meses antes do alvo) -- um bug de off-by-one
    # descoberto comparando contra o baseline do Dia 3 (ver docs/DEVLOG.md,
    # Dia 4): o modelo treinado com esse bug ficava sistematicamente pior
    # que a persistencia simples, porque nem enxergava o mes imediatamente
    # anterior ao alvo.
    df["lag_1"] = g[TARGET].shift(0)
    df["lag_2"] = g[TARGET].shift(1)
    df["lag_3"] = g[TARGET].shift(2)
    df["media_movel_3"] = g[TARGET].transform(lambda s: s.shift(0).rolling(3).mean())
    df["media_movel_expandida"] = g[TARGET].transform(lambda s: s.shift(0).expanding().mean())

    angulo = 2 * np.pi * (df[COL_MES] - 1) / 12
    df["mes_sin"] = np.sin(angulo)
    df["mes_cos"] = np.cos(angulo)

    df["log_consumidores"] = np.log1p(df[EXPOSURE])
    df["log_n_eventos_lag_1"] = np.log1p(g["n_eventos_validos"].shift(0))
    df["prop_causa_generica_lag_1"] = g["_prop_causa_generica"].shift(0)
    df["prop_causa_ambiental_lag_1"] = g["_prop_causa_ambiental"].shift(0)
    df["n_distribuidoras_lag_1"] = g["n_distribuidoras"].shift(0)

    df["alvo"] = g[TARGET].shift(-1)
    df["alvo_contagem"] = g["n_eventos_validos"].shift(-1)
    df["exposicao"] = df[EXPOSURE]

    # descarta as linhas sinteticas criadas so para o calendario ficar
    # completo (buracos e meses fora da janela de cada municipio) -- elas
    # ja cumpriram seu papel de impedir o shift de pular por cima delas.
    df = df[df["_linha_real"]].reset_index(drop=True)

    return df[COLUNAS_SAIDA].copy()


def filtrar_utilizaveis(dataset: pd.DataFrame) -> pd.DataFrame:
    """Remove linhas sem `lag_1` (primeiro mês de um município) ou sem
    `alvo` (último mês do histórico) -- as únicas duas colunas que TODO
    modelo (GLM ou GBM) precisa ter preenchidas."""
    return dataset.dropna(subset=["lag_1", "alvo"]).reset_index(drop=True)


def divisao_temporal(dataset: pd.DataFrame, ano_corte: int = 2025):
    """Corte temporal: treino = alvo observado antes de `ano_corte`, teste =
    alvo observado em `ano_corte` -- nunca embaralha meses entre os dois."""
    utilizaveis = filtrar_utilizaveis(dataset)
    alvo_periodo = utilizaveis["periodo"] + 1  # o mes do ALVO, nao do mes t
    treino = utilizaveis[alvo_periodo.dt.year < ano_corte].reset_index(drop=True)
    teste = utilizaveis[alvo_periodo.dt.year == ano_corte].reset_index(drop=True)
    return treino, teste
