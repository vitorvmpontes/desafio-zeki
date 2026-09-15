"""Download dos arquivos Parquet anuais de interrupcoes da ANEEL.

Idempotente: se o arquivo do ano ja existe localmente com o mesmo tamanho
reportado pelo servidor (Content-Length), o download e pulado -- assim o
job mensal do GitHub Actions pode rodar todo mes sem rebaixar anos que nao
mudaram, so o ano corrente (que a ANEEL atualiza mensalmente).

NOTA: este script precisa de acesso real a internet para
dadosabertos.aneel.gov.br. Ele nao roda no ambiente de desenvolvimento
usado para escrever este pipeline (sandbox sem acesso a esse dominio) --
foi testado apenas com fixtures sinteticas em tests/. Rode-o no seu
ambiente local ou no GitHub Actions, que tem internet irrestrita.
"""
import argparse
import logging
import sys

import requests

from etl.config import CONJUNTO_MUNICIPIO_PATH, RAW_DIR, aneel_indqual_municipio_url, aneel_parquet_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60
CHUNK_SIZE = 1024 * 1024  # 1 MiB


def download_ano(ano: int, force: bool = False) -> None:
    url = aneel_parquet_url(ano)
    destino = RAW_DIR / f"interrupcoes-{ano}.parquet"
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with requests.head(url, timeout=TIMEOUT_SECONDS, allow_redirects=True) as head:
        head.raise_for_status()
        tamanho_remoto = int(head.headers.get("Content-Length", 0))

    if destino.exists() and not force:
        tamanho_local = destino.stat().st_size
        if tamanho_remoto and tamanho_local == tamanho_remoto:
            logger.info("%s ja esta atualizado (%d bytes) -- pulando download", destino.name, tamanho_local)
            return
        logger.info(
            "%s existe mas o tamanho mudou (local=%d, remoto=%d) -- baixando de novo",
            destino.name,
            tamanho_local,
            tamanho_remoto,
        )

    logger.info("Baixando %s (%.1f MiB esperados)...", url, tamanho_remoto / 2**20)
    with requests.get(url, timeout=TIMEOUT_SECONDS, stream=True) as resp:
        resp.raise_for_status()
        tmp = destino.with_suffix(".parquet.tmp")
        baixado = 0
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                f.write(chunk)
                baixado += len(chunk)
        tmp.rename(destino)
    logger.info("Salvo em %s (%.1f MiB)", destino, baixado / 2**20)


def download_indqual_municipio(force: bool = False) -> None:
    """Baixa o de-para conjunto->municipio (dataset "IndQual Municipio").

    Diferente dos Parquet anuais de interrupcoes, este arquivo nao varia por
    ano -- e baixado uma vez e reaproveitado por qualquer ano processado. Se
    o resource_id ainda nao foi confirmado em etl/config.py, levanta um erro
    com instrucoes de download manual (o pipeline consegue rodar assim que o
    arquivo existir em CONJUNTO_MUNICIPIO_PATH, baixado manualmente ou nao).
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if CONJUNTO_MUNICIPIO_PATH.exists() and not force:
        logger.info(
            "%s ja existe -- pulando download (use --force para atualizar)",
            CONJUNTO_MUNICIPIO_PATH.name,
        )
        return

    url = aneel_indqual_municipio_url()
    logger.info("Baixando bridge conjunto->municipio de %s", url)
    resp = requests.get(url, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()
    CONJUNTO_MUNICIPIO_PATH.write_bytes(resp.content)
    logger.info("Salvo em %s", CONJUNTO_MUNICIPIO_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--anos",
        type=str,
        required=True,
        help="anos a baixar, separados por virgula (ex: 2024,2025)",
    )
    parser.add_argument("--force", action="store_true", help="rebaixa mesmo se o arquivo local parecer atualizado")
    args = parser.parse_args()

    anos = [int(a) for a in args.anos.split(",")]
    falhas = []

    try:
        download_indqual_municipio(force=args.force)
    except Exception as exc:  # noqa: BLE001 -- nao deve travar o download dos Parquet anuais
        logger.error(
            "Falha ao baixar/gerar o bridge conjunto->municipio: %s -- veja etl/README.md "
            "para o download manual",
            exc,
        )
        falhas.append("indqual_municipio")

    for ano in anos:
        try:
            download_ano(ano, force=args.force)
        except Exception as exc:  # noqa: BLE001 -- queremos seguir tentando os outros anos
            logger.error("Falha ao baixar %d: %s", ano, exc)
            falhas.append(ano)

    if falhas:
        logger.error("Anos que falharam: %s", falhas)
        sys.exit(1)


if __name__ == "__main__":
    main()
