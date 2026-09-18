"""Testa etl/load_db.py contra SQLite (nao Postgres) -- so para validar a
logica de carga (to_sql substitui a tabela, indices sao criados, o
DataFrame carregado bate com o original) sem depender de uma instancia
Postgres rodando no CI. A validacao contra Postgres de verdade foi feita
manualmente via docker compose / instancia local (ver docs/DEVLOG.md, Dia 5).
"""
import pandas as pd
from sqlalchemy import create_engine, text

from etl.load_db import TABELA, carregar


def test_carregar_grava_todas_as_linhas_e_cria_indices(tmp_path):
    df = pd.DataFrame(
        {
            "codigo_ibge_resolvido": ["1100015", "1100023"],
            "ano": [2024, 2024],
            "mes": [1, 1],
            "fec_aprox": [0.01, 0.02],
        }
    )
    caminho_parquet = tmp_path / "municipio_mes.parquet"
    df.to_parquet(caminho_parquet, index=False)

    database_url = f"sqlite:///{tmp_path / 'teste.db'}"
    n = carregar(caminho_parquet, database_url)
    assert n == 2

    engine = create_engine(database_url)
    with engine.connect() as conn:
        lido = pd.read_sql(f"SELECT * FROM {TABELA}", conn)
        indices = conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'")).fetchall()

    assert len(lido) == 2
    assert set(lido["codigo_ibge_resolvido"]) == {"1100015", "1100023"}
    nomes_indices = {row[0] for row in indices}
    assert f"ix_{TABELA}_codigo" in nomes_indices
    assert f"ix_{TABELA}_periodo" in nomes_indices


def test_carregar_e_idempotente_recria_tabela(tmp_path):
    """Rodar de novo com um parquet MENOR nao deve deixar linhas antigas
    para tras -- to_sql(if_exists='replace') precisa recriar a tabela do
    zero, nao so appendar."""
    caminho_parquet = tmp_path / "municipio_mes.parquet"
    database_url = f"sqlite:///{tmp_path / 'teste.db'}"

    pd.DataFrame({"codigo_ibge_resolvido": ["A", "B", "C"], "ano": [2024] * 3, "mes": [1] * 3, "fec_aprox": [0.1, 0.2, 0.3]}).to_parquet(
        caminho_parquet, index=False
    )
    carregar(caminho_parquet, database_url)

    pd.DataFrame({"codigo_ibge_resolvido": ["A"], "ano": [2024], "mes": [1], "fec_aprox": [0.1]}).to_parquet(
        caminho_parquet, index=False
    )
    carregar(caminho_parquet, database_url)

    engine = create_engine(database_url)
    with engine.connect() as conn:
        lido = pd.read_sql(f"SELECT * FROM {TABELA}", conn)
    assert len(lido) == 1
