import pandas as pd

from ml.priorizacao import (
    adicionar_impacto_esperado,
    calcular_tendencia,
    calendario_sazonal,
    causas_taxonomia_acionavel,
    hotspots_geograficos,
    mttr_por_regiao,
    recomendar_acao,
    tendencia_top,
)


def _linha(
    municipio, nome, uf, regiao, ano, mes, n_eventos_total, n_eventos_validos, consumidores, fec_aprox,
    duracao_total_horas=0.0, dec_aprox_horas=None, **causas,
):
    if dec_aprox_horas is None:
        dec_aprox_horas = duracao_total_horas / consumidores if consumidores else 0.0
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
        "duracao_total_horas": duracao_total_horas,
        "dec_aprox_horas": dec_aprox_horas,
        "causa_interna": 0,
        "causa_interno": 0,
        "causa_interna/nao_programada/meio_ambiente/arvore_ou_vegetacao": 0,
        "causa_interna/nao_programada/proprias_do_sistema/falha_de_material_ou_equipamento": 0,
        "causa_interna/nao_programada/terceiros/vandalismo": 0,
        "causa_interna/nao_programada/falha_operacional/erro_de_operacao": 0,
    }
    linha.update(causas)
    return linha


# --------------------------------------------------------------------------
# causas_taxonomia_acionavel / recomendar_acao
# --------------------------------------------------------------------------
def test_taxonomia_classifica_causa_ambiental_com_alta_confianca():
    painel = pd.DataFrame(
        [
            _linha(
                "1100015", "Municipio A", "RO", "Norte", 2025, 1, 100, 90, 1000, 0.09,
                **{"causa_interna/nao_programada/meio_ambiente/arvore_ou_vegetacao": 80, "causa_interna": 10},
            )
        ]
    )
    taxonomia = causas_taxonomia_acionavel(painel)
    assert taxonomia["ambiental"] == round(80 / 90, 4)
    assert taxonomia["generica_sem_detalhe"] == round(10 / 90, 4)

    acao = recomendar_acao(taxonomia)
    assert acao["confianca_recomendacao"] == "alta"
    assert acao["causa_dominante"] == "ambiental"
    assert "poda" in acao["acao_recomendada"].lower()


def test_recomenda_confianca_media_entre_15_e_40_por_cento():
    painel = pd.DataFrame(
        [
            _linha(
                "1100015", "Municipio A", "RO", "Norte", 2025, 1, 100, 100, 1000, 0.10,
                **{
                    "causa_interna/nao_programada/proprias_do_sistema/falha_de_material_ou_equipamento": 20,
                    "causa_interna": 80,
                },
            )
        ]
    )
    taxonomia = causas_taxonomia_acionavel(painel)
    acao = recomendar_acao(taxonomia)
    assert acao["confianca_recomendacao"] == "media"
    assert acao["causa_dominante"] == "equipamento"
    assert acao["percentual_causa_dominante"] == 20.0


def test_recomenda_confianca_baixa_quando_tudo_e_generico():
    painel = pd.DataFrame(
        [_linha("1100015", "Municipio A", "RO", "Norte", 2025, 1, 100, 100, 1000, 0.10, causa_interna=100)]
    )
    taxonomia = causas_taxonomia_acionavel(painel)
    acao = recomendar_acao(taxonomia)
    assert acao["confianca_recomendacao"] == "baixa"
    assert acao["causa_dominante"] is None
    assert "genérica" in acao["acao_recomendada"] or "generica" in acao["acao_recomendada"].lower()


def test_recomendar_acao_sem_eventos_validos():
    acao = recomendar_acao({})
    assert acao["confianca_recomendacao"] == "sem_dado"
    assert acao["causa_dominante"] is None


# --------------------------------------------------------------------------
# adicionar_impacto_esperado
# --------------------------------------------------------------------------
def test_impacto_esperado_multiplica_previsao_por_exposicao():
    previsao = pd.DataFrame(
        [
            {"codigo_ibge_resolvido": "A", "previsao_modelo": 0.10, "exposicao": 1000},
            {"codigo_ibge_resolvido": "B", "previsao_modelo": 0.01, "exposicao": 500000},
        ]
    )
    resultado = adicionar_impacto_esperado(previsao)
    assert resultado.set_index("codigo_ibge_resolvido")["impacto_esperado"]["A"] == 100.0
    assert resultado.set_index("codigo_ibge_resolvido")["impacto_esperado"]["B"] == 5000.0
    # municipio B tem risco por consumidor MENOR que A, mas impacto esperado MAIOR --
    # e exatamente essa inversao que o ranking por impacto real deve capturar.


