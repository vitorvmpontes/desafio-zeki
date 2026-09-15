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

**`aggregate_conjunto_mes` roda por LOTE, nunca sobre os ~19 milhões de
eventos de uma vez** -- mesmo depois de eliminar o filtro de linhas que
estourava memória (ver docstring de `aggregate_conjunto_mes`), manter as
colunas derivadas de limpeza (`etl.clean`) para os 18,9 milhões de eventos
inteiros ao mesmo tempo ainda esgotava a memória de uma máquina comum
(`numpy._core._exceptions._ArrayMemoryError`/`ArrowMemoryError` mesmo para
alocações pequenas, de ~150 MiB -- sinal de que não sobrava quase memória
livre nesse ponto). `etl.pipeline` lê o Parquet em lotes (via
`pyarrow.parquet.ParquetFile.iter_batches`), limpa e agrega CADA LOTE
separadamente para o grão conjunto x mês, e `combine_conjunto_mes` junta os
resultados parciais (pequenos) no final -- o pico de memória fica limitado
ao tamanho de um lote, não ao dataset inteiro, então o número total de
eventos deixa de importar para a viabilidade do pipeline.
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
# `n_distribuidoras` também fica de fora: não é uma soma, é a cardinalidade
# de um conjunto de nomes (ver `_DISTRIBUIDORAS_SET_COL` mais abaixo).
_COLUNAS_PONDERADAS_BASE = [
    "n_eventos_total",
    "n_eventos_programados",
    "n_eventos_validos",
    "consumidores_ativos_max",
    "consumidores_afetados_total",
]

# `n_distribuidoras` -- contagem EXATA de distribuidoras distintas, mesmo
# passando por lotes (`combine_conjunto_mes`) e por conjuntos diferentes
# fanned-out para o mesmo município (`aggregate_municipio_mes`). Uma
# primeira versão calculava isso com `nunique` direto em cada nível e somava
# (ou ponderava) o resultado entre lotes/conjuntos -- o que super ou
# subcontava sempre que a mesma distribuidora aparecia em mais de um
# lote/conjunto para o mesmo grupo (pego por
# `test_processar_em_lotes_da_o_mesmo_resultado_que_de_uma_vez`). A
# correção: carregar o CONJUNTO de nomes (não a contagem) por todos os
# passos de agregação, unindo (nunca somando) entre lotes/conjuntos, e só
# converter para contagem (`len()`) no grão final -- assim a união elimina
# duplicatas exatamente como um `set()` faria.
_DISTRIBUIDORAS_SET_COL = "_distribuidoras_set"


def _unir_conjuntos(serie: pd.Series) -> frozenset:
    uniao: frozenset = frozenset()
    for s in serie:
        uniao |= s
    return uniao


_CAUSA_EXCLUIDA = "__PROGRAMADA_OU_INVALIDA__"

# Colunas somáveis ao combinar resultados parciais de lotes diferentes
# (`combine_conjunto_mes`) -- o mesmo conjunto x mês pode ter eventos
# espalhados em lotes diferentes (o Parquet não vem ordenado por conjunto),
# então tudo aqui é soma, exceto `consumidores_ativos_max` (max entre
# lotes) e `_distribuidoras_set` (união, ver acima).
_COLUNAS_SOMAVEIS_ENTRE_LOTES = [
    "n_eventos_total",
    "n_eventos_programados",
    "n_eventos_validos",
    "duracao_total_horas",
    "consumidores_afetados_total",
]


def aggregate_conjunto_mes(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
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
            _distribuidoras_set=(COL_AGENTE_SIGLA, lambda s: frozenset(s)),
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


def combine_conjunto_mes(partes: list[pd.DataFrame]) -> tuple[pd.DataFrame, list[str]]:
    """Combina os resultados parciais de `aggregate_conjunto_mes` calculados
    por lote (ver `etl.pipeline`) em uma única tabela conjunto x mês.

    O mesmo conjunto x mês pode ter eventos em lotes diferentes (o Parquet
    não vem ordenado por conjunto), então as colunas "extensivas" são
    somadas entre lotes, e `consumidores_ativos_max` toma o máximo -- cada
    lote já é pequeno (poucas centenas de milhares de linhas no máximo),
    então concatenar e reagrupar os resultados parciais é barato.
    """
    causa_cols = sorted({c for parte in partes for c in parte.columns if c.startswith("causa_")})

    todas = pd.concat(partes, ignore_index=True, sort=False)
    for col in causa_cols:
        if col not in todas.columns:
            todas[col] = 0
    todas[causa_cols] = todas[causa_cols].fillna(0)

    agg_cols = {col: "sum" for col in _COLUNAS_SOMAVEIS_ENTRE_LOTES + causa_cols}
    agg_cols["consumidores_ativos_max"] = "max"
    agg_cols[_DISTRIBUIDORAS_SET_COL] = _unir_conjuntos

    combinado = todas.groupby(CONJUNTO_GROUP_COLS, dropna=False).agg(agg_cols).reset_index()
    return combinado, causa_cols


def aggregate_municipio_mes(
    conjunto_mes: pd.DataFrame,
    causa_cols: list[str],
    bridge: pd.DataFrame,
    referencia: pd.DataFrame,
) -> pd.DataFrame:
    """Agrega a tabela conjunto x mês (`aggregate_conjunto_mes` +
    `combine_conjunto_mes`, ver docstring do módulo) para o grão final
    município x mês: fan-out (`etl.ibge.fanout_municipio`) e agregação.

    Quando um conjunto atende mais de um município, `peso_evento`
    (`1 / n_municipios_no_conjunto`) divide as colunas "extensivas"
    (contagens, consumidores) entre eles; ao final, municípios atendidos
    por MAIS DE UM conjunto somam as parcelas de cada um -- diferente de um
    `max` ingênuo, que subestimaria o total quando vários conjuntos
    distintos servem o mesmo município.
    """
    fanned = fanout_municipio(conjunto_mes, bridge, referencia, id_col="conjunto_id")

    colunas_ponderadas = _COLUNAS_PONDERADAS_BASE + causa_cols
    peso = fanned["peso_evento"]
    for col in colunas_ponderadas:
        fanned[col] = fanned[col] * peso

    agg_cols = {col: "sum" for col in colunas_ponderadas}
    agg_cols["duracao_total_horas"] = "sum"  # nao ponderada -- ver docstring do modulo
    agg_cols["n_municipios_no_conjunto"] = "mean"  # so para reportar, nao e uma soma
    agg_cols[_DISTRIBUIDORAS_SET_COL] = _unir_conjuntos  # nao ponderada -- ver nota acima

    out = fanned.groupby(MUNICIPIO_GROUP_COLS, dropna=False).agg(agg_cols).reset_index()
    out["n_distribuidoras"] = out[_DISTRIBUIDORAS_SET_COL].map(len)
    out = out.drop(columns=[_DISTRIBUIDORAS_SET_COL])

    # Indicadores próprios (aproximados -- não são o DEC/FEC oficial da
    # ANEEL, que usa "conjuntos de unidades consumidoras" como denominador;
    # aqui normalizamos por consumidores ativos do município no período, o
    # que é suficiente para o ranking de risco proposto). Ver
    # docs/REQUISITOS.md.
    out["fec_aprox"] = out["n_eventos_validos"] / out["consumidores_ativos_max"].replace(0, pd.NA)
    out["dec_aprox_horas"] = out["duracao_total_horas"] / out["consumidores_ativos_max"].replace(0, pd.NA)

    return out.sort_values(MUNICIPIO_GROUP_COLS).reset_index(drop=True)
