import pandas as pd
import pytest

from etl.aggregate import aggregate_conjunto_mes, aggregate_municipio_mes, combine_conjunto_mes
from etl.clean import clean_interrupcoes


def _agregado(raw_df, referencia, bridge):
    limpo = clean_interrupcoes(raw_df)
    conjunto_mes, causa_cols = aggregate_conjunto_mes(limpo)
    return aggregate_municipio_mes(conjunto_mes, causa_cols, bridge=bridge, referencia=referencia)


def test_fanout_nao_infla_o_total_nacional_de_eventos(raw_df, referencia, bridge):
    """O total de n_eventos_total (ponderado por peso_evento, aplicado no
    nivel conjunto x mes -- ver etl.aggregate) somado sobre TODOS os grupos
    deve continuar batendo com o numero de eventos distintos de entrada --
    o fan-out para conjuntos compartilhados entre municipios (CJ02) nao
    pode inflar o total nacional so porque o mesmo conjunto aparece em mais
    de uma linha."""
    agregado = _agregado(raw_df, referencia, bridge)
    assert agregado["n_eventos_total"].sum() == pytest.approx(len(raw_df))


def test_conjunto_compartilhado_divide_peso_igualmente_entre_municipios(raw_df, referencia, bridge):
    """CJ02 atende Sao Paulo e Guarulhos -- os eventos de janeiro/2025 desse
    conjunto devem aparecer com os MESMOS numeros (ponderados por 0.5) nos
    dois municipios, nao duplicados nem atribuidos a um so."""
    agregado = _agregado(raw_df, referencia, bridge)
    sp_jan = agregado[(agregado["nome_municipio"] == "São Paulo") & (agregado["mes"] == 1)].iloc[0]
    guarulhos_jan = agregado[(agregado["nome_municipio"] == "Guarulhos") & (agregado["mes"] == 1)].iloc[0]

    assert sp_jan["n_eventos_total"] == pytest.approx(1.0)
    assert guarulhos_jan["n_eventos_total"] == pytest.approx(1.0)
    assert sp_jan["consumidores_ativos_max"] == pytest.approx(guarulhos_jan["consumidores_ativos_max"])
    assert sp_jan["consumidores_afetados_total"] == pytest.approx(guarulhos_jan["consumidores_afetados_total"])
    assert sp_jan["causa_externa"] == pytest.approx(0.5)
    assert sp_jan["causa_interna"] == pytest.approx(0.5)


def test_interrupcao_programada_nao_entra_na_duracao_mas_e_contada(raw_df, referencia, bridge):
    agregado = _agregado(raw_df, referencia, bridge)
    ariquemes_fev = agregado[(agregado["nome_municipio"] == "Ariquemes") & (agregado["mes"] == 2)].iloc[0]
    # INT0003 (valido, 1h15) e INT0004 (programada, nao entra na duracao)
    assert ariquemes_fev["n_eventos_total"] == pytest.approx(2)
    assert ariquemes_fev["n_eventos_programados"] == pytest.approx(1)
    assert ariquemes_fev["n_eventos_validos"] == pytest.approx(1)
    assert round(ariquemes_fev["duracao_total_horas"], 2) == 1.25


def test_registro_com_duracao_invalida_nao_entra_na_soma_mas_conta_como_evento(raw_df, referencia, bridge):
    agregado = _agregado(raw_df, referencia, bridge)
    sp_fev = agregado[(agregado["nome_municipio"] == "São Paulo") & (agregado["mes"] == 2)].iloc[0]
    # copia (peso 0.5) de INT0007 (duracao 0, valida) e INT0008 (fim antes do inicio, invalida)
    assert sp_fev["n_eventos_total"] == pytest.approx(1.0)
    assert sp_fev["n_eventos_validos"] == pytest.approx(0.5)


