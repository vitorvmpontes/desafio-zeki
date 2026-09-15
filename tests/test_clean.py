import pandas as pd

from etl.clean import clean_interrupcoes


def test_calcula_duracao_em_horas(raw_df, referencia):
    df = clean_interrupcoes(raw_df, referencia=referencia)
    evento = df[df["CodInterrupcao"] == "INT0001"].iloc[0]
    # 01/01 10:00 -> 01/01 12:30 = 2h30 = 2.5h
    assert evento["duracao_horas"] == 2.5
    assert evento["duracao_valida"]


def test_duracao_invalida_quando_fim_antes_do_inicio(raw_df, referencia):
    df = clean_interrupcoes(raw_df, referencia=referencia)
    evento = df[df["CodInterrupcao"] == "INT0008"].iloc[0]
    assert not evento["duracao_valida"]


def test_duracao_invalida_quando_datas_ausentes(raw_df, referencia):
    df = clean_interrupcoes(raw_df, referencia=referencia)
    evento = df[df["CodInterrupcao"] == "INT0010"].iloc[0]
    assert not evento["duracao_valida"]
    assert pd.isna(evento["duracao_horas"])


def test_registro_expurgado_e_sinalizado_mas_mantido(raw_df, referencia):
    df = clean_interrupcoes(raw_df, referencia=referencia)
    assert len(df) == len(raw_df)  # nada foi descartado
    evento = df[df["CodInterrupcao"] == "INT0004"].iloc[0]
    assert evento["expurgado"]

    nao_expurgado = df[df["CodInterrupcao"] == "INT0001"].iloc[0]
    assert not nao_expurgado["expurgado"]


def test_join_ibge_resolve_municipio_com_7_digitos(raw_df, referencia):
    df = clean_interrupcoes(raw_df, referencia=referencia)
    evento = df[df["CodInterrupcao"] == "INT0001"].iloc[0]
    assert evento["nome_municipio"] == "Ariquemes"
    assert evento["uf_sigla"] == "RO"


def test_join_ibge_resolve_municipio_com_6_digitos_para_o_mesmo_codigo_canonico(raw_df, referencia):
    """INT0001 usa o codigo de 7 digitos (1100023) e INT0003 usa o de 6
    (110002) para o mesmo municipio (Ariquemes/RO) -- ambos devem resolver
    para o MESMO codigo_ibge_resolvido, senao a agregacao os trata como
    municipios diferentes."""
    df = clean_interrupcoes(raw_df, referencia=referencia)
    cod_7 = df[df["CodInterrupcao"] == "INT0001"].iloc[0]["codigo_ibge_resolvido"]
    cod_6 = df[df["CodInterrupcao"] == "INT0003"].iloc[0]["codigo_ibge_resolvido"]
    assert cod_7 == cod_6 == "1100023"


def test_join_ibge_sem_correspondencia_mantem_registro(raw_df, referencia):
    df = clean_interrupcoes(raw_df, referencia=referencia)
    eventos = df[df["CodMunicipioIBGE"] == "9999999"]
    assert len(eventos) == 2  # nao descartou
    assert eventos["uf_sigla"].isna().all()
    # mantem o codigo bruto como identificador quando nao ha match
    assert (eventos["codigo_ibge_resolvido"] == "9999999").all()
