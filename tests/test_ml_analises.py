import pandas as pd

from ml.analises import disparidade_regional, mix_causas, persistencia_risco, sazonalidade_nacional


def _linha(municipio, nome, uf, regiao, ano, mes, n_eventos_total, n_eventos_validos, consumidores, fec_aprox, **causas):
    linha = {
        "codigo_ibge_resolvido": municipio,
        "nome_municipio": nome,
        "uf_sigla": uf,
        "regiao": regiao,
        "ano": ano,
        "mes": mes,
        "n_eventos_total": n_eventos_total,
        "n_eventos_validos": n_eventos_validos,
        "consumidores_ativos_max": consumidores,
        "fec_aprox": fec_aprox,
        "causa_interna": 0,
        "causa_interno": 0,
        "causa_externa": 0,
    }
    linha.update(causas)
    return linha


def _painel_sintetico() -> pd.DataFrame:
    linhas = [
        # municipio A (Norte): risco alto e persistente (fec_aprox sempre alto)
        _linha("1100015", "Municipio A", "RO", "Norte", 2024, 1, 100, 90, 1000, 0.09, causa_interna=80, causa_externa=10),
        _linha("1100015", "Municipio A", "RO", "Norte", 2024, 2, 110, 95, 1000, 0.095, causa_interna=85, causa_externa=10),
        # municipio B (Sudeste): risco baixo e persistente (fec_aprox sempre baixo)
        _linha("3550308", "Municipio B", "SP", "Sudeste", 2024, 1, 20, 18, 5000, 0.0036, causa_interna=16, causa_externa=2),
        _linha("3550308", "Municipio B", "SP", "Sudeste", 2024, 2, 22, 19, 5000, 0.0038, causa_interna=17, causa_externa=2),
    ]
    return pd.DataFrame(linhas)


def test_sazonalidade_agrega_por_ano_mes():
    resultado = sazonalidade_nacional(_painel_sintetico())
    assert resultado == [
        {"ano": 2024, "mes": 1, "n_eventos_total": 120.0},
        {"ano": 2024, "mes": 2, "n_eventos_total": 132.0},
    ]


def test_disparidade_regional_normaliza_por_consumidor():
    resultado = disparidade_regional(_painel_sintetico())
    por_regiao = {linha["regiao"]: linha for linha in resultado}

    # Norte: (100+110) eventos / (1000+1000) consumidores (soma dos 2 meses) * 1000 / 2 periodos = 52.5
    assert por_regiao["Norte"]["eventos_por_1000_consumidores_mes"] == 52.5
    # Sudeste: (20+22) eventos / (5000+5000) consumidores * 1000 / 2 periodos = 2.1
    assert por_regiao["Sudeste"]["eventos_por_1000_consumidores_mes"] == 2.1
    # Norte tem taxa por consumidor muito maior que Sudeste, mesmo com menos eventos brutos
    assert por_regiao["Norte"]["eventos_por_1000_consumidores_mes"] > por_regiao["Sudeste"]["eventos_por_1000_consumidores_mes"]
    assert por_regiao["Norte"]["n_eventos_total"] < por_regiao["Sudeste"]["n_eventos_total"] * 6  # so garante que nao inverteu por engano


def test_mix_causas_calcula_percentual_generico():
    resultado = mix_causas(_painel_sintetico())
    # total validos = 90+95+18+19 = 222; genericas (causa_interna+causa_interno) = 80+85+16+17 = 198
    assert resultado["percentual_causa_generica"] == round(198 / 222 * 100, 1)
    assert resultado["top_causas"][0]["causa"] == "interna"


def test_persistencia_correlacao_positiva_quando_risco_e_estavel():
    resultado = persistencia_risco(_painel_sintetico(), tamanho_amostra=10)
    # municipio A sempre alto, municipio B sempre baixo -- correlacao mes a mes deve ser bem positiva
    assert resultado["correlacao_mes_a_mes"] > 0.9
    assert len(resultado["amostra_dispersao"]) == 2  # 2 municipios x 1 par (mes1->mes2) cada
