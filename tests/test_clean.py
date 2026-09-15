import pandas as pd

from etl.clean import clean_interrupcoes, normalizar_causa


def test_calcula_duracao_em_horas(raw_df, referencia, bridge):
    df = clean_interrupcoes(raw_df, referencia=referencia, bridge=bridge)
    evento = df[df["NumOrdemInterrupcao"] == "INT0001"].iloc[0]
    # 01/01 10:00 -> 01/01 12:30 = 2h30 = 2.5h
    assert evento["duracao_horas"] == 2.5
    assert evento["duracao_valida"]


def test_duracao_invalida_quando_fim_antes_do_inicio(raw_df, referencia, bridge):
    df = clean_interrupcoes(raw_df, referencia=referencia, bridge=bridge)
    evento = df[df["NumOrdemInterrupcao"] == "INT0008"].iloc[0]
    assert not evento["duracao_valida"]


def test_duracao_invalida_e_ano_mes_ausentes_quando_datas_ausentes(raw_df, referencia, bridge):
    df = clean_interrupcoes(raw_df, referencia=referencia, bridge=bridge)
    evento = df[df["NumOrdemInterrupcao"] == "INT0010"].iloc[0]
    assert not evento["duracao_valida"]
    assert pd.isna(evento["duracao_horas"])
    # ano/mes sao derivados de DatInicioInterrupcao -- sem data, ficam nulos
    # (nao existe AnoCompetencia/MesCompetencia no schema real).
    assert pd.isna(evento["ano"])
    assert pd.isna(evento["mes"])


def test_interrupcao_programada_e_sinalizada_mas_mantida(raw_df, referencia, bridge):
    """Nao existe campo equivalente a DscMotivoExpurgo no schema real -- o
    filtro analogo disponivel e DscTipoInterrupcao (Programada / Nao
    Programada), ver docs/DEVLOG.md."""
    df = clean_interrupcoes(raw_df, referencia=referencia, bridge=bridge)
    assert df["NumOrdemInterrupcao"].nunique() == len(raw_df)  # nenhum evento foi descartado

    programado = df[df["NumOrdemInterrupcao"] == "INT0004"].iloc[0]
    assert programado["programada"]

    nao_programado = df[df["NumOrdemInterrupcao"] == "INT0001"].iloc[0]
    assert not nao_programado["programada"]


def test_motivo_interrupcao_e_mantido_bruto_sem_decodificar(raw_df, referencia, bridge):
    df = clean_interrupcoes(raw_df, referencia=referencia, bridge=bridge)
    evento = df[df["NumOrdemInterrupcao"] == "INT0006"].iloc[0]
    assert evento["motivo_interrupcao_codigo"] == "1"


def test_sigagente_com_espacos_e_normalizado(raw_df, referencia, bridge):
    """SigAgente vem com espacos em branco a direita nos dados reais (ex:
    'EAC                 ') -- sem strip, a mesma distribuidora contaria
    como duas diferentes."""
    df = clean_interrupcoes(raw_df, referencia=referencia, bridge=bridge)
    evento = df[df["NumOrdemInterrupcao"] == "INT0002"].iloc[0]
    assert evento["SigAgente"] == "DIST_A"


def test_normalizar_causa_unifica_separadores_e_acentuacao():
    serie = pd.Series(
        [
            "INTERNA;NAO PROGRAMADA;PROPRIAS DO SISTEMA;FALHA DE MATERIAL OU EQUIPAMENTO",
            "Interna-Não programada-Próprias do sistema-Falha de material ou equipamento",
        ]
    )
    resultado = normalizar_causa(serie)
    assert resultado["causa_normalizada"].nunique() == 1
    assert resultado["causa_origem"].tolist() == ["INTERNA", "INTERNA"]


def test_join_conjunto_resolve_municipio_unico(raw_df, referencia, bridge):
    df = clean_interrupcoes(raw_df, referencia=referencia, bridge=bridge)
    evento = df[df["NumOrdemInterrupcao"] == "INT0001"].iloc[0]
    assert evento["nome_municipio"] == "Ariquemes"
    assert evento["uf_sigla"] == "RO"
    assert evento["n_municipios_no_conjunto"] == 1
    assert evento["peso_evento"] == 1.0


def test_join_conjunto_com_mais_de_um_municipio_faz_fanout(raw_df, referencia, bridge):
    """CJ02 atende dois municipios (Sao Paulo e Guarulhos) -- um evento
    nesse conjunto deve virar DUAS linhas, uma por municipio, cada uma com
    peso_evento = 1/2, para nao inflar o total nacional de eventos."""
    df = clean_interrupcoes(raw_df, referencia=referencia, bridge=bridge)
    eventos = df[df["NumOrdemInterrupcao"] == "INT0005"]
    assert len(eventos) == 2
    assert set(eventos["nome_municipio"]) == {"São Paulo", "Guarulhos"}
    assert (eventos["uf_sigla"] == "SP").all()
    assert (eventos["n_municipios_no_conjunto"] == 2).all()
    assert (eventos["peso_evento"] == 0.5).all()


def test_join_conjunto_sem_correspondencia_mantem_registro(raw_df, referencia, bridge):
    df = clean_interrupcoes(raw_df, referencia=referencia, bridge=bridge)
    eventos = df[df["DscConjuntoUnidadeConsumidora"] == "Conjunto Desconhecido"]
    assert len(eventos) == 2  # INT0009 e INT0010, nao descartados
    assert eventos["uf_sigla"].isna().all()
    assert (eventos["codigo_ibge_resolvido"] == "CONJUNTO_CJ03").all()
    assert (eventos["n_municipios_no_conjunto"] == 1).all()
    assert (eventos["peso_evento"] == 1.0).all()
