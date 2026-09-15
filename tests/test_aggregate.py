from etl.aggregate import aggregate_municipio_mes
from etl.clean import clean_interrupcoes
from etl.config import COL_MUNICIPIO_IBGE


def _agregado(raw_df, referencia):
    limpo = clean_interrupcoes(raw_df, referencia=referencia)
    return aggregate_municipio_mes(limpo, codigo_municipio_col=COL_MUNICIPIO_IBGE)


def test_mesmo_municipio_com_codigo_de_6_e_7_digitos_nao_duplica_linha(raw_df, referencia):
    """Ariquemes/RO aparece com codigo de 7 digitos em janeiro/2025 (INT0001,
    INT0002) e de 6 digitos em fevereiro/2025 (INT0003) -- sao meses
    diferentes, entao devem virar DUAS linhas (um municipio, dois meses),
    nunca ficar espalhado em municipios "diferentes" por causa do codigo."""
    agregado = _agregado(raw_df, referencia)
    ariquemes = agregado[agregado["nome_municipio"] == "Ariquemes"]
    assert set(ariquemes["mes"]) == {1, 2}
    assert ariquemes["codigo_ibge_resolvido"].nunique() == 1


def test_expurgados_nao_entram_na_duracao_mas_sao_contados(raw_df, referencia):
    agregado = _agregado(raw_df, referencia)
    ariquemes_fev = agregado[(agregado["nome_municipio"] == "Ariquemes") & (agregado["mes"] == 2)].iloc[0]
    # INT0003 (valido, 1h15) e INT0004 (expurgado, nao entra na duracao)
    assert ariquemes_fev["n_eventos_total"] == 2
    assert ariquemes_fev["n_eventos_expurgados"] == 1
    assert ariquemes_fev["n_eventos_validos"] == 1
    assert round(ariquemes_fev["duracao_total_horas"], 2) == 1.25


def test_registro_com_duracao_invalida_nao_entra_na_soma_mas_conta_como_evento(raw_df, referencia):
    agregado = _agregado(raw_df, referencia)
    sp_fev = agregado[(agregado["nome_municipio"] == "São Paulo") & (agregado["mes"] == 2)].iloc[0]
    # INT0007 (duracao 0, valida) e INT0008 (fim antes do inicio, invalida)
    assert sp_fev["n_eventos_total"] == 2
    assert sp_fev["n_eventos_validos"] == 1


def test_fec_e_dec_aproximados_sao_calculados(raw_df, referencia):
    agregado = _agregado(raw_df, referencia)
    ariquemes_jan = agregado[(agregado["nome_municipio"] == "Ariquemes") & (agregado["mes"] == 1)].iloc[0]
    assert ariquemes_jan["fec_aprox"] > 0
    assert ariquemes_jan["dec_aprox_horas"] > 0


def test_municipio_sem_correspondencia_ibge_fica_em_grupo_proprio_nao_e_descartado(raw_df, referencia):
    agregado = _agregado(raw_df, referencia)
    sem_uf = agregado[agregado["uf_sigla"].isna()]
    assert len(sem_uf) == 2  # janeiro e fevereiro do municipio 9999999
    assert sem_uf["codigo_ibge_resolvido"].nunique() == 1


def test_mix_de_causas_conta_eventos_validos_por_origem(raw_df, referencia):
    agregado = _agregado(raw_df, referencia)
    ariquemes_jan = agregado[(agregado["nome_municipio"] == "Ariquemes") & (agregado["mes"] == 1)].iloc[0]
    # INT0001 = EXTERNO, INT0002 = INTERNO -- uma ocorrencia de cada
    assert ariquemes_jan["causa_externo"] == 1
    assert ariquemes_jan["causa_interno"] == 1
