import pandas as pd

from ml.features import construir_dataset, divisao_temporal, filtrar_utilizaveis


def _linha(municipio, ano, mes, fec, n_validos=10, consumidores=1000, causa_interna=8, causa_arvore=2, uf="RO", regiao="Norte", n_distribuidoras=1):
    return {
        "codigo_ibge_resolvido": municipio,
        "nome_municipio": f"Municipio {municipio}",
        "uf_sigla": uf,
        "regiao": regiao,
        "ano": ano,
        "mes": mes,
        "n_eventos_total": n_validos,
        "n_eventos_validos": n_validos,
        "consumidores_ativos_max": consumidores,
        "n_distribuidoras": n_distribuidoras,
        "causa_interna": causa_interna,
        "causa_interna/nao_programada/meio_ambiente/arvore_ou_vegetacao": causa_arvore,
        "fec_aprox": fec,
    }


def _painel_sintetico() -> pd.DataFrame:
    """Um municipio com meses seguidos de historico atravessando a virada
    de ano (fec crescente, facil de conferir manualmente) e um segundo
    municipio sem correspondencia de nome (deve ser excluido)."""
    linhas = [
        _linha("1100015", 2024, 1, fec=0.01),
        _linha("1100015", 2024, 2, fec=0.02),
        _linha("1100015", 2024, 12, fec=0.03),
        _linha("1100015", 2025, 1, fec=0.04),
    ]
    df = pd.DataFrame(linhas)
    sem_nome = _linha("CONJUNTO_X", 2024, 1, fec=0.5)
    sem_nome["nome_municipio"] = None
    sem_nome["uf_sigla"] = None
    sem_nome["regiao"] = None
    df = pd.concat([df, pd.DataFrame([sem_nome])], ignore_index=True)
    return df


def test_lag_1_e_o_proprio_mes_atual_nao_o_mes_anterior():
    """lag_1 precisa ser o fec_aprox do PROPRIO mes t (a linha atual) --
    porque o alvo e o mes t+1, entao "1 mes antes do alvo" e o mes t. Um bug
    anterior usava shift(1) aqui, o que fazia lag_1 apontar 2 meses antes do
    alvo em vez de 1 -- pego ao comparar contra o baseline do Dia 3 (ver
    docs/DEVLOG.md, Dia 4)."""
    dataset = construir_dataset(_painel_sintetico())
    linha_fev = dataset[(dataset["codigo_ibge_resolvido"] == "1100015") & (dataset["mes"] == 2) & (dataset["ano"] == 2024)].iloc[0]
    assert linha_fev["lag_1"] == 0.02  # o proprio fev/2024, nao jan/2024
    assert linha_fev["lag_2"] == 0.01  # jan/2024 (1 mes antes de lag_1)


def test_alvo_e_o_mes_seguinte():
    dataset = construir_dataset(_painel_sintetico())
    linha_jan = dataset[(dataset["codigo_ibge_resolvido"] == "1100015") & (dataset["mes"] == 1) & (dataset["ano"] == 2024)].iloc[0]
    assert linha_jan["alvo"] == 0.02  # fev/2024


def test_ultimo_mes_do_historico_fica_sem_alvo():
    dataset = construir_dataset(_painel_sintetico())
    linha_2025 = dataset[(dataset["codigo_ibge_resolvido"] == "1100015") & (dataset["ano"] == 2025)].iloc[0]
    assert pd.isna(linha_2025["alvo"])


def test_municipio_sem_nome_e_excluido():
    dataset = construir_dataset(_painel_sintetico())
    assert "CONJUNTO_X" not in dataset["codigo_ibge_resolvido"].values


def test_filtrar_utilizaveis_mantem_primeiro_mes_do_historico():
    """Como lag_1 agora e shift(0), o primeiro mes de historico de um
    municipio TEM lag_1 valido (e o proprio mes) -- so falta alvo no
    ULTIMO mes. filtrar_utilizaveis deve manter o primeiro mes."""
    dataset = construir_dataset(_painel_sintetico())
    utilizaveis = filtrar_utilizaveis(dataset)
    primeiro_mes = utilizaveis[(utilizaveis["codigo_ibge_resolvido"] == "1100015") & (utilizaveis["ano"] == 2024) & (utilizaveis["mes"] == 1)]
    assert len(primeiro_mes) == 1


def test_divisao_temporal_corta_por_ano_do_alvo_nao_do_mes_atual():
    """dez/2024 tem alvo = jan/2025 -- precisa cair no TESTE, mesmo o
    proprio mes "atual" da linha sendo 2024. E fev/2024 (que no fixture tem
    um buraco depois -- o proximo dado real e so dez/2024) precisa ficar
    SEM alvo (marco/2024 nao existe) e sumir de treino/teste, nao herdar
    por engano o valor de dez/2024 como se fossem meses vizinhos."""
    dataset = construir_dataset(_painel_sintetico())
    treino, teste = divisao_temporal(dataset, ano_corte=2025)

    linha_dez_2024 = teste[(teste["ano"] == 2024) & (teste["mes"] == 12)]
    assert len(linha_dez_2024) == 1
    assert linha_dez_2024.iloc[0]["alvo"] == 0.04  # jan/2025

    # fev/2024 nao pode aparecer em treino nem teste -- o alvo dela (mar/2024)
    # nao existe no dado real, e nao devia ser "preenchido" com dez/2024.
    assert treino[(treino["ano"] == 2024) & (treino["mes"] == 2)].empty
    assert teste[(teste["ano"] == 2024) & (teste["mes"] == 2)].empty

    assert ((treino["periodo"] + 1).dt.year < 2025).all()
    assert ((teste["periodo"] + 1).dt.year == 2025).all()


def test_causa_generica_e_ambiental_somam_no_maximo_o_total_de_validos():
    dataset = construir_dataset(_painel_sintetico())
    linha = dataset[(dataset["codigo_ibge_resolvido"] == "1100015") & (dataset["ano"] == 2024) & (dataset["mes"] == 1)].iloc[0]
    # 8 causa_interna + 2 causa_arvore, sobre 10 validos
    assert round(linha["prop_causa_generica_lag_1"], 2) == 0.8
    assert round(linha["prop_causa_ambiental_lag_1"], 2) == 0.2
