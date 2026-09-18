"""Análises agregadas sobre o painel município x mês, para a página
"Análises" do frontend.

Reaproveita exatamente a metodologia já validada em
`ml/notebooks/01-eda.ipynb` (Dia 3) -- mesmas agregações, mesmas colunas --
só reescrita como funções reutilizáveis que a API pode chamar e servir como
JSON, em vez de ficar só em gráficos estáticos (PNG) dentro do notebook.
Nenhuma conclusão nova é inventada aqui: os números batem com os já
documentados em `docs/DEVLOG.md` (Dia 3/4).

`comparacao_modelo_baseline` só lê um artefato já existente
(`ml/artifacts/modelagem_metricas.json`, gerado no Dia 4 por
`ml/notebooks/04-modelagem.ipynb`) -- não recalcula nada.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

COL_ID = "codigo_ibge_resolvido"
TARGET = "fec_aprox"
CAUSA_COLS_GENERICAS = ("causa_interna", "causa_interno")


def sazonalidade_nacional(painel: pd.DataFrame) -> list[dict]:
    """Volume nacional de eventos por ano/mês (soma de `n_eventos_total`,
    já ponderado pelo fan-out de `etl/ibge.py`) -- mesma agregação da seção
    2 do EDA. Mostra o padrão sazonal (pico dez-jan/set-out, vale jun-jul)."""
    por_mes = painel.groupby(["ano", "mes"], as_index=False)["n_eventos_total"].sum()
    por_mes = por_mes.sort_values(["ano", "mes"])
    return [
        {"ano": int(row.ano), "mes": int(row.mes), "n_eventos_total": float(row.n_eventos_total)}
        for row in por_mes.itertuples()
    ]


def disparidade_regional(painel: pd.DataFrame) -> list[dict]:
    """Eventos por 1.000 consumidores/mês, por região -- normalizado por
    consumidor (não volume bruto), mesma lógica de `fec_aprox`. Ver seção 3
    do EDA: em volume bruto o Sudeste domina (mais consumidores), mas
    normalizado Norte/Nordeste têm taxa maior."""
    n_periodos = painel[["ano", "mes"]].drop_duplicates().shape[0]
    por_regiao = painel.dropna(subset=["regiao"]).groupby("regiao").agg(
        n_eventos=("n_eventos_total", "sum"),
        consumidores=("consumidores_ativos_max", "sum"),
        municipios=(COL_ID, "nunique"),
    )
    por_regiao["eventos_por_1000_consumidores_mes"] = (
        por_regiao["n_eventos"] / por_regiao["consumidores"] * 1000 / n_periodos
    )
    por_regiao = por_regiao.sort_values("eventos_por_1000_consumidores_mes", ascending=False)
    return [
        {
            "regiao": regiao,
            "n_eventos_total": float(row["n_eventos"]),
            "municipios": int(row["municipios"]),
            "eventos_por_1000_consumidores_mes": round(float(row["eventos_por_1000_consumidores_mes"]), 3),
        }
        for regiao, row in por_regiao.iterrows()
    ]


def mix_causas(painel: pd.DataFrame, top_n: int = 8) -> dict:
    """Proporção de eventos válidos por causa (texto livre normalizado) --
    seção 4 do EDA: confirma que ~95% dos eventos só têm a causa genérica
    "interna"/"interno", sem detalhe -- limitação real do dado, não do
    pipeline."""
    causa_cols = [c for c in painel.columns if c.startswith("causa_")]
    total_validos = float(painel["n_eventos_validos"].sum())
    soma_causas = painel[causa_cols].sum()

    generico = sum(soma_causas.get(c, 0.0) for c in CAUSA_COLS_GENERICAS) / total_validos

    top = (soma_causas / total_validos * 100).sort_values(ascending=False).head(top_n)
    top_causas = [
        {"causa": nome.replace("causa_", "").replace("_", " "), "percentual": round(float(valor), 2)}
        for nome, valor in top.items()
        if valor > 0
    ]

    return {
        "percentual_causa_generica": round(float(generico) * 100, 1),
        "n_causas_distintas": len(causa_cols),
        "top_causas": top_causas,
    }


def persistencia_risco(painel: pd.DataFrame, tamanho_amostra: int = 500, seed: int = 42) -> dict:
    """Correlação entre `fec_aprox` de um município num mês e no mês
    seguinte -- seção 5 do EDA: evidência de que o risco é persistente
    (existe sinal histórico real pra ranquear, não é ruído). Também devolve
    uma amostra de pontos (não o painel inteiro) para um gráfico de
    dispersão no frontend."""
    df = painel.dropna(subset=["nome_municipio"]).sort_values([COL_ID, "ano", "mes"]).copy()
    df["fec_aprox_mes_seguinte"] = df.groupby(COL_ID)[TARGET].shift(-1)
    valido = df.dropna(subset=[TARGET, "fec_aprox_mes_seguinte"])

    correlacao = valido[TARGET].corr(valido["fec_aprox_mes_seguinte"])

    n = min(tamanho_amostra, len(valido))
    amostra = valido.sample(n=n, random_state=seed)[[TARGET, "fec_aprox_mes_seguinte"]] if n else valido

    return {
        "correlacao_mes_a_mes": round(float(correlacao), 3),
        "amostra_dispersao": [
            {
                "fec_aprox": round(float(row[TARGET]), 5),
                "fec_aprox_mes_seguinte": round(float(row["fec_aprox_mes_seguinte"]), 5),
            }
            for row in amostra.to_dict(orient="records")
        ],
    }


def comparacao_modelo_baseline(caminho: Path) -> dict:
    """Lê o artefato já gerado no Dia 4 (`ml/notebooks/04-modelagem.ipynb`)
    com a comparação entre persistência simples, os dois GLMs, o gradient
    boosting e o baseline combinado do Dia 3 -- não recalcula nada, só
    expõe o que já foi validado."""
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def montar_analises(painel: pd.DataFrame, caminho_comparacao_modelos: Path) -> dict:
    """Monta o payload completo da página de Análises -- chamado uma vez na
    inicialização da API (`api/servico.py`), igual ao resto do estado."""
    return {
        "sazonalidade": sazonalidade_nacional(painel),
        "disparidade_regional": disparidade_regional(painel),
        "mix_causas": mix_causas(painel),
        "persistencia": persistencia_risco(painel),
        "comparacao_modelos": comparacao_modelo_baseline(caminho_comparacao_modelos),
    }