# --------------------------------------------------------------------------
# calcular_tendencia
# --------------------------------------------------------------------------
def _painel_tendencia() -> pd.DataFrame:
    linhas = []
    # Municipio PIORA: 0.02 nos 3 primeiros meses, 0.06 nos 3 ultimos (variacao +200%)
    for mes, fec in zip(range(1, 7), [0.02, 0.02, 0.02, 0.06, 0.06, 0.06]):
        linhas.append(_linha("1100015", "Piora", "RO", "Norte", 2025, mes, 10, 10, 1000, fec))
    # Municipio MELHORA: 0.08 -> 0.02 (variacao -75%)
    for mes, fec in zip(range(1, 7), [0.08, 0.08, 0.08, 0.02, 0.02, 0.02]):
        linhas.append(_linha("3550308", "Melhora", "SP", "Sudeste", 2025, mes, 10, 10, 5000, fec))
    # Municipio com so 3 meses de historico -- nao deve entrar (janela incompleta)
    for mes, fec in zip(range(1, 4), [0.05, 0.05, 0.05]):
        linhas.append(_linha("2611606", "Curto", "PE", "Nordeste", 2025, mes, 10, 10, 2000, fec))
    # Municipio com buraco no meio dos ultimos 6 meses (pula o mes 4) -- nao deve entrar
    for mes, fec in zip([1, 2, 3, 5, 6, 7], [0.05] * 6):
        linhas.append(_linha("4106902", "ComBuraco", "PR", "Sul", 2025, mes, 10, 10, 3000, fec))
    return pd.DataFrame(linhas)


def test_calcula_tendencia_piora_e_melhora_e_exclui_dado_insuficiente():
    resultado = calcular_tendencia(_painel_tendencia())
    por_municipio = {row["codigo_ibge_resolvido"]: row for row in resultado.to_dict(orient="records")}

    assert "2611606" not in por_municipio  # historico curto demais
    assert "4106902" not in por_municipio  # buraco no meio da janela de 6 meses

    assert round(por_municipio["1100015"]["variacao_pct"], 6) == 200.0
    assert round(por_municipio["3550308"]["variacao_pct"], 6) == -75.0


def test_tendencia_top_lista_piorando_e_melhorando_separadamente():
    municipios_info = pd.DataFrame(
        [
            {"codigo_ibge_resolvido": "1100015", "nome_municipio": "Piora", "uf_sigla": "RO", "regiao": "Norte"},
            {"codigo_ibge_resolvido": "3550308", "nome_municipio": "Melhora", "uf_sigla": "SP", "regiao": "Sudeste"},
        ]
    )
    resultado = tendencia_top(_painel_tendencia(), municipios_info, top_n=5)
    assert resultado["piorando"][0]["codigo_ibge"] == "1100015"
    assert resultado["melhorando"][0]["codigo_ibge"] == "3550308"


# --------------------------------------------------------------------------
# calendario_sazonal
# --------------------------------------------------------------------------
def test_calendario_sazonal_aponta_meses_criticos():
    linhas = []
    # setembro (mes 9) sempre com volume muito maior que os outros meses, nos 2 anos
    for ano in (2024, 2025):
        for mes in range(1, 13):
            volume = 500 if mes == 9 else 50
            linhas.append(_linha("1100015", "Municipio A", "RO", "Norte", ano, mes, volume, volume, 1000, 0.01))
    resultado = calendario_sazonal(pd.DataFrame(linhas), top_n_meses=1)
    assert resultado["meses_criticos"] == [9]
    assert "setembro" in resultado["recomendacao"]
    assert len(resultado["pontos"]) == 24


