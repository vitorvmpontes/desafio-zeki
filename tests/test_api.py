"""Testes de integracao dos endpoints da API.

Em vez de depender de um Postgres rodando (o CI nao tem um, ver
docs/DEVLOG.md sobre a escolha de nao acoplar os testes automatizados a
infra externa), os testes montam o `EstadoAplicacao` diretamente a partir
de um painel sintetico em memoria (`servico.montar_estado`), pulando
`api/database.py` -- mas usando o modelo REAL (`ml/artifacts/modelo_final.joblib`)
e a importancia REAL (`ml/artifacts/importancia_features.json`) ja
commitados no repositorio, entao o caminho de previsao/interpretabilidade e
exercitado de verdade, so o Postgres que e' trocado.

A validacao contra um Postgres de verdade (via docker compose / instancia
local) foi feita manualmente -- ver docs/DEVLOG.md, Dia 5.
"""
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api import chat_sql, servico
from api.main import criar_app

_URL_READONLY_TESTE = "postgresql://continua_readonly:continua_readonly@localhost:5432/continua"


def _postgres_readonly_acessivel() -> bool:
    try:
        with create_engine(_URL_READONLY_TESTE).connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _linha(municipio, ano, mes, fec, nome=None, uf="RO", regiao="Norte", consumidores=1000, duracao_total_horas=6.0):
    return {
        "codigo_ibge_resolvido": municipio,
        "nome_municipio": nome or f"Municipio {municipio}",
        "uf_sigla": uf,
        "regiao": regiao,
        "ano": ano,
        "mes": mes,
        "n_eventos_total": 12,
        "n_eventos_validos": 12,
        "consumidores_ativos_max": consumidores,
        "n_distribuidoras": 1,
        "causa_interna": 11,
        "causa_interna/nao_programada/meio_ambiente/arvore_ou_vegetacao": 1,
        "fec_aprox": fec,
        "duracao_total_horas": duracao_total_horas,
        "dec_aprox_horas": duracao_total_horas / consumidores,
    }


def _painel_sintetico() -> pd.DataFrame:
    """Dois municipios com 24 meses de historico (2024-01 a 2025-12),
    espelhando o formato real (municipio x mes) -- suficiente para
    construir_dataset/o modelo final rodarem de ponta a ponta."""
    linhas = []
    periodos = [(ano, mes) for ano in (2024, 2025) for mes in range(1, 13)]
    for i, (ano, mes) in enumerate(periodos):
        fec = 0.01 + 0.001 * (i % 12)
        linhas.append(_linha("1100015", ano, mes, fec=fec, nome="Alta Floresta D'Oeste", uf="RO", regiao="Norte"))
        linhas.append(_linha("3550308", ano, mes, fec=fec * 2, nome="São Paulo", uf="SP", regiao="Sudeste", consumidores=50000))
    return pd.DataFrame(linhas)


@pytest.fixture(scope="module")
def client():
    estado = servico.montar_estado(_painel_sintetico())
    app = criar_app(estado_inicial=estado)
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_listar_municipios(client):
    r = client.get("/municipios")
    assert r.status_code == 200
    corpo = r.json()
    assert len(corpo) == 2
    codigos = {m["codigo_ibge"] for m in corpo}
    assert codigos == {"1100015", "3550308"}


def test_listar_municipios_filtra_por_busca(client):
    r = client.get("/municipios", params={"busca": "paulo"})
    assert r.status_code == 200
    corpo = r.json()
    assert len(corpo) == 1
    assert corpo[0]["nome"] == "São Paulo"


def test_historico_municipio(client):
    r = client.get("/municipios/1100015/historico")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["nome"] == "Alta Floresta D'Oeste"
    assert len(corpo["historico"]) == 24
    assert corpo["historico"][0]["ano"] == 2024
    assert corpo["historico"][0]["mes"] == 1


def test_historico_municipio_inexistente_da_404(client):
    r = client.get("/municipios/0000000/historico")
    assert r.status_code == 404


def test_previsao_municipio(client):
    r = client.get("/municipios/1100015/previsao")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["mes_alvo"] == "2026-01"
    assert isinstance(corpo["previsao_modelo"], float)
    assert isinstance(corpo["previsao_baseline"], float)
    # features usadas precisam bater com o que o modelo realmente usou
    assert set(corpo["features_utilizadas"].keys()) == {
        "lag_1", "lag_2", "lag_3", "media_movel_3", "media_movel_expandida",
        "mes_sin", "mes_cos", "log_consumidores", "log_n_eventos_lag_1",
        "prop_causa_generica_lag_1", "prop_causa_ambiental_lag_1", "n_distribuidoras_lag_1",
        "regiao", "uf_sigla",
    }
    assert len(corpo["importancia_features_modelo"]) == 14
    # a soma das causas dominantes tem que fechar em ~1 (sao proporcoes)
    causas = corpo["causas_dominantes_ultimos_12_meses"]
    assert abs(sum(causas.values()) - 1.0) < 0.01


