"""Cruza o conjunto de unidades consumidoras de cada interrupção com o
município que ele atende.

Historicamente este módulo assumia que a ANEEL publicava um
`CodMunicipioIBGE` direto no dataset de interrupções -- descobrimos, só ao
processar o Parquet real (ver docs/DEVLOG.md, "Dia 2 — descoberta do schema
real"), que isso está errado: o dataset só identifica o conjunto de
unidades consumidoras (`IdeConjuntoUnidadeConsumidora`). O de-para
conjunto -> município é publicado à parte, no dataset "IndQual Município"
(ver `etl/config.py`). Mantivemos o nome do arquivo (`ibge.py`) para não
precisar de uma renomeação de módulo no meio da correção, mas o join hoje é
conjunto -> município, não mais código IBGE direto.

**Complicação real, não documentada previamente**: a relação conjunto ->
município NÃO é 1:1. Nos dados de 2024/2025, de 15.162 conjuntos, 6.135
(40,5%) atendem MAIS DE UM município -- um único conjunto pode cobrir uma
cidade inteira e partes de cidades vizinhas.

**Decisão de projeto** (ver docs/REQUISITOS.md): em vez de escolher
arbitrariamente um "município principal" por conjunto -- o que enviesaria o
ranking de risco a favor ou contra municípios que dividem conjunto com
vizinhos, sem nenhuma base nos dados para essa escolha -- cada conjunto é
distribuído (fan-out) para TODOS os municípios que atende, e ganha um peso
`peso_evento = 1 / n_municipios_no_conjunto`. Isso mantém o total nacional
de eventos consistente (a soma dos pesos de um conjunto fanned-out é sempre
1) às custas de uma resolução mais grosseira exatamente nos conjuntos
compartilhados -- uma limitação real do dado publicado pela ANEEL, não do
pipeline, e por isso é reportada explicitamente (`n_municipios_no_conjunto`)
em vez de escondida atrás de uma escolha arbitrária.

**Importante -- por que o fan-out acontece no dataset JÁ AGREGADO por
conjunto x mês, nunca no dataset de eventos brutos**: a primeira versão
deste pipeline fazia o fan-out linha a linha, no nível evento (~19 milhões
de linhas). Rodando contra o dataset real, isso estourou a memória de uma
máquina comum (`numpy._core._exceptions._ArrayMemoryError`, um merge
muitos-para-muitos gerando mais de 100 milhões de linhas intermediárias --
ver docs/DEVLOG.md). A correção agrega primeiro por conjunto x mês (no
máximo algumas centenas de milhares de linhas) e só então faz o fan-out
sobre esse dataset pequeno -- ver `etl.aggregate` para o pipeline completo
de dois níveis.
"""
import logging

import pandas as pd

from etl.config import (
    COL_BRIDGE_COD_MUNICIPIO,
    COL_BRIDGE_CONJUNTO_ID,
    COL_BRIDGE_NOME_MUNICIPIO,
    COL_BRIDGE_UF,
    CONJUNTO_MUNICIPIO_PATH,
    MUNICIPIOS_REFERENCE_PATH,
)

logger = logging.getLogger(__name__)

_CAMPOS_REGIAO = ["codigo_ibge_7", "regiao"]


def load_municipios_reference(path=MUNICIPIOS_REFERENCE_PATH) -> pd.DataFrame:
    """Tabela IBGE/UF/região (kelvins/municipios-brasileiros).

    Usada aqui só como lookup auxiliar de REGIÃO a partir do código IBGE
    resolvido -- o dataset "IndQual Município" já dá município/UF
    diretamente, mas não publica região.
    """
    return pd.read_csv(path, dtype=str)


