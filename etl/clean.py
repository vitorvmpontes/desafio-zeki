"""Limpeza dos registros de interrupção (nível evento) da ANEEL.

Cada linha de entrada é uma interrupção individual, no schema real
publicado pela ANEEL (18 colunas, bem diferente do que a documentação
oficial descrevia -- ver docs/DEVLOG.md, "Dia 2 — descoberta do schema
real"). Este módulo:

  1. Calcula a duração da interrupção (a ANEEL não publica isso pronto).
  2. Sinaliza registros com duração inválida (ausente ou fim < início) sem
     descartá-los -- ficam marcados em `duracao_valida=False`.
  3. Deriva `ano`/`mes` de `DatInicioInterrupcao` -- o schema real não tem
     `AnoCompetencia`/`MesCompetencia`.
  4. Sinaliza interrupções programadas (`DscTipoInterrupcao == "Programada"`)
     em vez de "expurgadas" -- o campo `DscMotivoExpurgo` que a documentação
     oficial descrevia não existe no Parquet real; `DscTipoInterrupcao` é o
     filtro análogo disponível (ver docstring de `clean_interrupcoes`).
  5. Normaliza `DscFatoGeradorInterrupcao` (causa), que vem em texto livre
     com separadores e capitalização/acentuação inconsistentes.
  6. Cruza o conjunto de unidades consumidoras com o município que ele
     atende, via `etl.ibge.join_conjunto_municipio` (com fan-out para
     conjuntos que atendem mais de um município).
"""
import logging
import unicodedata

import pandas as pd

from etl.config import (
    COL_AGENTE_SIGLA,
    COL_CONSUMIDORES_AFETADOS,
    COL_CONSUMIDORES_ATIVOS,
    COL_FATO_GERADOR,
    COL_FIM,
    COL_INICIO,
    COL_MOTIVO_ID,
    COL_TIPO_INTERRUPCAO,
)
from etl.ibge import join_conjunto_municipio, load_conjunto_municipio_bridge, load_municipios_reference

logger = logging.getLogger(__name__)


def _parse_datetime(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    # Formato documentado pela ANEEL: dd/mm/yyyy hh:mm:ss
    return pd.to_datetime(series, format="%d/%m/%Y %H:%M:%S", errors="coerce")


def _strip_accents(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar_causa(series: pd.Series) -> pd.DataFrame:
    """Normaliza `DscFatoGeradorInterrupcao`.

    O campo real mistura separadores (`;`, `-`, ` - `) e
    capitalização/acentuação inconsistentes para descrever a MESMA causa --
    ex.: ``"INTERNA;NAO PROGRAMADA;PROPRIAS DO SISTEMA;FALHA DE MATERIAL OU
    EQUIPAMENTO"`` e ``"Interna-Não programada-Próprias do sistema-Falha de
    material ou equipamento"`` são o mesmo valor. Sem normalizar, um
    ``value_counts()`` ingênuo conta como causas diferentes (visto nos
    dados reais -- ver docs/DEVLOG.md).

    Retorna duas colunas:
      - ``causa_normalizada``: string canônica (maiúscula, sem acento,
        componentes sempre separados por ``;``).
      - ``causa_origem``: primeiro componente (tipicamente
        INTERNA/EXTERNA) -- usado no mix de causas da agregação.
    """
    bruto = series.fillna("").astype(str).map(_strip_accents).str.upper().str.strip()
    canonico = bruto.str.replace(r"\s*-\s*", ";", regex=True)
    canonico = canonico.str.replace(r"\s*;\s*", ";", regex=True).str.strip(";")
    origem = canonico.str.split(";").str[0]
    origem = origem.where(origem.str.len() > 0, "NAO_INFORMADO")
    return pd.DataFrame({"causa_normalizada": canonico, "causa_origem": origem})


def clean_interrupcoes(
    df_raw: pd.DataFrame,
    referencia: pd.DataFrame | None = None,
    bridge: pd.DataFrame | None = None,
) -> pd.DataFrame:
    df = df_raw.copy()

    df[COL_INICIO] = _parse_datetime(df[COL_INICIO])
    df[COL_FIM] = _parse_datetime(df[COL_FIM])

    # O Parquet oficial da ANEEL já publica esses campos como numéricos, mas
    # forçamos a conversão aqui para o pipeline aceitar também CSV bruto (ex:
    # fixtures de teste) sem quebrar as contas mais adiante.
    df[COL_CONSUMIDORES_AFETADOS] = pd.to_numeric(df[COL_CONSUMIDORES_AFETADOS], errors="coerce")
    df[COL_CONSUMIDORES_ATIVOS] = pd.to_numeric(df[COL_CONSUMIDORES_ATIVOS], errors="coerce")

    # `SigAgente` vem com espaços em branco à direita nos dados reais (ex:
    # "EAC                 ") -- sem strip, a mesma distribuidora contaria
    # como duas diferentes em `nunique()`.
    df[COL_AGENTE_SIGLA] = df[COL_AGENTE_SIGLA].astype(str).str.strip()

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

    # Schema real não tem AnoCompetencia/MesCompetencia -- derivamos do
    # início da própria interrupção.
    df["ano"] = df[COL_INICIO].dt.year
    df["mes"] = df[COL_INICIO].dt.month

    # Não existe campo equivalente a "DscMotivoExpurgo" no schema real (a
    # documentação oficial usada para desenhar este pipeline descrevia um
    # campo que não está no Parquet publicado -- ver docs/DEVLOG.md). O
    # filtro análogo disponível é `DscTipoInterrupcao`: interrupções
    # "Programada" (manutenção preventiva avisada) são sinalizadas mas não
    # descartadas, e ficam de fora das somas de duração/frequência da mesma
    # forma que os antigos "expurgados" ficavam -- ver docs/REQUISITOS.md.
    # Isso NÃO é semanticamente idêntico ao conceito de expurgo oficial da
    # ANEEL (que também exclui, por ex., eventos de força maior); é a
    # aproximação honesta possível com os campos realmente publicados.
    df["programada"] = df[COL_TIPO_INTERRUPCAO].astype(str).str.strip().str.upper() == "PROGRAMADA"

    # `IdeMotivoInterrupcao` é um código numérico sem dicionário de dados
    # publicado junto do Parquet -- mantido bruto (sem decodificar) para não
    # inventar uma interpretação não verificada. Ver docs/DEVLOG.md.
    df["motivo_interrupcao_codigo"] = df[COL_MOTIVO_ID]

    causa = normalizar_causa(df[COL_FATO_GERADOR])
    df["causa_normalizada"] = causa["causa_normalizada"]
    df["causa_origem"] = causa["causa_origem"]

    referencia = referencia if referencia is not None else load_municipios_reference()
    bridge = bridge if bridge is not None else load_conjunto_municipio_bridge()
    df = join_conjunto_municipio(df, bridge, referencia)

    return df
