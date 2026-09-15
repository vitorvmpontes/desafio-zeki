"""Orquestra o pipeline completo: limpeza + agregacao dos Parquet baixados.

Uso:
    python -m etl.pipeline --anos 2024,2025

Le todos os `data/raw/interrupcoes-<ano>.parquet` para os anos pedidos,
aplica etl.clean e etl.aggregate, e escreve o resultado em
`data/processed/municipio_mes.parquet` (e uma copia .csv, mais facil de
inspecionar). Reprocessar com os mesmos anos e seguro -- o arquivo de saida
e sempre reescrito do zero a partir do raw, nunca appendado (evita registros
duplicados se a ANEEL republicar um ano com correcoes).
"""
import argparse
import logging

import pandas as pd

from etl.aggregate import aggregate_municipio_mes
from etl.clean import clean_interrupcoes
from etl.config import COL_MUNICIPIO_IBGE, PROCESSED_DIR, RAW_DIR
from etl.ibge import load_municipios_reference

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run(anos: list[int]) -> pd.DataFrame:
    referencia = load_municipios_reference()

    partes = []
    for ano in anos:
        caminho = RAW_DIR / f"interrupcoes-{ano}.parquet"
        if not caminho.exists():
            raise FileNotFoundError(
                f"{caminho} nao encontrado -- rode antes: python -m etl.download --anos {ano}"
            )
        logger.info("Lendo %s", caminho)
        partes.append(pd.read_parquet(caminho))

    df_raw = pd.concat(partes, ignore_index=True)
    logger.info("%d eventos brutos carregados (%d anos)", len(df_raw), len(anos))

    df_limpo = clean_interrupcoes(df_raw, referencia=referencia)
    df_agregado = aggregate_municipio_mes(df_limpo, codigo_municipio_col=COL_MUNICIPIO_IBGE)
    logger.info("%d linhas municipio x mes geradas", len(df_agregado))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    saida_parquet = PROCESSED_DIR / "municipio_mes.parquet"
    saida_csv = PROCESSED_DIR / "municipio_mes.csv"
    df_agregado.to_parquet(saida_parquet, index=False)
    df_agregado.to_csv(saida_csv, index=False)
    logger.info("Salvo em %s e %s", saida_parquet, saida_csv)

    return df_agregado


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anos", type=str, required=True, help="anos a processar, ex: 2024,2025")
    args = parser.parse_args()
    anos = [int(a) for a in args.anos.split(",")]
    run(anos)


if __name__ == "__main__":
    main()
