"""Limpeza dos registros de interrupcao (nivel evento) da ANEEL.

Cada linha de entrada e uma interrupcao individual, no formato bruto
publicado pela ANEEL (ver docs/ARQUITETURA.md para a lista de colunas).
Este modulo:

  1. Calcula a duracao da interrupcao (a ANEEL nao publica isso pronto).
  2. Sinaliza registros invalidos (duracao negativa/ausente) sem descarta-los
     silenciosamente -- eles ficam marcados em `duracao_valida=False`.
  3. Sinaliza registros expurgados (`DscMotivoExpurgo` preenchido) com
     `expurgado=True`, tambem sem descartar -- ver docs/REQUISITOS.md.
  4. Cruza o municipio (UF, nome, regiao) via etl.ibge.
"""
import logging

import pandas as pd

from etl.config import (
    COL_CONSUMIDORES_AFETADOS,
    COL_CONSUMIDORES_ATIVOS,
    COL_FIM,
    COL_INICIO,
    COL_MOTIVO_EXPURGO,
)
from etl.ibge import join_municipio, load_municipios_reference

logger = logging.getLogger(__name__)


def _parse_datetime(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    # Formato documentado pela ANEEL: dd/mm/yyyy hh:mm:ss
    return pd.to_datetime(series, format="%d/%m/%Y %H:%M:%S", errors="coerce")


def clean_interrupcoes(df_raw: pd.DataFrame, referencia: pd.DataFrame | None = None) -> pd.DataFrame:
    df = df_raw.copy()

    df[COL_INICIO] = _parse_datetime(df[COL_INICIO])
    df[COL_FIM] = _parse_datetime(df[COL_FIM])

    # O Parquet oficial da ANEEL ja publica esses campos como numericos, mas
    # forcamos a conversao aqui para o pipeline aceitar tambem CSV bruto (ex:
    # fixtures de teste) sem quebrar as contas mais adiante.
    df[COL_CONSUMIDORES_AFETADOS] = pd.to_numeric(df[COL_CONSUMIDORES_AFETADOS], errors="coerce")
    df[COL_CONSUMIDORES_ATIVOS] = pd.to_numeric(df[COL_CONSUMIDORES_ATIVOS], errors="coerce")

    df["duracao_horas"] = (df[COL_FIM] - df[COL_INICIO]).dt.total_seconds() / 3600
    df["duracao_valida"] = df["duracao_horas"].notna() & (df["duracao_horas"] >= 0)
    n_invalidas = (~df["duracao_valida"]).sum()
    if n_invalidas:
        logger.info(
            "%d/%d registros com duracao invalida (datas ausentes ou fim < inicio) -- "
            "mantidos, mas excluidos das somas de duracao",
            n_invalidas,
            len(df),
        )

    df["expurgado"] = df[COL_MOTIVO_EXPURGO].notna() & (df[COL_MOTIVO_EXPURGO].astype(str).str.strip() != "")

    referencia = referencia if referencia is not None else load_municipios_reference()
    df = join_municipio(df, referencia)

    return df
