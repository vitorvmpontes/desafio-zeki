"""API do Continua -- indicadores históricos, ranking de risco previsto e a
explicação por trás de cada previsão (ver `api/README.md` e
`docs/REQUISITOS.md`).

Rodar localmente: `uvicorn api.main:app --reload` (com `DATABASE_URL`
apontando para um Postgres já carregado via `python -m etl.load_db`) --
documentação interativa em `/docs`.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api import servico
from api.database import carregar_painel, criar_engine
from api.schemas import (
    HistoricoResponse,
    MapaResponse,
    MunicipioResumo,
    PrevisaoResponse,
    PriorizacaoResponse,
    RankingResponse,
)
from api.servico import EstadoAplicacao


def criar_app(estado_inicial: EstadoAplicacao | None = None) -> FastAPI:
    """Fábrica de app -- permite injetar um `EstadoAplicacao` pronto nos
    testes (`tests/test_api.py`), sem depender de um Postgres real."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if estado_inicial is not None:
            app.state.estado = estado_inicial
        else:
            engine = criar_engine()
            painel = carregar_painel(engine)
            app.state.estado = servico.montar_estado(painel)
        yield

    app = FastAPI(
        title="Continua API",
        description=(
            "Indicadores de continuidade de energia por município, ranking de "
            "risco previsto para o mês seguinte e a explicação por trás de cada "
            "previsão -- dados reais da ANEEL. Ver docs/REQUISITOS.md e ml/README.md."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # o frontend (web/) roda numa origem diferente da API (portas/hosts
    # distintos -- ex.: localhost:3000 vs localhost:8000), e o navegador
    # bloqueia isso por padrao (CORS). Como esta API só expõe dados
    # públicos e de leitura (sem autenticação, sem escrita), liberar
    # qualquer origem é uma escolha pragmática para este desafio -- um
    # deploy real restringiria a origens conhecidas.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    def get_estado(request: Request) -> EstadoAplicacao:
        return request.app.state.estado

    @app.get("/", include_in_schema=False)
    def raiz():
        return {"servico": "Continua API", "docs": "/docs"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/municipios", response_model=list[MunicipioResumo])
    def municipios(
        request: Request,
        busca: str | None = Query(None, description="filtro por nome do municipio (contem, case-insensitive)"),
        limite: int = Query(200, ge=1, le=6000),
    ):
        estado = get_estado(request)
        return servico.listar_municipios(estado, busca, limite)

    @app.get("/municipios/{codigo_ibge}/historico", response_model=HistoricoResponse)
    def historico(request: Request, codigo_ibge: str):
        estado = get_estado(request)
        resultado = servico.historico_municipio(estado, codigo_ibge)
        if resultado is None:
            raise HTTPException(status_code=404, detail=f"Municipio '{codigo_ibge}' nao encontrado.")
        return resultado

    @app.get("/municipios/{codigo_ibge}/previsao", response_model=PrevisaoResponse)
    def previsao(request: Request, codigo_ibge: str):
        estado = get_estado(request)
        resultado = servico.previsao_municipio(estado, codigo_ibge)
        if resultado is None:
            raise HTTPException(status_code=404, detail=f"Municipio '{codigo_ibge}' nao encontrado.")
        return resultado

    @app.get("/ranking", response_model=RankingResponse)
    def ranking(
        request: Request,
        ano: int | None = Query(None, description="se informado junto com mes, retorna o ranking HISTORICO observado desse periodo"),
        mes: int | None = Query(None, ge=1, le=12),
        limite: int = Query(50, ge=1, le=6000),
    ):
        estado = get_estado(request)
        if (ano is None) != (mes is None):
            raise HTTPException(status_code=400, detail="Informe 'ano' e 'mes' juntos, ou nenhum dos dois (ranking previsto).")
        if ano is not None and mes is not None:
            return servico.ranking_historico(estado, ano, mes, limite)
        return servico.ranking_previsto(estado, limite)

    @app.get("/priorizacao", response_model=PriorizacaoResponse)
    def priorizacao(
        request: Request,
        limite: int = Query(20, ge=1, le=500, description="quantos municipios entram no ranking por impacto"),
    ):
        estado = get_estado(request)
        return servico.priorizacao(estado, limite)

    @app.get("/mapa", response_model=MapaResponse)
    def mapa(request: Request):
        estado = get_estado(request)
        return servico.mapa_clusters(estado)

    @app.get(
        "/mapa/kml",
        responses={200: {"content": {"application/vnd.google-earth.kml+xml": {}}}},
    )
    def mapa_kml(request: Request):
        estado = get_estado(request)
        kml = servico.mapa_kml(estado)
        return Response(content=kml, media_type="application/vnd.google-earth.kml+xml")

    return app


app = criar_app()
