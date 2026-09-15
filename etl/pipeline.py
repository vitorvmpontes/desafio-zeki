"""Orquestra o pipeline completo: limpeza + agregacao dos Parquet baixados.

Uso:
    python -m etl.pipeline --anos 2024,2025
    python -m etl.pipeline --anos 2024,2025 --batch-size 200000   # maquina com pouca memoria

Le todos os `data/raw/interrupcoes-<ano>.parquet` para os anos pedidos EM
LOTES (nunca o arquivo inteiro de uma vez -- ver docstring de `etl.aggregate`
e docs/DEVLOG.md: manter os ~18,9 milhoes de eventos reais limpos na
memoria ao mesmo tempo esgotou a RAM de uma maquina comum, mesmo depois de
eliminar os pontos que faziam copias desnecessarias). Cada lote e limpo e
agregado para o grao conjunto x mes (`etl.aggregate.aggregate_conjunto_mes`)
e descartado antes do proximo ser lido; so os resultados parciais (pequenos)
ficam acumulados. No final, os parciais sao combinados
(`etl.aggregate.combine_conjunto_mes`), cruzados com o bridge
conjunto->municipio e agregados para o grao final municipio x mes, e o
resultado e escrito em `data/processed/municipio_mes.{parquet,csv}`.
Reprocessar com os mesmos anos e seguro -- o arquivo de saida e sempre
reescrito do zero a partir do raw, nunca appendado.
"""
import argparse
import logging

import pandas as pd
import pyarrow.parquet as pq

from etl.aggregate import aggregate_conjunto_mes, aggregate_municipio_mes, combine_conjunto_mes
from etl.clean import clean_interrupcoes
from etl.config import CONJUNTO_MUNICIPIO_PATH, PROCESSED_DIR, RAW_DIR
from etl.ibge import load_conjunto_municipio_bridge, load_municipios_reference

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Linhas por lote lidas do Parquet de cada vez. Nao e uma ciencia exata --
# e so grande o suficiente para o groupby por lote ser eficiente, e pequeno
# o suficiente para caber com folga na memoria de uma maquina comum. Ajuste
# com --batch-size se ainda faltar memoria (lotes menores) ou se sobrar
# memoria e voce quiser processar mais rapido (lotes maiores).
BATCH_SIZE_PADRAO = 300_000


def _iter_lotes_brutos(caminhos: list, batch_size: int):
    for caminho in caminhos:
        logger.info("Lendo %s em lotes de %d linhas", caminho, batch_size)
        parquet_file = pq.ParquetFile(caminho)
        for batch in parquet_file.iter_batches(batch_size=batch_size):
            yield batch.to_pandas()


def run(anos: list[int], batch_size: int = BATCH_SIZE_PADRAO) -> pd.DataFrame:
    referencia = load_municipios_reference()

    if not CONJUNTO_MUNICIPIO_PATH.exists():
        raise FileNotFoundError(
            f"{CONJUNTO_MUNICIPIO_PATH} nao encontrado -- rode antes: python -m etl.download "
            f"--anos {','.join(str(a) for a in anos)} (ou baixe manualmente, ver etl/README.md)"
        )
    bridge = load_conjunto_municipio_bridge()

    caminhos = []
    for ano in anos:
        caminho = RAW_DIR / f"interrupcoes-{ano}.parquet"
        if not caminho.exists():
            raise FileNotFoundError(
                f"{caminho} nao encontrado -- rode antes: python -m etl.download --anos {ano}"
            )
        caminhos.append(caminho)

    partes_conjunto_mes = []
    total_eventos = 0
    for i, lote_bruto in enumerate(_iter_lotes_brutos(caminhos, batch_size)):
        total_eventos += len(lote_bruto)
        lote_limpo = clean_interrupcoes(lote_bruto)
        parte, _ = aggregate_conjunto_mes(lote_limpo)
        partes_conjunto_mes.append(parte)
        logger.info("Lote %d processado (%d eventos neste lote, %d acumulados)", i + 1, len(lote_bruto), total_eventos)

    logger.info("%d eventos brutos processados em %d lotes (%d anos)", total_eventos, len(partes_conjunto_mes), len(anos))

    conjunto_mes, causa_cols = combine_conjunto_mes(partes_conjunto_mes)
    logger.info("%d linhas conjunto x mes apos combinar os lotes", len(conjunto_mes))

    df_agregado = aggregate_municipio_mes(conjunto_mes, causa_cols, bridge=bridge, referencia=referencia)
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
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE_PADRAO,
        help=f"linhas por lote lidas do Parquet (padrao: {BATCH_SIZE_PADRAO}; reduza se faltar memoria)",
    )
    args = parser.parse_args()
    anos = [int(a) for a in args.anos.split(",")]
    run(anos, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