def test_previsao_municipio_inexistente_da_404(client):
    r = client.get("/municipios/0000000/previsao")
    assert r.status_code == 404


def test_ranking_previsto_ordenado_desc(client):
    r = client.get("/ranking")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["modo"] == "previsto"
    assert corpo["total_municipios"] == 2
    riscos = [item["risco"] for item in corpo["itens"]]
    assert riscos == sorted(riscos, reverse=True)
    assert corpo["itens"][0]["posicao"] == 1


def test_ranking_historico_usa_fec_aprox_observado(client):
    r = client.get("/ranking", params={"ano": 2025, "mes": 6})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["modo"] == "historico"
    assert corpo["ano"] == 2025
    assert corpo["mes"] == 6
    for item in corpo["itens"]:
        assert item["fec_aprox_observado"] is not None
        assert item["previsao_modelo"] is None


def test_ranking_exige_ano_e_mes_juntos(client):
    r = client.get("/ranking", params={"ano": 2025})
    assert r.status_code == 400


def test_priorizacao_ranking_por_impacto(client):
    r = client.get("/priorizacao", params={"limite": 2})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["mes_alvo"] == "2026-01"
    assert corpo["total_municipios"] == 2
    assert len(corpo["ranking_impacto"]) == 2

    # Sao Paulo tem risco por consumidor MAIOR (fec = 2x) E muito mais
    # consumidores (50000 vs 1000) -- entao domina tanto o ranking por taxa
    # quanto o ranking por impacto real neste caso sintetico.
    item = corpo["ranking_impacto"][0]
    assert item["codigo_ibge"] == "3550308"
    # impacto_esperado e previsao_modelo sao arredondados separadamente para
    # exibicao (5 e 2 casas decimais) -- o produto reconstruido bate so
    # aproximadamente, nao exatamente.
    assert item["impacto_esperado"] == pytest.approx(item["previsao_modelo"] * item["consumidores_ativos_estimados"], rel=1e-3)

    # so ~8% dos eventos sinteticos sao ambientais (1 de 12) -- abaixo do
    # limiar de media confianca (15%), entao esse sinal continua exposto no
    # campo (causa_dominante/percentual), mas nao e' ele quem decide a
    # confianca -- quem decide agora e' o padrao frequencia x duracao (ver
    # ml/priorizacao.py::recomendar_acao), que sempre tem algo a dizer
    # porque fec_aprox/dec_aprox_horas existem pros 2 municipios.
    por_municipio = {item["codigo_ibge"]: item for item in corpo["ranking_impacto"]}
    for item in corpo["ranking_impacto"]:
        assert item["confianca_recomendacao"] == "alta"
        assert item["causa_dominante"] == "ambiental"
        assert item["percentual_causa_dominante"] == pytest.approx(1 / 12 * 100, rel=1e-2)

    # Sao Paulo: fec_aprox 2x maior que Alta Floresta -- domina em frequencia,
    # nao em duracao (dec_aprox_horas e' MENOR, por ter 50x mais consumidores
    # no denominador). Alta Floresta e' o oposto: domina em duracao.
    assert por_municipio["3550308"]["padrao_operacional"] == "frequencia_dominante"
    assert por_municipio["1100015"]["padrao_operacional"] == "duracao_dominante"


def test_priorizacao_traz_tendencia_e_calendario(client):
    r = client.get("/priorizacao")
    assert r.status_code == 200
    corpo = r.json()
    assert isinstance(corpo["tendencia_piorando"], list)
    assert isinstance(corpo["tendencia_melhorando"], list)
    assert len(corpo["calendario_sazonal"]["pontos"]) == 24
    assert all(1 <= m <= 12 for m in corpo["calendario_sazonal"]["meses_criticos"])
    assert corpo["nota_metodologica"]


def test_priorizacao_limite_e_respeitado(client):
    r = client.get("/priorizacao", params={"limite": 1})
    assert r.status_code == 200
    assert len(r.json()["ranking_impacto"]) == 1


def test_priorizacao_traz_desempenho_geografico(client):
    r = client.get("/priorizacao")
    assert r.status_code == 200
    corpo = r.json()["desempenho_geografico"]
    assert corpo["janela_meses"] == 12
    assert len(corpo["hotspots"]) == 2  # so 2 municipios no painel sintetico
    for item in corpo["hotspots"]:
        assert item["fec_aprox_medio"] > 0
        assert item["dec_aprox_horas_medio"] >= 0
        assert 0 <= item["indice_hotspot"] <= 100
    assert {r["regiao"] for r in corpo["mttr_por_regiao"]} == {"Norte", "Sudeste"}
    assert corpo["nota_metodologica"]


