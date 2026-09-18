"""Carrega data/processed/municipio_mes.parquet no Postgres (tabela
`municipio_mes`) -- o passo entre o ETL (Dia 2) e a API (Dia 5) que
`docs/ARQUITETURA.md` sempre previu ("DB -> API"), e que a automação
mensal do Dia 7 também roda depois de reprocessar os dados.

Uso:
    python -m etl.load_db                                    # usa data/processed/municipio_mes.parquet e DATABASE_URL do .env
    python -m etl.load_db --parquet outro/caminho.parquet
    python -m etl.load_db --database-url postgresql://usuario:senha@host:5432/banco

Idempotente: a tabela é sempre RECRIADA a partir do parquet
(`if_exists="replace"`), nunca appendada -- reprocessar é sempre seguro,
seguindo o mesmo princípio de `etl/pipeline.py`.
"""
import argparse
import logging
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from etl.config import PROCESSED_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TABELA = "municipio_mes"


def _database_url(explicito: str | None = None) -> str:
    if explicito:
        return explicito
    # tenta carregar .env se python-dotenv estiver disponivel (nao e
    # obrigatorio -- DATABASE_URL pode vir de qualquer jeito do ambiente)
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL nao encontrada no ambiente. Copie .env.example para .env "
            "(ver README.md) ou passe --database-url."
        )
    return url


def carregar(caminho_parquet: Path, database_url: str) -> int:
    if not caminho_parquet.exists():
        raise FileNotFoundError(
            f"{caminho_parquet} nao encontrado -- rode antes: python -m etl.pipeline --anos 2024,2025"
        )

    df = pd.read_parquet(caminho_parquet)
    logger.info("%d linhas lidas de %s", len(df), caminho_parquet)

    engine = create_engine(database_url)
    df.to_sql(TABELA, engine, if_exists="replace", index=False, chunksize=10_000)
    logger.info("%d linhas carregadas na tabela '%s'", len(df), TABELA)

    with engine.begin() as conn:
        conn.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{TABELA}_codigo ON "{TABELA}" (codigo_ibge_resolvido)'))
        conn.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{TABELA}_periodo ON "{TABELA}" (ano, mes)'))
    logger.info("Indices (codigo_ibge_resolvido) e (ano, mes) garantidos.")

    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parquet",
        type=Path,
        default=PROCESSED_DIR / "municipio_mes.parquet",
        help="caminho do parquet a carregar (padrao: data/processed/municipio_mes.parquet)",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="URL de conexao Postgres (padrao: variavel de ambiente DATABASE_URL / .env)",
    )
    args = parser.parse_args()
    url = _database_url(args.database_url)
    carregar(args.parquet, url)


if __name__ == "__main__":
    main()
