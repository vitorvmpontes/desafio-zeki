"""Modelos de resposta (Pydantic) da API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MunicipioResumo(BaseModel):
    codigo_ibge: str
    nome: str
    uf: str
    regiao: str
    consumidores_ativos_estimados: float | None = Field(
        None, description="consumidores_ativos_max do mes mais recente disponivel"
    )


class HistoricoPonto(BaseModel):
    ano: int
    mes: int
    fec_aprox: float | None
    n_eventos_validos: float | None
    consumidores_ativos_max: float | None


class HistoricoResponse(BaseModel):
    codigo_ibge: str
    nome: str
    uf: str
    regiao: str
    historico: list[HistoricoPonto]


class ImportanciaFeature(BaseModel):
    feature: str
    importancia_relativa: float
    aumento_mae_medio: float


class PrevisaoResponse(BaseModel):
    codigo_ibge: str
    nome: str
    uf: str
    regiao: str
    mes_alvo: str = Field(..., description="mes que a previsao se refere, formato AAAA-MM")

    previsao_modelo: float = Field(..., description="fec_aprox previsto pelo gradient boosting (ml/artifacts/modelo_final.joblib)")
    previsao_baseline: float | None = Field(
        None, description="fec_aprox previsto pelo baseline oficial do Dia 3 (persistencia t-1 + t-12), exposto como referencia"
    )
    baseline_persistencia_t1: float | None = None
    baseline_persistencia_t12: float | None = None

    features_utilizadas: dict[str, float | str | None] = Field(
        ..., description="valores de entrada usados pelo modelo para esta previsao especifica"
    )
    causas_dominantes_ultimos_12_meses: dict[str, float] = Field(
        ..., description="proporcao de eventos validos por causa agregada, nos ultimos meses observados do municipio"
    )
    importancia_features_modelo: list[ImportanciaFeature] = Field(
        ..., description="importancia GLOBAL por permutacao do modelo (nao especifica deste municipio) -- ver ml/interpretabilidade.py"
    )
    nota_metodologica: str


class RankingItem(BaseModel):
    posicao: int
    codigo_ibge: str
    nome: str
    uf: str
    regiao: str
    risco: float = Field(..., description="valor usado para ordenar o ranking (fec_aprox previsto ou observado, conforme o modo)")
    previsao_modelo: float | None = None
    previsao_baseline: float | None = None
    fec_aprox_observado: float | None = None


class RankingResponse(BaseModel):
    modo: str = Field(..., description="'previsto' (ranking do proximo mes, pelo modelo) ou 'historico' (ano/mes observado)")
    ano: int
    mes: int
    total_municipios: int
    itens: list[RankingItem]


class ItemPriorizacao(BaseModel):
    posicao: int
    codigo_ibge: str
    nome: str
    uf: str
    regiao: str
    previsao_modelo: float = Field(..., description="fec_aprox previsto para o mes_alvo (mesmo valor de /ranking)")
    consumidores_ativos_estimados: float | None
    impacto_esperado: float = Field(
        ..., description="previsao_modelo x consumidores_ativos_estimados -- proxy de interrupcoes-consumidor esperadas no mes seguinte, nao so a taxa por consumidor"
    )
    acao_recomendada: str = Field(
        ...,
        description=(
            "acao concreta a partir do padrao de frequencia (fec_aprox) x duracao (dec_aprox_horas) do "
            "municipio comparado ao percentil nacional dos ultimos 12 meses -- disponivel para 100% dos "
            "municipios; a causa reportada pela distribuidora, quando existir, aparece como evidencia adicional "
            "no texto"
        ),
    )
    confianca_recomendacao: str = Field(
        ..., description="'alta' | 'media' | 'baixa', conforme a clareza do padrao frequencia/duracao (reforcada por causa reportada, se houver), ou 'sem_dado'"
    )
    padrao_operacional: str = Field(
        ...,
        description=(
            "'critico_ambos' | 'frequencia_dominante' | 'duracao_dominante' | 'atencao_moderada' | "
            "'dentro_do_padrao' | 'sem_dado'"
        ),
    )
    percentil_frequencia: float | None = Field(None, description="percentil nacional (0-100) de fec_aprox medio do municipio nos ultimos 12 meses")
    percentil_duracao: float | None = Field(None, description="percentil nacional (0-100) de dec_aprox_horas medio do municipio nos ultimos 12 meses")
    causa_dominante: str | None = Field(None, description="'ambiental' | 'equipamento' | 'terceiros' | 'operacional', se houver uma dominante com algum sinal (evidencia adicional, nao mais a base da recomendacao)")
    percentual_causa_dominante: float | None = None


class TendenciaItem(BaseModel):
    codigo_ibge: str
    nome: str
    uf: str
    regiao: str
    variacao_pct: float = Field(..., description="variacao % entre a media de fec_aprox dos ultimos 3 meses e a dos 3 meses anteriores")
    fec_aprox_medio_recente: float
    fec_aprox_medio_anterior: float


class CalendarioSazonalPonto(BaseModel):
    ano: int
    mes: int
    n_eventos_total: float = Field(..., description="soma nacional de eventos (ja ponderada pelo fan-out de etl/ibge.py)")


class CalendarioSazonal(BaseModel):
    pontos: list[CalendarioSazonalPonto]
    meses_criticos: list[int] = Field(..., description="meses do calendario (1-12) com maior media historica de eventos")
    recomendacao: str


class HotspotItem(BaseModel):
    codigo_ibge: str
    nome: str
    uf: str
    regiao: str
    fec_aprox_medio: float = Field(..., description="media de fec_aprox (frequencia por consumidor) na janela")
    dec_aprox_horas_medio: float = Field(..., description="media de dec_aprox_horas (duracao por consumidor) na janela")
    n_eventos_validos: float = Field(..., description="soma de eventos validos na janela, contexto (nao usado para ordenar)")
    mttr_horas: float | None = Field(None, description="duracao_total_horas / n_eventos_validos -- horas por evento, nao por consumidor")
    indice_hotspot: float = Field(..., description="media dos percentis de fec_aprox_medio e dec_aprox_horas_medio (0-100)")


class MttrRegional(BaseModel):
    regiao: str
    n_eventos_validos: float
    duracao_total_horas: float
    mttr_horas: float | None = Field(None, description="duracao_total_horas / n_eventos_validos na regiao, na janela")


class DesempenhoGeografico(BaseModel):
    janela_meses: int = Field(..., description="quantos meses mais recentes do calendario global entram no calculo")
    hotspots: list[HotspotItem] = Field(..., description="municipios com pior fec_aprox E dec_aprox_horas medios simultaneamente")
    mttr_por_regiao: list[MttrRegional]
    nota_metodologica: str


class MapaMunicipio(BaseModel):
    codigo_ibge: str
    nome: str
    uf: str
    regiao: str
    latitude: float
    longitude: float
    fec_aprox_medio: float = Field(..., description="media de fec_aprox (frequencia por consumidor) na janela")
    dec_aprox_horas_medio: float = Field(..., description="media de dec_aprox_horas (duracao por consumidor) na janela")
    severidade: str = Field(
        ..., description="'critico' | 'alto' | 'moderado' | 'baixo' -- atribuido pela severidade real do centroide do cluster, nao pelo id arbitrario do KMeans"
    )


class MapaClusterResumo(BaseModel):
    severidade: str
    n_municipios: int
    fec_aprox_medio: float
    dec_aprox_horas_medio: float


class MapaResponse(BaseModel):
    janela_meses: int
    n_clusters: int
    n_municipios_no_mapa: int
    municipios: list[MapaMunicipio]
    resumo_por_cluster: list[MapaClusterResumo]
    kml_url: str = Field(..., description="endpoint que serve o arquivo KML real (application/vnd.google-earth.kml+xml)")
    nota_metodologica: str


class ChatRequest(BaseModel):
    pergunta: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="pergunta em portugues sobre os dados de municipio_mes (ex.: 'quais os 5 municipios com maior fec_aprox em 2025?')",
    )


class ChatResponse(BaseModel):
    pergunta: str
    sql_gerado: str = Field(
        ..., description="consulta SQL gerada pelo modelo e validada (LIMIT garantido) -- a mesma que foi de fato executada"
    )
    colunas: list[str]
    linhas: list[dict[str, Any]]
    total_linhas: int
    aviso: str | None = Field(None, description="ex.: aviso de truncamento pelo limite maximo de linhas de seguranca")


class PriorizacaoResponse(BaseModel):
    mes_alvo: str = Field(..., description="mes que a previsao de impacto se refere, formato AAAA-MM")
    total_municipios: int
    ranking_impacto: list[ItemPriorizacao] = Field(..., description="top N municipios por impacto_esperado (nao por taxa isolada)")
    tendencia_piorando: list[TendenciaItem]
    tendencia_melhorando: list[TendenciaItem]
    calendario_sazonal: CalendarioSazonal
    desempenho_geografico: DesempenhoGeografico
    nota_metodologica: str
