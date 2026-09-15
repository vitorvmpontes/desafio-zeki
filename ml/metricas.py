"""Métricas de avaliação do modelo de risco -- as mesmas definições usadas
no baseline (`ml/notebooks/02-baseline.ipynb`), reescritas aqui em formato
"longo" (uma linha por município x mês) para reuso entre o baseline, os
modelos do Dia 4 (`ml/notebooks/04-modelagem.ipynb`) e o treino final
(`ml/train.py`) -- garante que todos são comparados exatamente da mesma
forma.

Como o produto é um RANKING mensal de risco, erro absoluto (MAE/RMSE) não
conta a história toda -- por isso, junto com MAE/RMSE, sempre reportamos:
correlação de Spearman do ranking e precisão no top 10% de risco (dos
municípios que o modelo põe no top 10% previsto, quantos realmente estavam
no top 10% real naquele mês) -- a métrica mais próxima do uso real do
produto (priorizar fiscalização/manutenção).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def avaliar_ranking(df: pd.DataFrame, coluna_periodo: str, coluna_real: str, coluna_previsto: str) -> dict:
    """`df` no formato longo (uma linha por município x mês de teste), com
    uma coluna de período (mês do alvo), uma de valor real e uma de valor
    previsto. Retorna a média das métricas calculadas mês a mês."""
    maes, rmses, spearmans, precisoes = [], [], [], []
    for _, grupo in df.groupby(coluna_periodo):
        real = grupo[coluna_real]
        previsto = grupo[coluna_previsto]
        if len(grupo) < 10:
            continue
        erro = real - previsto
        maes.append(erro.abs().mean())
        rmses.append(np.sqrt((erro ** 2).mean()))
        spearmans.append(real.rank().corr(previsto.rank()))
        k = max(1, int(len(grupo) * 0.1))
        top_real = set(real.sort_values(ascending=False).head(k).index)
        top_previsto = set(previsto.sort_values(ascending=False).head(k).index)
        precisoes.append(len(top_real & top_previsto) / k)
    return {
        "mae": float(np.mean(maes)),
        "rmse": float(np.mean(rmses)),
        "spearman": float(np.mean(spearmans)),
        "precisao_top10pct": float(np.mean(precisoes)),
        "n_meses_avaliados": len(maes),
    }