# --------------------------------------------------------------------------
# hotspots_geograficos / mttr_por_regiao
# --------------------------------------------------------------------------
def _painel_hotspots() -> pd.DataFrame:
    linhas = []
    # HOTSPOT: alta frequencia E alta duracao POR CONSUMIDOR -- ruim nas duas dimensoes
    for mes in range(1, 13):
        linhas.append(
            _linha("1100015", "Hotspot", "RO", "Norte", 2025, mes, 100, 100, 1000, 0.1,
                   duracao_total_horas=50, dec_aprox_horas=5.0)
        )
    # SO_FREQUENTE: mesma frequencia do hotspot (fec_aprox igual), mas resolve rapido
    # (dec_aprox_horas baixo) -- e uma cidade grande, entao o volume BRUTO de eventos e
    # duracao seria enganoso (pareceria pior que o Hotspot em volume absoluto, mas nao e
    # pior em qualidade de servico por consumidor)
    for mes in range(1, 13):
        linhas.append(
            _linha("3550308", "SoFrequente", "SP", "Sudeste", 2025, mes, 100, 100, 50000, 0.1,
                   duracao_total_horas=5, dec_aprox_horas=0.1)
        )
    # BAIXO: baixa frequencia e baixa duracao por consumidor -- nao deveria aparecer no topo
    for mes in range(1, 13):
        linhas.append(
            _linha("2611606", "Baixo", "PE", "Nordeste", 2025, mes, 10, 10, 2000, 0.01,
                   duracao_total_horas=2, dec_aprox_horas=0.01)
        )
    return pd.DataFrame(linhas)


def test_hotspots_prioriza_municipio_ruim_nas_duas_dimensoes_normalizadas():
    resultado = hotspots_geograficos(_painel_hotspots(), ultimos_n_meses=12, top_n=3)
    assert resultado[0]["codigo_ibge"] == "1100015"
    assert resultado[0]["indice_hotspot"] > resultado[1]["indice_hotspot"]
    assert resultado[0]["indice_hotspot"] > resultado[2]["indice_hotspot"]
    # mttr = duracao total / eventos totais = (50*12) / (100*12) = 0.5h por evento
    assert resultado[0]["mttr_horas"] == 0.5


def test_hotspots_usa_metrica_normalizada_nao_volume_bruto():
    # SoFrequente e Hotspot tem o MESMO numero bruto de eventos por mes (100) -- um
    # indice baseado em volume bruto os trataria como igualmente ruins nessa dimensao.
    # Mas SoFrequente e uma cidade grande (50.000 consumidores) com boa duracao POR
    # CONSUMIDOR (dec_aprox_horas=0.1), bem menor que a de Hotspot (5.0) -- o indice
    # normalizado precisa refletir essa diferenca de qualidade de servico, nao só igualar
    # os dois por terem o mesmo volume bruto de eventos.
    resultado = hotspots_geograficos(_painel_hotspots(), ultimos_n_meses=12, top_n=3)
    por_municipio = {r["codigo_ibge"]: r for r in resultado}
    assert por_municipio["3550308"]["indice_hotspot"] < por_municipio["1100015"]["indice_hotspot"]


def test_hotspots_respeita_janela_de_meses_e_ignora_dado_antigo():
    linhas = [
        _linha("1100015", "Municipio A", "RO", "Norte", 2025, mes, 10, 10, 1000, 0.01, duracao_total_horas=1)
        for mes in range(1, 13)
    ]
    # evento de 2024, fora da janela dos ultimos 12 meses (calendario termina em 2025-12) -- nao deve entrar
    linhas.append(_linha("1100015", "Municipio A", "RO", "Norte", 2024, 12, 9999, 9999, 1000, 99, duracao_total_horas=9999))
    resultado = hotspots_geograficos(pd.DataFrame(linhas), ultimos_n_meses=12, top_n=1)
    assert resultado[0]["n_eventos_validos"] == 120  # 10 * 12, nao 9999 + 120


def test_mttr_por_regiao_agrega_duracao_sobre_eventos_nao_faz_media_simples():
    linhas = []
    for mes in range(1, 13):
        # Norte: 10 eventos/mes, 20h/mes -- 2h por evento
        linhas.append(_linha("1100015", "A", "RO", "Norte", 2025, mes, 10, 10, 1000, 0.01, duracao_total_horas=20))
        # Sudeste: 10 eventos/mes, 5h/mes -- 0.5h por evento
        linhas.append(_linha("3550308", "B", "SP", "Sudeste", 2025, mes, 10, 10, 50000, 0.0002, duracao_total_horas=5))
    resultado = mttr_por_regiao(pd.DataFrame(linhas), ultimos_n_meses=12)
    por_regiao = {r["regiao"]: r for r in resultado}
    assert por_regiao["Norte"]["mttr_horas"] == 2.0
    assert por_regiao["Sudeste"]["mttr_horas"] == 0.5
    assert resultado[0]["regiao"] == "Norte"  # ordenado desc por mttr_horas
