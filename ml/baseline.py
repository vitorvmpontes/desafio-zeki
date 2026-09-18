"""Baseline oficial do Dia 3 (persistência combinada t-1 + t-12), reescrito
como um módulo reutilizável.

O notebook `02-baseline.ipynb` definiu e avaliou esse baseline só contra os
12 meses de 2025 (avaliação por corte temporal, comparando com o valor real
já observado). Este módulo generaliza a mesma regra para prever um mês-alvo
qualquer -- em particular o mês seguinte ao último mês disponível no painel,
que é o que `api/` precisa para mostrar o baseline ao lado da previsão do
gradient boosting (ver `docs/REQUISITOS.md`, decisão "Dia 4" sobre manter o
baseline como referência).

Regra (idêntica à do Dia 3): para o município `m` e o mês-alvo `t`,
`baseline(m, t) = média(fec_aprox(m, t-1), fec_aprox(m, t-12))`, usando
qualquer um dos dois que estiver disponível (se só um existir, o baseline
vira esse único valor -- se nenhum existir, não há baseline possível para
aquele município).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COL_ID = "codigo_ibge_resolvido"
TARGET = "fec_aprox"


def _periodo(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime({"year": df["ano"], "month": df["mes"], "day": 1}).dt.to_period("M")


def _serie_real(painel: pd.DataFrame) -> pd.DataFrame:
    """Só as linhas reais (município resolvido), com a coluna `periodo`."""
    df = painel.dropna(subset=["nome_municipio"]).copy()
    df["periodo"] = _periodo(df)
    return df


def prever_baseline(painel: pd.DataFrame, periodo_alvo: pd.Period | None = None) -> pd.DataFrame:
    """Baseline combinado para um mês-alvo, por município.

    Se `periodo_alvo` não for informado, usa o mês seguinte ao último mês
    observado de CADA município (o que a API precisa para a previsão "do
    próximo mês") -- municípios diferentes podem então ter mês-alvo
    diferente, se o histórico deles não for igualmente recente; no dado real
    atual (2024-01 a 2025-12) isso não acontece, todos os 5.509 municípios
    têm 2025-12 como último mês.

    Retorna uma linha por município com o mês-alvo usado e os dois
    componentes do baseline (`baseline_t1`/`baseline_t12`), além do valor
    combinado (`baseline_previsto`). Quando um componente não existe, a
    célula vem como NaN (não `None`) -- o pandas força isso ao montar a
    coluna float do DataFrame de saída; quem for expor via API deve
    converter NaN -> `null` explicitamente.
    """
    df = _serie_real(painel)
    valores = df.set_index([COL_ID, "periodo"])[TARGET]
    # em teoria (codigo, periodo) já é único no painel município x mês, mas
    # colapsa por segurança (ex.: se algum reprocessamento duplicar linhas)
    valores = valores.groupby(level=[0, 1]).mean()

    if periodo_alvo is not None:
        alvos = pd.Series(periodo_alvo, index=df[COL_ID].unique())
    else:
        alvos = df.groupby(COL_ID)["periodo"].max() + 1

    linhas = []
    for codigo, alvo in alvos.items():
        t1 = valores.get((codigo, alvo - 1), np.nan)
        t12 = valores.get((codigo, alvo - 12), np.nan)
        candidatos = [v for v in (t1, t12) if pd.notna(v)]
        linhas.append(
            {
                COL_ID: codigo,
                "periodo_alvo": alvo,
                "baseline_t1": float(t1) if pd.notna(t1) else None,
                "baseline_t12": float(t12) if pd.notna(t12) else None,
                "baseline_previsto": float(np.mean(candidatos)) if candidatos else None,
            }
        )
    return pd.DataFrame(linhas)
