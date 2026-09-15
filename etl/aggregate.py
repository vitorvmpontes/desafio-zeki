"""Agregacao do dataset limpo (nivel evento) para o grao municipio x mes.

Essa e a tabela que alimenta a analise exploratoria, o modelo de risco (ml/)
e a API -- reduz centenas de milhares de eventos brutos para um numero de
linhas administravel (municipios x meses), sem perder a informacao de
causas, que fica resumida em colunas `causa_<origem>`.
"""
import pandas as pd

from etl.config import (
    COL_AGENTE_SIGLA,
    COL_ANO_COMPETENCIA,
    COL_CONSUMIDORES_AFETADOS,
    COL_CONSUMIDORES_ATIVOS,
    COL_FATO_GERADOR_ORIGEM,
    COL_MES_COMPETENCIA,
)

GROUP_COLS = ["codigo_ibge_resolvido", "nome_municipio", "uf_sigla", "regiao", "ano", "mes"]


def aggregate_municipio_mes(df: pd.DataFrame, codigo_municipio_col: str) -> pd.DataFrame:
    """Agrega o dataset limpo (ja passado por etl.clean, com codigo_ibge_resolvido
    preenchido) para o grao municipio x mes.

    `codigo_municipio_col` e usado apenas para contar eventos (`size`); o
    agrupamento em si usa sempre `codigo_ibge_resolvido` (a chave canonica
    produzida pelo join em etl.ibge), nunca o codigo bruto -- ver o
    docstring de `etl.ibge.join_municipio` para o porque.
    """
    df = df.copy()
    df["ano"] = df[COL_ANO_COMPETENCIA].astype(int)
    df["mes"] = df[COL_MES_COMPETENCIA].astype(int)

    # Só eventos não-expurgados e com duração válida entram nas somas de
    # duração/frequência -- expurgados continuam contados à parte para
    # transparência, nunca somem silenciosamente do dataset.
    validos = df[~df["expurgado"] & df["duracao_valida"]]

    # dropna=False e essencial: municipios sem correspondencia no join (ver
    # etl.ibge.join_municipio) ficam com uf_sigla/nome_municipio/regiao
    # nulos, e o comportamento padrao do pandas e DESCARTAR silenciosamente
    # qualquer grupo cuja chave contenha NaN -- o que violaria a decisao
    # documentada em docs/REQUISITOS.md de nunca descartar esses registros.
    base = (
        df.groupby(GROUP_COLS, dropna=False)
        .agg(
            n_distribuidoras=(COL_AGENTE_SIGLA, "nunique"),
            n_eventos_total=(codigo_municipio_col, "size"),
            n_eventos_expurgados=("expurgado", "sum"),
            consumidores_ativos_max=(COL_CONSUMIDORES_ATIVOS, "max"),
        )
        .reset_index()
    )

    validos_agg = (
        validos.groupby(GROUP_COLS, dropna=False)
        .agg(
            n_eventos_validos=(codigo_municipio_col, "size"),
            duracao_total_horas=("duracao_horas", "sum"),
            duracao_media_horas=("duracao_horas", "mean"),
            consumidores_afetados_total=(COL_CONSUMIDORES_AFETADOS, "sum"),
        )
        .reset_index()
    )

    out = base.merge(validos_agg, on=GROUP_COLS, how="left")
    for col in ["n_eventos_validos", "duracao_total_horas", "consumidores_afetados_total"]:
        out[col] = out[col].fillna(0)

    # Indicadores proprios (aproximados -- nao sao o DEC/FEC oficial da
    # ANEEL, que usa "conjuntos de unidades consumidoras" como denominador;
    # aqui normalizamos por consumidores ativos do municipio no periodo, o
    # que e suficiente para o ranking de risco proposto). Ver
    # docs/REQUISITOS.md.
    out["fec_aprox"] = out["n_eventos_validos"] / out["consumidores_ativos_max"].replace(0, pd.NA)
    out["dec_aprox_horas"] = out["duracao_total_horas"] / out["consumidores_ativos_max"].replace(0, pd.NA)

    # Mix de causas: uma coluna por valor de DscFatoGeradorOrigem observado,
    # com a contagem de eventos (nao-expurgados) daquela causa no periodo.
    if COL_FATO_GERADOR_ORIGEM in df.columns:
        causas = (
            validos.groupby(GROUP_COLS + [COL_FATO_GERADOR_ORIGEM], dropna=False)
            .size()
            .unstack(fill_value=0)
            .add_prefix("causa_")
        )
        causas.columns = [c.strip().lower().replace(" ", "_") for c in causas.columns]
        out = out.merge(causas.reset_index(), on=GROUP_COLS, how="left")

    return out.sort_values(GROUP_COLS).reset_index(drop=True)
