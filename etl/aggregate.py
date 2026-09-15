"""Agregação do dataset limpo (nível evento) para o grão município x mês.

Essa é a tabela que alimenta a análise exploratória, o modelo de risco
(ml/) e a API -- reduz milhões de eventos brutos para um número de linhas
administrável (municípios x meses), sem perder a informação de causas, que
fica resumida em colunas `causa_<origem>`.

**Agregação em DOIS níveis, de propósito**: evento -> conjunto x mês ->
município x mês, em vez de ir direto de evento para município. A primeira
versão deste pipeline cruzava conjunto -> município já no nível evento
(~19 milhões de linhas) -- rodando contra o dataset real, isso estourou a
memória de uma máquina comum (`numpy._core._exceptions._ArrayMemoryError`,
um merge muitos-para-muitos produzindo mais de 100 milhões de linhas
intermediárias, já que ~40% dos conjuntos têm múltiplos municípios e
alguns conjuntos concentram muitos eventos -- ver docs/DEVLOG.md).
Agregando por conjunto x mês primeiro (no máximo algumas centenas de
milhares de linhas -- um conjunto x um mês, não um evento x um mês) e só
então fazendo o fan-out para município sobre esse dataset pequeno, o merge
fica trivial em memória sem abrir mão do mesmo tratamento ponderado para
conjuntos compartilhados.
"""
import pandas as pd

from etl.config import COL_AGENTE_SIGLA, COL_CONJUNTO_ID, COL_CONSUMIDORES_AFETADOS, COL_CONSUMIDORES_ATIVOS
from etl.ibge import fanout_municipio

CONJUNTO_GROUP_COLS = ["conjunto_id", "ano", "mes"]
MUNICIPIO_GROUP_COLS = ["codigo_ibge_resolvido", "nome_municipio", "uf_sigla", "regiao", "ano", "mes"]

# Colunas "extensivas" (contagens/somas) que fazem sentido divididas
# proporcionalmente entre os municípios de um conjunto compartilhado --
# `duracao_total_horas` fica de fora de propósito (ver docstring do
# módulo -- é uma grandeza "intensiva", entra inteira em cada município).
# `n_distribuidoras` é a aproximação menos exata do grupo: é um `nunique`
# por conjunto x mês, não uma soma "de verdade" -- ponderar e somar entre
# conjuntos/municípios é só uma estimativa (pode super ou subcontar quando
# a mesma distribuidora aparece em conjuntos diferentes do mesmo
# município), mas não há como manter uma contagem distinta exata sem
# guardar o nível evento, que é exatamente o que este desenho evita.
_COLUNAS_PONDERADAS_BASE = [
    "n_distribuidoras",
    "n_eventos_total",
    "n_eventos_programados",
    "n_eventos_validos",
    "consumidores_ativos_max",
    "consumidores_afetados_total",
]


_CAUSA_EXCLUIDA = "__PROGRAMADA_OU_INVALIDA__"


