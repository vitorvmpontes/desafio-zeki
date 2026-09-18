import pandas as pd

from ml.baseline import prever_baseline


def _linha(municipio, ano, mes, fec):
    return {
        "codigo_ibge_resolvido": municipio,
        "nome_municipio": f"Municipio {municipio}",
        "ano": ano,
        "mes": mes,
        "fec_aprox": fec,
    }


def _painel_sintetico() -> pd.DataFrame:
    linhas = [
        _linha("1100015", 2024, 1, fec=0.01),
        _linha("1100015", 2024, 2, fec=0.02),
        _linha("1100015", 2024, 12, fec=0.03),
        _linha("1100015", 2025, 1, fec=0.04),
        # 1100023 so tem 2 meses de historico -- nao tem t-12 disponivel
        # para nenhum mes-alvo razoavel, so t-1.
        _linha("1100023", 2025, 11, fec=0.10),
        _linha("1100023", 2025, 12, fec=0.20),
    ]
    return pd.DataFrame(linhas)


def test_baseline_combina_t1_e_t12_quando_os_dois_existem():
    resultado = prever_baseline(_painel_sintetico())
    linha = resultado[resultado["codigo_ibge_resolvido"] == "1100015"].iloc[0]
    # ultimo mes de 1100015 e jan/2025 -> alvo default e fev/2025
    assert str(linha["periodo_alvo"]) == "2025-02"
    assert linha["baseline_t1"] == 0.04  # jan/2025
    assert linha["baseline_t12"] == 0.02  # fev/2024 (fev/2025 - 12 meses)
    assert round(linha["baseline_previsto"], 4) == round((0.04 + 0.02) / 2, 4)


def test_baseline_usa_so_t1_quando_t12_nao_existe():
    resultado = prever_baseline(_painel_sintetico())
    linha = resultado[resultado["codigo_ibge_resolvido"] == "1100023"].iloc[0]
    # ultimo mes e dez/2025 -> alvo default e jan/2026; t-12 seria jan/2025,
    # que nao existe no historico desse municipio (so comeca em nov/2025)
    assert str(linha["periodo_alvo"]) == "2026-01"
    assert linha["baseline_t1"] == 0.20  # dez/2025
    assert pd.isna(linha["baseline_t12"])
    assert linha["baseline_previsto"] == 0.20


def test_periodo_alvo_explicito_e_respeitado():
    alvo = pd.Period("2025-01", freq="M")
    resultado = prever_baseline(_painel_sintetico(), periodo_alvo=alvo)
    linha = resultado[resultado["codigo_ibge_resolvido"] == "1100015"].iloc[0]
    assert str(linha["periodo_alvo"]) == "2025-01"
    assert linha["baseline_t1"] == 0.03  # dez/2024 (jan/2025 - 1 mes)
    assert linha["baseline_t12"] == 0.01  # jan/2024 (jan/2025 - 12 meses)
    assert round(linha["baseline_previsto"], 4) == round((0.03 + 0.01) / 2, 4)
