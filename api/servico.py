"""Estado da aplicação e lógica de negócio dos endpoints.

Tudo é montado UMA VEZ na inicialização (`montar_estado`) a partir do
Postgres + dos artefatos do modelo (Dia 4) -- ver `api/database.py` para a
justificativa de manter o painel inteiro em memória em vez de uma query por
requisição. Um refresh exigiria reiniciar a API (ou um endpoint de reload,
fora do escopo por ora) -- aceitável porque o dado só muda com a automação
mensal (Dia 7), não em tempo real (ver `docs/DEVLOG.md`, Dia 5).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd

from api import chat_sql, config
from ml.baseline import prever_baseline
from ml.features import FEATURES_CATEGORICAS, FEATURES_NUMERICAS, TARGET, construir_dataset
from ml.mapa import mapa_clusters_kml
from ml.modelos import prever_gbm
from ml.priorizacao import (
    adicionar_impacto_esperado,
    calendario_sazonal,
    desempenho_geografico,
    padrao_frequencia_duracao,
    ranking_por_impacto,
    tendencia_top,
)

COL_ID = "codigo_ibge_resolvido"

CAUSA_COLS_AMBIENTAL_MARCADOR = "meio_ambiente"
CAUSA_COLS_GENERICAS = ("causa_interna", "causa_interno")


def _num(valor) -> float | None:
    """Converte um escalar pandas/numpy para float nativo, ou None se NaN --
    Pydantic/JSON não aceitam NaN como número."""
    if valor is None:
        return None
    if isinstance(valor, (int, float, np.integer, np.floating)):
        return None if pd.isna(valor) else float(valor)
    return valor


@dataclass
class EstadoAplicacao:
    painel: pd.DataFrame
    dataset: pd.DataFrame
    modelo: object
    modelo_metadata: dict
    importancia_features: dict
    previsao: pd.DataFrame  # 1 linha por municipio: previsao do modelo + baseline p/ o proximo mes, ja com impacto_esperado
    municipios: pd.DataFrame  # info cadastral mais recente por municipio
    tendencia: dict  # top N piorando/melhorando pre-computado (ml/priorizacao.py) -- nao depende do "limite" da requisicao
    calendario_sazonal: dict  # calendario sazonal pre-computado (ml/priorizacao.py) -- idem
    desempenho_geografico: dict  # hotspots por municipio + MTTR por regiao pre-computado (ml/priorizacao.py) -- idem
    padrao_operacional: pd.DataFrame  # percentil nacional de frequencia/duracao por municipio, pre-computado (ml/priorizacao.py::padrao_frequencia_duracao) -- base da acao recomendada de /priorizacao
    mapa_geografico: dict  # clusters de qualidade de servico + KML pre-computado (ml/mapa.py) -- idem


def _municipios_info(painel: pd.DataFrame) -> pd.DataFrame:
    df = painel.dropna(subset=["nome_municipio"]).copy()
    df = df.sort_values([COL_ID, "ano", "mes"])
    ultimo = df.groupby(COL_ID, as_index=False).tail(1)
    return ultimo[[COL_ID, "nome_municipio", "uf_sigla", "regiao", "consumidores_ativos_max"]].reset_index(drop=True)


def montar_estado(painel: pd.DataFrame) -> EstadoAplicacao:
    dataset = construir_dataset(painel)

    modelo = joblib.load(config.MODELO_PATH)
    with open(config.MODELO_METADATA_PATH, encoding="utf-8") as f:
        modelo_metadata = json.load(f)
    with open(config.IMPORTANCIA_FEATURES_PATH, encoding="utf-8") as f:
        importancia_features = json.load(f)

    # a ultima linha (maior periodo) de cada municipio no dataset tem
    # features calculadas com todo o historico conhecido ate ali -- e'
    # exatamente a linha para prever o mes seguinte (por isso fica sem
    # "alvo": ninguem observou esse mes ainda). Ver ml/features.py.
    ultimas_linhas = (
        dataset.sort_values([COL_ID, "periodo"]).groupby(COL_ID, as_index=False).tail(1).reset_index(drop=True)
    )
    ultimas_linhas["previsao_modelo"] = prever_gbm(modelo, ultimas_linhas)
    ultimas_linhas["periodo_alvo"] = ultimas_linhas["periodo"] + 1

    baseline = prever_baseline(painel).drop(columns=["periodo_alvo"])
    previsao = ultimas_linhas.merge(baseline, on=COL_ID, how="left", validate="one_to_one")
    previsao = adicionar_impacto_esperado(previsao)

    municipios = _municipios_info(painel)
    tendencia = tendencia_top(painel, municipios)
    calendario = calendario_sazonal(painel)
    geografico = desempenho_geografico(painel)
    padrao_operacional = padrao_frequencia_duracao(painel)
    mapa = mapa_clusters_kml(painel)

    return EstadoAplicacao(
        painel=painel,
        dataset=dataset,
        modelo=modelo,
        modelo_metadata=modelo_metadata,
        importancia_features=importancia_features,
        previsao=previsao,
        municipios=municipios,
        tendencia=tendencia,
        calendario_sazonal=calendario,
        desempenho_geografico=geografico,
        padrao_operacional=padrao_operacional,
        mapa_geografico=mapa,
    )


# --------------------------------------------------------------------------
# /municipios
# --------------------------------------------------------------------------
def listar_municipios(estado: EstadoAplicacao, busca: str | None, limite: int) -> list[dict]:
    df = estado.municipios
    if busca:
        df = df[df["nome_municipio"].str.contains(busca, case=False, na=False)]
    df = df.sort_values("nome_municipio").head(limite)
    return [
        {
            "codigo_ibge": row[COL_ID],
            "nome": row["nome_municipio"],
            "uf": row["uf_sigla"],
            "regiao": row["regiao"],
            "consumidores_ativos_estimados": _num(row["consumidores_ativos_max"]),
        }
        for row in df.to_dict(orient="records")
    ]


# --------------------------------------------------------------------------
# /municipios/{codigo}/historico
# --------------------------------------------------------------------------
def historico_municipio(estado: EstadoAplicacao, codigo_ibge: str) -> dict | None:
    info = estado.municipios[estado.municipios[COL_ID] == codigo_ibge]
    if info.empty:
        return None
    info = info.iloc[0]

    serie = estado.painel[estado.painel[COL_ID] == codigo_ibge].sort_values(["ano", "mes"])
    pontos = [
        {
            "ano": int(row["ano"]),
            "mes": int(row["mes"]),
            "fec_aprox": _num(row["fec_aprox"]),
            "n_eventos_validos": _num(row["n_eventos_validos"]),
            "consumidores_ativos_max": _num(row["consumidores_ativos_max"]),
        }
        for row in serie.to_dict(orient="records")
    ]
    return {
        "codigo_ibge": codigo_ibge,
        "nome": info["nome_municipio"],
        "uf": info["uf_sigla"],
        "regiao": info["regiao"],
        "historico": pontos,
    }


# --------------------------------------------------------------------------
# /municipios/{codigo}/previsao
# --------------------------------------------------------------------------
def _causas_dominantes(painel_municipio: pd.DataFrame, ultimos_n_meses: int = 12) -> dict[str, float]:
    """Proporção de eventos válidos por causa agregada (mesma agregação
    grosseira de `ml/features.py`: genérica vs. ambiental vs. resto), nos
    últimos meses observados do município -- ~95% dos eventos reais só têm
    causa genérica (ver EDA do Dia 3), então essa é a granularidade honesta
    disponível, não as ~46 colunas originais."""
    df = painel_municipio.sort_values(["ano", "mes"]).tail(ultimos_n_meses)
    causa_cols = [c for c in df.columns if c.startswith("causa_")]
    generica_cols = [c for c in causa_cols if c in CAUSA_COLS_GENERICAS]
    ambiental_cols = [c for c in causa_cols if CAUSA_COLS_AMBIENTAL_MARCADOR in c]

    total_validos = df["n_eventos_validos"].sum()
    if not total_validos or pd.isna(total_validos) or total_validos <= 0:
        return {}

    generica = df[generica_cols].sum().sum() if generica_cols else 0.0
    ambiental = df[ambiental_cols].sum().sum() if ambiental_cols else 0.0
    resto = max(total_validos - generica - ambiental, 0.0)

    return {
        "generica_sem_detalhe": round(float(generica / total_validos), 4),
        "ambiental": round(float(ambiental / total_validos), 4),
        "outras_causas_detalhadas": round(float(resto / total_validos), 4),
    }


def previsao_municipio(estado: EstadoAplicacao, codigo_ibge: str) -> dict | None:
    info = estado.municipios[estado.municipios[COL_ID] == codigo_ibge]
    linha_previsao = estado.previsao[estado.previsao[COL_ID] == codigo_ibge]
    if info.empty or linha_previsao.empty:
        return None
    info = info.iloc[0]
    prev = linha_previsao.iloc[0]

    features_utilizadas = {}
    for feature in FEATURES_NUMERICAS + FEATURES_CATEGORICAS:
        features_utilizadas[feature] = _num(prev[feature]) if feature in FEATURES_NUMERICAS else prev[feature]

    causas = _causas_dominantes(estado.painel[estado.painel[COL_ID] == codigo_ibge])

    return {
        "codigo_ibge": codigo_ibge,
        "nome": info["nome_municipio"],
        "uf": info["uf_sigla"],
        "regiao": info["regiao"],
        "mes_alvo": str(prev["periodo_alvo"]),
        "previsao_modelo": _num(prev["previsao_modelo"]),
        "previsao_baseline": _num(prev["baseline_previsto"]),
        "baseline_persistencia_t1": _num(prev["baseline_t1"]),
        "baseline_persistencia_t12": _num(prev["baseline_t12"]),
        "features_utilizadas": features_utilizadas,
        "causas_dominantes_ultimos_12_meses": causas,
        "importancia_features_modelo": estado.importancia_features["importancias"],
        "nota_metodologica": (
            "previsao_modelo vem do gradient boosting treinado com todo o historico "
            "disponivel (ml/artifacts/modelo_final.joblib); previsao_baseline e a "
            "media da persistencia do mes anterior com a persistencia do mesmo mes "
            "no ano anterior (baseline oficial do Dia 3), mantida como referencia "
            "porque supera o modelo na precisao do top 10% de risco na validacao "
            "do Dia 4 (ver docs/REQUISITOS.md). importancia_features_modelo e GLOBAL "
            "(do modelo validado por corte temporal), nao especifica deste municipio."
        ),
    }


# --------------------------------------------------------------------------
# /ranking
# --------------------------------------------------------------------------
def ranking_previsto(estado: EstadoAplicacao, limite: int) -> dict:
    # estado.previsao ja tem nome_municipio/regiao/uf_sigla (vem do dataset
    # de features, que carrega essas colunas -- ver ml/features.py,
    # COLUNAS_SAIDA) -- nao precisa (e nao deve) mesclar com
    # estado.municipios de novo, isso so duplicaria as colunas.
    df = estado.previsao.sort_values("previsao_modelo", ascending=False).head(limite).reset_index(drop=True)

    mes_alvo = df["periodo_alvo"].iloc[0] if len(df) else None
    itens = [
        {
            "posicao": i + 1,
            "codigo_ibge": row[COL_ID],
            "nome": row["nome_municipio"],
            "uf": row["uf_sigla"],
            "regiao": row["regiao"],
            "risco": _num(row["previsao_modelo"]),
            "previsao_modelo": _num(row["previsao_modelo"]),
            "previsao_baseline": _num(row["baseline_previsto"]),
            "fec_aprox_observado": None,
        }
        for i, row in enumerate(df.to_dict(orient="records"))
    ]
    return {
        "modo": "previsto",
        "ano": mes_alvo.year if mes_alvo is not None else None,
        "mes": mes_alvo.month if mes_alvo is not None else None,
        "total_municipios": len(estado.previsao),
        "itens": itens,
    }


def ranking_historico(estado: EstadoAplicacao, ano: int, mes: int, limite: int) -> dict:
    df = estado.painel[
        (estado.painel["ano"] == ano) & (estado.painel["mes"] == mes) & estado.painel["nome_municipio"].notna()
    ].copy()
    df = df.sort_values(TARGET, ascending=False).head(limite).reset_index(drop=True)

    itens = [
        {
            "posicao": i + 1,
            "codigo_ibge": row[COL_ID],
            "nome": row["nome_municipio"],
            "uf": row["uf_sigla"],
            "regiao": row["regiao"],
            "risco": _num(row[TARGET]),
            "previsao_modelo": None,
            "previsao_baseline": None,
            "fec_aprox_observado": _num(row[TARGET]),
        }
        for i, row in enumerate(df.to_dict(orient="records"))
    ]
    total = int(
        (
            (estado.painel["ano"] == ano) & (estado.painel["mes"] == mes) & estado.painel["nome_municipio"].notna()
        ).sum()
    )
    return {"modo": "historico", "ano": ano, "mes": mes, "total_municipios": total, "itens": itens}


# --------------------------------------------------------------------------
# /priorizacao
# --------------------------------------------------------------------------
def priorizacao(estado: EstadoAplicacao, limite: int) -> dict:
    """Substitui `/analises` (ver `docs/DEVLOG.md`, pivot "Priorização"):
    ranking por impacto real (não só taxa por consumidor) + ação recomendada
    por município + tendência piorando/melhorando + calendário sazonal +
    desempenho geográfico (hotspots + MTTR regional).

    O ranking por impacto e a ação recomendada são calculados a cada
    requisição, limitados ao `limite` pedido (ver `ml/priorizacao.py`,
    `ranking_por_impacto`) -- mas o percentil nacional de frequência/duração
    que sustenta a ação (`estado.padrao_operacional`) e o mix de causas por
    município (`causas_taxonomia_acionavel`) tem custo pra recalcular, então
    só vale a pena fazer o lookup/agregação para quem entra na lista, não
    para os ~5500 municípios. Tendência, calendário sazonal, desempenho
    geográfico e o próprio `padrao_operacional` não dependem de `limite` e
    já vêm pré-computados de `montar_estado`."""
    mes_alvo = estado.previsao["periodo_alvo"].iloc[0] if len(estado.previsao) else None
    return {
        "mes_alvo": str(mes_alvo) if mes_alvo is not None else None,
        "total_municipios": len(estado.previsao),
        "ranking_impacto": ranking_por_impacto(estado.previsao, estado.painel, estado.padrao_operacional, limite),
        "tendencia_piorando": estado.tendencia["piorando"],
        "tendencia_melhorando": estado.tendencia["melhorando"],
        "calendario_sazonal": estado.calendario_sazonal,
        "desempenho_geografico": estado.desempenho_geografico,
        "nota_metodologica": (
            # Nota enxuta e restrita ao que so aparece aqui (impacto/acao) --
            # tendencia e desempenho_geografico tem nota_metodologica propria
            # (calendario_sazonal.recomendacao / desempenho_geografico.nota_metodologica),
            # repetir o resumo delas aqui so duplicava texto nas paginas que
            # ja mostram a versao completa (ver docs/DEVLOG.md, "reorganizacao
            # em paginas + tema escuro", pedido do usuario para reduzir texto).
            "impacto_esperado = previsao_modelo (gradient boosting) x consumidores_ativos_estimados -- prioriza "
            "por impacto absoluto, nao so pela taxa de risco por consumidor (ver /ranking). acao_recomendada "
            "compara o percentil nacional de frequencia (fec_aprox) e duracao (dec_aprox_horas) do municipio nos "
            "ultimos 12 meses -- disponivel para 100% dos municipios, ao contrario da causa reportada pela "
            "distribuidora (~95% dos eventos so tem causa generica, ver docs/DEVLOG.md, Dia 3): nenhum dos "
            "municipios do topo do ranking por impacto tinha causa detalhada, entao a recomendacao anterior, "
            "baseada so em causa, virava o mesmo texto generico repetido nas linhas que mais importam. A causa "
            "detalhada, quando existe, continua aparecendo na acao como evidencia adicional."
        ),
    }


# --------------------------------------------------------------------------
# /mapa e /mapa/kml
# --------------------------------------------------------------------------
def mapa_clusters(estado: EstadoAplicacao) -> dict:
    """Payload JSON do mapa (`GET /mapa`) -- clusters de qualidade de
    serviço por município (`ml/mapa.py`, pré-computado uma vez em
    `montar_estado`), pronto para o frontend desenhar os marcadores sem
    precisar parsear o KML. O arquivo KML de verdade continua disponível em
    `GET /mapa/kml` (`kml_url` abaixo) -- o mesmo dado, em formato GIS
    padrão, para quem quiser abrir num visualizador externo."""
    m = estado.mapa_geografico
    return {
        "janela_meses": m["janela_meses"],
        "n_clusters": m["n_clusters"],
        "n_municipios_no_mapa": m["n_municipios_no_mapa"],
        "municipios": m["municipios"],
        "resumo_por_cluster": m["resumo_por_cluster"],
        "kml_url": "/mapa/kml",
        "nota_metodologica": m["nota_metodologica"],
    }


def mapa_kml(estado: EstadoAplicacao) -> str:
    """XML do arquivo KML (`GET /mapa/kml`) -- mesmo cluster de
    `mapa_clusters`, servido no formato padrão OGC (`application/vnd.google-
    earth.kml+xml`, ver `api/main.py`)."""
    return estado.mapa_geografico["kml"]


# --------------------------------------------------------------------------
# /chat -- chatbot text-to-SQL (ver api/chat_sql.py para a validação/execução
# em si; esta função só orquestra: gera o SQL, executa, formata a resposta)
# --------------------------------------------------------------------------
def responder_chat(pergunta: str, engine_leitura) -> dict:
    """Traduz `pergunta` (português) em SQL via Gemini, valida e executa
    contra `engine_leitura` (role Postgres somente-leitura, ver
    `api/database.py::criar_engine_leitura`).

    Não depende de `EstadoAplicacao`/`estado.painel` -- o chat lê os mesmos
    dados, mas direto do Postgres via SQL gerado dinamicamente, não do
    DataFrame em memória que sustenta o resto da API (ver módulo
    `api/database.py` para a justificativa de manter dois caminhos de
    leitura separados: o painel em memória é rápido e fixo por reinicialização,
    o chat precisa de uma consulta nova por pergunta).

    `engine_leitura=None` (chat não configurado, ver `criar_engine_leitura`)
    e `chat_sql.SqlInvalidoError` (consulta gerada reprovada na validação)
    são erros esperados, tratados explicitamente aqui pra api/main.py devolver
    o HTTP status certo (503 vs. 422) em vez de um 500 genérico."""
    if engine_leitura is None:
        raise RuntimeError(
            "Chat não configurado: defina DATABASE_URL_READONLY no .env (rode db/readonly_role.sql "
            "uma vez contra o Postgres e veja .env.example para o formato da URL)."
        )

    sql_gerado = chat_sql.gerar_sql(pergunta)
    resultado = chat_sql.executar_sql_seguro(sql_gerado, engine_leitura)

    aviso = None
    if len(resultado.linhas) >= chat_sql.LIMITE_LINHAS_MAXIMO:
        aviso = f"Resultado truncado em {chat_sql.LIMITE_LINHAS_MAXIMO} linhas (limite máximo de segurança)."

    return {
        "pergunta": pergunta,
        "sql_gerado": resultado.sql,
        "colunas": resultado.colunas,
        "linhas": resultado.linhas,
        "total_linhas": len(resultado.linhas),
        "aviso": aviso,
    }