def test_fec_e_dec_aproximados_sao_calculados(raw_df, referencia, bridge):
    agregado = _agregado(raw_df, referencia, bridge)
    ariquemes_jan = agregado[(agregado["nome_municipio"] == "Ariquemes") & (agregado["mes"] == 1)].iloc[0]
    assert ariquemes_jan["fec_aprox"] > 0
    assert ariquemes_jan["dec_aprox_horas"] > 0


def test_conjunto_sem_correspondencia_fica_em_grupo_proprio_nao_e_descartado(raw_df, referencia, bridge):
    agregado = _agregado(raw_df, referencia, bridge)
    sem_uf = agregado[agregado["uf_sigla"].isna()]
    # INT0009 (janeiro) e INT0010 (data ausente, ano/mes tambem NaN) --
    # ficam em dois grupos distintos (chaves de ano/mes diferentes), mas
    # ambos com o MESMO codigo_ibge_resolvido "CONJUNTO_CJ03" -- nao sao
    # descartados nem confundidos com outro conjunto desconhecido.
    assert len(sem_uf) == 2
    assert sem_uf["codigo_ibge_resolvido"].nunique() == 1
    assert (sem_uf["codigo_ibge_resolvido"] == "CONJUNTO_CJ03").all()


def test_mix_de_causas_conta_eventos_validos_por_origem(raw_df, referencia, bridge):
    agregado = _agregado(raw_df, referencia, bridge)
    ariquemes_jan = agregado[(agregado["nome_municipio"] == "Ariquemes") & (agregado["mes"] == 1)].iloc[0]
    # INT0001 = EXTERNA, INT0002 = INTERNA -- uma ocorrencia de cada
    assert ariquemes_jan["causa_externa"] == pytest.approx(1)
    assert ariquemes_jan["causa_interna"] == pytest.approx(1)


def test_processar_em_lotes_da_o_mesmo_resultado_que_de_uma_vez(raw_df, referencia, bridge):
    """`etl.pipeline` le o Parquet real em lotes (nunca os ~19 milhoes de
    eventos de uma vez -- ver docs/DEVLOG.md) e usa `combine_conjunto_mes`
    para juntar os resultados parciais. Isso so e seguro se o resultado
    combinado for IDENTICO a agregar tudo de uma vez -- em particular
    quando o mesmo conjunto x mes cai espalhado em lotes diferentes (o
    Parquet nao vem ordenado por conjunto)."""
    limpo = clean_interrupcoes(raw_df)

    # separa os eventos em dois "lotes" que misturam conjuntos e meses,
    # como um corte arbitrario de linhas do Parquet faria na pratica.
    lote_a = limpo.iloc[::2].reset_index(drop=True)
    lote_b = limpo.iloc[1::2].reset_index(drop=True)
    assert len(lote_a) > 0 and len(lote_b) > 0

    parte_a, _ = aggregate_conjunto_mes(lote_a)
    parte_b, _ = aggregate_conjunto_mes(lote_b)
    conjunto_mes_lotes, causa_cols_lotes = combine_conjunto_mes([parte_a, parte_b])
    agregado_em_lotes = aggregate_municipio_mes(conjunto_mes_lotes, causa_cols_lotes, bridge=bridge, referencia=referencia)

    conjunto_mes_direto, causa_cols_direto = aggregate_conjunto_mes(limpo)
    agregado_direto = aggregate_municipio_mes(conjunto_mes_direto, causa_cols_direto, bridge=bridge, referencia=referencia)

    colunas_numericas = [
        c
        for c in agregado_direto.columns
        if c not in ("codigo_ibge_resolvido", "nome_municipio", "uf_sigla", "regiao", "ano", "mes")
    ]
    pd.testing.assert_frame_equal(
        agregado_em_lotes.sort_values(["codigo_ibge_resolvido", "ano", "mes"]).reset_index(drop=True)[colunas_numericas],
        agregado_direto.sort_values(["codigo_ibge_resolvido", "ano", "mes"]).reset_index(drop=True)[colunas_numericas],
        check_dtype=False,
    )