def test_mapa_traz_clusters_com_coordenadas(client):
    r = client.get("/mapa")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["janela_meses"] == 12
    assert corpo["n_municipios_no_mapa"] == 2  # so 2 municipios no painel sintetico, ambos com coordenada real
    assert len(corpo["municipios"]) == 2
    assert corpo["kml_url"] == "/mapa/kml"
    assert corpo["nota_metodologica"]
    for item in corpo["municipios"]:
        assert -35 < item["latitude"] < 6  # faixa aproximada do territorio brasileiro
        assert -75 < item["longitude"] < -30
        assert item["severidade"]
    # Sao Paulo tem fec_aprox/dec_aprox_horas medios maiores (fec = 2x, ver
    # _painel_sintetico) -- tem que ficar no cluster pior (primeiro da lista
    # de severidade, ja que so ha 2 municipios/2 clusters).
    por_municipio = {m["codigo_ibge"]: m for m in corpo["municipios"]}
    assert por_municipio["3550308"]["fec_aprox_medio"] > por_municipio["1100015"]["fec_aprox_medio"]


def test_mapa_kml_serve_arquivo_kml_valido(client):
    r = client.get("/mapa/kml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.google-earth.kml+xml")
    assert r.text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert r.text.count("<Placemark>") == 2


# --------------------------------------------------------------------------
# /chat -- chatbot text-to-SQL (api/chat_sql.py). `gerar_sql` (a chamada de
# rede ao Gemini) e' sempre mockada aqui: o que este endpoint precisa
# garantir e' o roteamento HTTP certo (503/422/200) a partir do que
# `chat_sql`/`servico.responder_chat` decidem, nao o texto que o Gemini
# devolveria de verdade -- isso fica para a primeira execucao real na
# maquina do usuario (ver docs/DEVLOG.md).
# --------------------------------------------------------------------------


def test_chat_sem_engine_leitura_configurada_da_503(client):
    """O fixture `client` (topo do arquivo) monta o app sem `engine_leitura`
    -- mesmo estado de uma instalacao sem DATABASE_URL_READONLY no .env."""
    r = client.post("/chat", json={"pergunta": "quantos municipios existem?"})
    assert r.status_code == 503
    assert "DATABASE_URL_READONLY" in r.json()["detail"]


@pytest.fixture(scope="module")
def client_com_chat():
    if not _postgres_readonly_acessivel():
        pytest.skip(
            "Postgres local com o role 'continua_readonly' indisponivel (rode "
            "db/readonly_role.sql, ver docs/DEVLOG.md) -- testes de /chat com "
            "banco real pulados, sem acoplar o CI a infraestrutura externa."
        )
    estado = servico.montar_estado(_painel_sintetico())
    engine_leitura = create_engine(_URL_READONLY_TESTE)
    app = criar_app(estado_inicial=estado, engine_leitura=engine_leitura)
    with TestClient(app) as c:
        yield c


def test_chat_com_sql_valido_executa_e_retorna_dados_reais(client_com_chat, monkeypatch):
    sql_fake = "SELECT codigo_ibge_resolvido, nome_municipio FROM municipio_mes WHERE codigo_ibge_resolvido = '1100015' LIMIT 3"
    monkeypatch.setattr(chat_sql, "gerar_sql", lambda pergunta: sql_fake)

    r = client_com_chat.post("/chat", json={"pergunta": "me mostre o municipio 1100015"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["pergunta"] == "me mostre o municipio 1100015"
    assert corpo["colunas"] == ["codigo_ibge_resolvido", "nome_municipio"]
    assert corpo["total_linhas"] == len(corpo["linhas"])
    assert 0 < corpo["total_linhas"] <= 3
    assert all(linha["codigo_ibge_resolvido"] == "1100015" for linha in corpo["linhas"])
    assert corpo["aviso"] is None


def test_chat_com_sql_invalido_gerado_pelo_modelo_da_422(client_com_chat, monkeypatch):
    """O modelo "alucinou" uma consulta perigosa -- confirma que o endpoint
    devolve 422 (pedido nao pode ser atendido com seguranca), nao um 500
    generico nem, pior, executa a consulta."""
    monkeypatch.setattr(chat_sql, "gerar_sql", lambda pergunta: "DROP TABLE municipio_mes")

    r = client_com_chat.post("/chat", json={"pergunta": "apague a tabela"})
    assert r.status_code == 422


def test_chat_pergunta_vazia_e_rejeitada_pelo_schema(client):
    r = client.post("/chat", json={"pergunta": ""})
    assert r.status_code == 422  # validacao do Pydantic (min_length=1), nem chega em servico.responder_chat