def _aggregate_conjunto_mes(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Primeiro nível: evento -> conjunto x mês (ver docstring do módulo).

    **Cuidado de memória, aprendido rodando contra os 18,9 milhões de
    eventos reais** (ver docs/DEVLOG.md): a primeira versão desta função
    fazia `validos = df[~df["programada"] & df["duracao_valida"]]` --
    filtrar linhas assim MATERIALIZA uma cópia inteira do DataFrame (todas
    as colunas, não só as usadas), o que travou uma máquina comum com
    `pyarrow.lib.ArrowMemoryError` (pandas 3.x usa arrays com backend Arrow
    por padrão, e o `.take()` por trás do filtro de linhas realoca um bloco
    contíguo do tamanho do resultado). A correção: em vez de filtrar
    linhas, mascaramos só as colunas necessárias com `.where(...)` --
    custo de memória de uma coluna por vez, não do DataFrame inteiro -- e
    fazemos toda a agregação em UMA única passada de `groupby`.
    """
    df = df.copy()
    df["conjunto_id"] = df[COL_CONJUNTO_ID].astype(str).str.strip()

    # "valido" = nao programado e com duracao valida -- eventos programados
    # ou com duracao invalida continuam CONTADOS (n_eventos_total,
    # n_eventos_programados), so ficam de fora das somas de duracao/
    # frequencia/causas, sem nunca serem removidos do dataset (ver
    # docs/REQUISITOS.md).
    valido = ~df["programada"] & df["duracao_valida"]
    df["_duracao_valida_horas"] = df["duracao_horas"].where(valido, 0.0)
    df["_consumidores_afetados_validos"] = df[COL_CONSUMIDORES_AFETADOS].where(valido, 0)
    df["_causa_origem_valida"] = df["causa_origem"].where(valido, _CAUSA_EXCLUIDA)
    df["_evento_valido"] = valido.astype("int64")

    # dropna=False é essencial: eventos com data ausente (ano/mes nulos)
    # não podem ser descartados silenciosamente pelo groupby -- ver
    # docs/REQUISITOS.md.
    base = (
        df.groupby(CONJUNTO_GROUP_COLS, dropna=False)
        .agg(
            n_distribuidoras=(COL_AGENTE_SIGLA, "nunique"),
            n_eventos_total=("conjunto_id", "size"),
            n_eventos_programados=("programada", "sum"),
            n_eventos_validos=("_evento_valido", "sum"),
            consumidores_ativos_max=(COL_CONSUMIDORES_ATIVOS, "max"),
            duracao_total_horas=("_duracao_valida_horas", "sum"),
            consumidores_afetados_total=("_consumidores_afetados_validos", "sum"),
        )
        .reset_index()
    )

    causas = (
        df.groupby(CONJUNTO_GROUP_COLS + ["_causa_origem_valida"], dropna=False)
        .size()
        .unstack(fill_value=0)
    )
    causas = causas.drop(columns=[_CAUSA_EXCLUIDA], errors="ignore")
    causas = causas.add_prefix("causa_")
    causas.columns = [c.strip().lower().replace(" ", "_") for c in causas.columns]
    causa_cols = list(causas.columns)
    causas = causas.reset_index()

    out = base.merge(causas, on=CONJUNTO_GROUP_COLS, how="left")
    out[causa_cols] = out[causa_cols].fillna(0)

    return out, causa_cols


def aggregate_municipio_mes(df: pd.DataFrame, bridge: pd.DataFrame, referencia: pd.DataFrame) -> pd.DataFrame:
    """Agrega o dataset limpo (`etl.clean.clean_interrupcoes`) para o grão
    município x mês, em dois passos: conjunto x mês (`_aggregate_conjunto_mes`)
    e depois fan-out + agregação final por município (`etl.ibge.fanout_municipio`).

    Quando um conjunto atende mais de um município, `peso_evento`
    (`1 / n_municipios_no_conjunto`) divide as colunas "extensivas"
    (contagens, consumidores) entre eles; ao final, municípios atendidos
    por MAIS DE UM conjunto somam as parcelas de cada um -- diferente de um
    `max` ingênuo, que subestimaria o total quando vários conjuntos
    distintos servem o mesmo município.
    """
    conjunto_mes, causa_cols = _aggregate_conjunto_mes(df)
    fanned = fanout_municipio(conjunto_mes, bridge, referencia, id_col="conjunto_id")

    colunas_ponderadas = _COLUNAS_PONDERADAS_BASE + causa_cols
    peso = fanned["peso_evento"]
    for col in colunas_ponderadas:
        fanned[col] = fanned[col] * peso

    agg_cols = {col: "sum" for col in colunas_ponderadas}
    agg_cols["duracao_total_horas"] = "sum"  # nao ponderada -- ver docstring do modulo
    agg_cols["n_municipios_no_conjunto"] = "mean"  # so para reportar, nao e uma soma

    out = fanned.groupby(MUNICIPIO_GROUP_COLS, dropna=False).agg(agg_cols).reset_index()

    # Indicadores próprios (aproximados -- não são o DEC/FEC oficial da
    # ANEEL, que usa "conjuntos de unidades consumidoras" como denominador;
    # aqui normalizamos por consumidores ativos do município no período, o
    # que é suficiente para o ranking de risco proposto). Ver
    # docs/REQUISITOS.md.
    out["fec_aprox"] = out["n_eventos_validos"] / out["consumidores_ativos_max"].replace(0, pd.NA)
    out["dec_aprox_horas"] = out["duracao_total_horas"] / out["consumidores_ativos_max"].replace(0, pd.NA)

    return out.sort_values(MUNICIPIO_GROUP_COLS).reset_index(drop=True)