def load_conjunto_municipio_bridge(path=CONJUNTO_MUNICIPIO_PATH) -> pd.DataFrame:
    """Lê o de-para conjunto -> município (dataset "IndQual Município").

    Um mesmo `IdeConjUnidConsumidoras` pode aparecer em múltiplas linhas --
    uma por município atendido (ver docstring do módulo). Este CSV não
    depende do ano (não é reprocessado por competência), então uma única
    cópia serve para todos os anos baixados.
    """
    bridge = pd.read_csv(path, dtype=str, encoding="latin1", sep=None, engine="python")
    bridge = bridge.rename(
        columns={
            COL_BRIDGE_CONJUNTO_ID: "conjunto_id",
            COL_BRIDGE_COD_MUNICIPIO: "codigo_ibge_bridge",
            COL_BRIDGE_NOME_MUNICIPIO: "nome_municipio",
            COL_BRIDGE_UF: "uf_sigla",
        }
    )
    bridge["conjunto_id"] = bridge["conjunto_id"].astype(str).str.strip()
    bridge["codigo_ibge_bridge"] = (
        bridge["codigo_ibge_bridge"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    )
    bridge = bridge.drop_duplicates(["conjunto_id", "codigo_ibge_bridge"])

    bridge["n_municipios_no_conjunto"] = bridge.groupby("conjunto_id")["codigo_ibge_bridge"].transform("nunique")

    total_conjuntos = bridge["conjunto_id"].nunique()
    multiplos = (bridge.groupby("conjunto_id")["codigo_ibge_bridge"].nunique() > 1).sum()
    logger.info(
        "Bridge conjunto->municipio: %d conjuntos, %d (%.1f%%) atendem mais de um municipio",
        total_conjuntos,
        multiplos,
        100 * multiplos / total_conjuntos if total_conjuntos else 0.0,
    )
    return bridge


def _resolver_regiao(bridge: pd.DataFrame, referencia: pd.DataFrame) -> pd.DataFrame:
    """Preenche `regiao` e o código IBGE canônico (7 dígitos) via a tabela
    kelvins, com o mesmo fallback de 7 -> 6 dígitos usado historicamente (a
    IndQual Município às vezes publica o código sem o dígito verificador).
    """
    ref_7 = referencia.set_index("codigo_ibge_7", drop=False)[_CAMPOS_REGIAO]
    ref_6 = (
        referencia.assign(codigo_ibge_6=referencia["codigo_ibge_7"].str[:6])
        .drop_duplicates("codigo_ibge_6")
        .set_index("codigo_ibge_6", drop=False)[_CAMPOS_REGIAO]
    )

    codigo = bridge["codigo_ibge_bridge"]
    codigo_6 = codigo.str[:6]

    match_7 = codigo.map(ref_7.to_dict("index"))
    match_6 = codigo_6.map(ref_6.to_dict("index"))
    resolved = match_7.where(match_7.notna(), match_6)

    def campo(nome):
        return resolved.map(lambda v, c=nome: v[c] if isinstance(v, dict) else None)

    out = bridge.copy()
    out["codigo_ibge_resolvido"] = campo("codigo_ibge_7").fillna(codigo)
    out["regiao"] = campo("regiao")
    return out


def fanout_municipio(
    df_agregado: pd.DataFrame,
    bridge: pd.DataFrame,
    referencia: pd.DataFrame,
    id_col: str = "conjunto_id",
) -> pd.DataFrame:
    """Faz o fan-out de um dataset JÁ AGREGADO por conjunto (ex.: conjunto x
    mês) para município -- nunca do dataset de eventos brutos (ver
    docstring do módulo para o porquê).

    Adiciona `codigo_ibge_resolvido` / `nome_municipio` / `uf_sigla` /
    `regiao` / `n_municipios_no_conjunto` / `peso_evento`.

    Conjuntos que não são encontrados na bridge (sem correspondência) são
    mantidos -- nunca descartados (ver docs/REQUISITOS.md) -- com
    município/UF/região nulos e `codigo_ibge_resolvido` marcado como
    `CONJUNTO_<id>` (para não conflar conjuntos desconhecidos diferentes no
    mesmo grupo "sem município"), `n_municipios_no_conjunto=1` e
    `peso_evento=1.0`, para não precisar de tratamento especial na
    agregação seguinte.
    """
    bridge_resolvido = _resolver_regiao(bridge, referencia)

    out = df_agregado.merge(
        bridge_resolvido[
            ["conjunto_id", "codigo_ibge_resolvido", "nome_municipio", "uf_sigla", "regiao", "n_municipios_no_conjunto"]
        ],
        left_on=id_col,
        right_on="conjunto_id",
        how="left",
    )

    sem_match = out["codigo_ibge_resolvido"].isna()
    out.loc[sem_match, "codigo_ibge_resolvido"] = "CONJUNTO_" + out.loc[sem_match, id_col].astype(str)
    out["n_municipios_no_conjunto"] = out["n_municipios_no_conjunto"].fillna(1)
    out["peso_evento"] = 1.0 / out["n_municipios_no_conjunto"]

    total = len(df_agregado)
    linhas_fanout = len(out) - total
    taxa_sem_match = 100 * sem_match.sum() / len(out) if len(out) else 0.0
    logger.info(
        "Fan-out conjunto->municipio (nivel conjunto x mes): %d linhas -> %d apos fan-out (+%d), "
        "%.2f%% sem correspondencia na bridge",
        total,
        len(out),
        linhas_fanout,
        taxa_sem_match,
    )
    if taxa_sem_match > 5:
        logger.warning(
            "Taxa de conjuntos sem correspondencia na bridge acima de 5%% -- vale investigar "
            "antes de seguir (ex: bridge desatualizada em relacao ao Parquet de interrupcoes)."
        )

    return out
