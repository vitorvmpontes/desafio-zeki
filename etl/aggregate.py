"""Agregação do dataset limpo (nível evento, já com fan-out de município)
para o grão município x mês.

Essa é a tabela que alimenta a análise exploratória, o modelo de risco
(ml/) e a API -- reduz milhões de eventos brutos para um número de linhas
administrável (municípios x meses), sem perder a informação de causas, que
fica resumida em colunas `causa_<origem>`.
"""
import pandas as pd

from etl.config import COL_AGENTE_SIGLA, COL_CONSUMIDORES_AFETADOS, COL_CONSUMIDORES_ATIVOS

GROUP_COLS = ["codigo_ibge_resolvido", "nome_municipio", "uf_sigla", "regiao", "ano", "mes"]


def aggregate_municipio_mes(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega o dataset já limpo e cruzado com município (`etl.clean`,
    `etl.ibge.join_conjunto_municipio`) para o grão município x mês.

    `peso_evento` (`1 / n_municipios_no_conjunto`, ver `etl.ibge`) é usado
    para contagens e para consumidores (grandezas "extensivas", que fazem
    sentido divididas entre municípios): quando um conjunto atende mais de
    um município, o mesmo evento (e os mesmos números de consumidores, que
    são publicados por CONJUNTO, não por município) aparece em uma linha
    por município fanned-out -- sem ponderar, cada município "herdaria" o
    evento inteiro e os totais nacionais ficariam inflados pelo número de
    municípios compartilhados. Ponderando por `peso_evento`, a soma de um
    evento fanned-out entre N municípios continua valendo 1 evento no total
    nacional.

    `duracao_horas` é a exceção deliberada: é uma grandeza "intensiva" (o
    tempo que a interrupção durou), não uma contagem -- não faz sentido
    dividir por 2 a duração de um evento só porque seu conjunto atende dois
    municípios, então ela entra inteira na soma de cada município afetado.
    """
    df = df.copy()
    df["_consumidores_afetados_ponderado"] = df[COL_CONSUMIDORES_AFETADOS] * df["peso_evento"]
    df["_consumidores_ativos_ponderado"] = df[COL_CONSUMIDORES_ATIVOS] * df["peso_evento"]
    df["_peso_se_programada"] = df["programada"] * df["peso_evento"]

    # Só eventos não-programados e com duração válida entram nas somas de
    # duração/frequência -- programados continuam contados à parte para
    # transparência, nunca somem silenciosamente do dataset.
    validos = df[~df["programada"] & df["duracao_valida"]]

    # dropna=False é essencial: municípios sem correspondência no join (ver
    # etl.ibge.join_conjunto_municipio) ficam com uf_sigla/nome_municipio/
    # regiao nulos, e o comportamento padrão do pandas é DESCARTAR
    # silenciosamente qualquer grupo cuja chave contenha NaN -- o que
    # violaria a decisão documentada em docs/REQUISITOS.md de nunca
    # descartar esses registros.
    base = (
        df.groupby(GROUP_COLS, dropna=False)
        .agg(
            n_distribuidoras=(COL_AGENTE_SIGLA, "nunique"),
            n_eventos_total=("peso_evento", "sum"),
            n_eventos_programados=("_peso_se_programada", "sum"),
            consumidores_ativos_max=("_consumidores_ativos_ponderado", "max"),
            n_municipios_no_conjunto_medio=("n_municipios_no_conjunto", "mean"),
        )
        .reset_index()
    )

    validos_agg = (
        validos.groupby(GROUP_COLS, dropna=False)
        .agg(
            n_eventos_validos=("peso_evento", "sum"),
            duracao_total_horas=("duracao_horas", "sum"),
            duracao_media_horas=("duracao_horas", "mean"),
            consumidores_afetados_total=("_consumidores_afetados_ponderado", "sum"),
        )
        .reset_index()
    )

    out = base.merge(validos_agg, on=GROUP_COLS, how="left")
    for col in ["n_eventos_validos", "duracao_total_horas", "consumidores_afetados_total"]:
        out[col] = out[col].fillna(0)

    # Indicadores próprios (aproximados -- não são o DEC/FEC oficial da
    # ANEEL, que usa "conjuntos de unidades consumidoras" como denominador;
    # aqui normalizamos por consumidores ativos do município no período, o
    # que é suficiente para o ranking de risco proposto). Ver
    # docs/REQUISITOS.md.
    out["fec_aprox"] = out["n_eventos_validos"] / out["consumidores_ativos_max"].replace(0, pd.NA)
    out["dec_aprox_horas"] = out["duracao_total_horas"] / out["consumidores_ativos_max"].replace(0, pd.NA)

    # Mix de causas: uma coluna por valor de `causa_origem` observado (ver
    # etl.clean.normalizar_causa), com a soma ponderada (peso_evento) de
    # eventos não-programados daquela origem no período.
    causas = (
        validos.groupby(GROUP_COLS + ["causa_origem"], dropna=False)["peso_evento"]
        .sum()
        .unstack(fill_value=0)
        .add_prefix("causa_")
    )
    causas.columns = [c.strip().lower().replace(" ", "_") for c in causas.columns]
    out = out.merge(causas.reset_index(), on=GROUP_COLS, how="left")

    return out.sort_values(GROUP_COLS).reset_index(drop=True)
