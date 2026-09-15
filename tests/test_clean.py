import pandas as pd

from etl.clean import clean_interrupcoes, normalizar_causa


def test_calcula_duracao_em_horas(raw_df):
    df = clean_interrupcoes(raw_df)
    evento = df[df["NumOrdemInterrupcao"] == "INT0001"].iloc[0]
    # 01/01 10:00 -> 01/01 12:30 = 2h30 = 2.5h
    assert evento["duracao_horas"] == 2.5
    assert evento["duracao_valida"]


def test_duracao_invalida_quando_fim_antes_do_inicio(raw_df):
    df = clean_interrupcoes(raw_df)
    evento = df[df["NumOrdemInterrupcao"] == "INT0008"].iloc[0]
    assert not evento["duracao_valida"]


def test_duracao_invalida_e_ano_mes_ausentes_quando_datas_ausentes(raw_df):
    df = clean_interrupcoes(raw_df)
    evento = df[df["NumOrdemInterrupcao"] == "INT0010"].iloc[0]
    assert not evento["duracao_valida"]
    assert pd.isna(evento["duracao_horas"])
    # ano/mes sao derivados de DatInicioInterrupcao -- sem data, ficam nulos
    # (nao existe AnoCompetencia/MesCompetencia no schema real).
    assert pd.isna(evento["ano"])
    assert pd.isna(evento["mes"])


def test_interrupcao_programada_e_sinalizada_mas_mantida(raw_df):
    """Nao existe campo equivalente a DscMotivoExpurgo no schema real -- o
    filtro analogo disponivel e DscTipoInterrupcao (Programada / Nao
    Programada), ver docs/DEVLOG.md."""
    df = clean_interrupcoes(raw_df)
    assert len(df) == len(raw_df)  # nenhum evento foi descartado

    programado = df[df["NumOrdemInterrupcao"] == "INT0004"].iloc[0]
    assert programado["programada"]

    nao_programado = df[df["NumOrdemInterrupcao"] == "INT0001"].iloc[0]
    assert not nao_programado["programada"]


def test_motivo_interrupcao_e_mantido_bruto_sem_decodificar(raw_df):
    df = clean_interrupcoes(raw_df)
    evento = df[df["NumOrdemInterrupcao"] == "INT0006"].iloc[0]
    assert evento["motivo_interrupcao_codigo"] == "1"


def test_sigagente_com_espacos_e_normalizado(raw_df):
    """SigAgente vem com espacos em branco a direita nos dados reais (ex:
    'EAC                 ') -- sem strip, a mesma distribuidora contaria
    como duas diferentes."""
    df = clean_interrupcoes(raw_df)
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
