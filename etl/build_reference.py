"""Constroi a tabela de referencia de municipios (data/reference/municipios.csv).

A ANEEL identifica o municipio de cada interrupcao só pelo codigo IBGE
(`CodMunicipioIBGE`), sem UF nem nome -- por isso o pipeline precisa de uma
tabela auxiliar para traduzir codigo -> municipio/UF/regiao.

Por que uma tabela estatica versionada no repositorio, em vez de consultar a
API do IBGE em tempo real a cada execucao:
  1. Municipios e UFs do Brasil praticamente nao mudam -- nao ha necessidade
     de buscar isso toda vez que o pipeline roda.
  2. Remove uma dependencia de rede (e um ponto de falha) do pipeline mensal.
  3. Deixa o join auditavel e reprodutivel: qualquer pessoa pode abrir o CSV
     e ver exatamente a tabela usada.

Fonte dos dados brutos: o repositorio publico `kelvins/municipios-brasileiros`
(https://github.com/kelvins/municipios-brasileiros), que consolida a tabela
de municipios do IBGE em CSV pronto para uso -- mais simples de consumir do
que o webservice oficial do IBGE para esse caso de uso pontual.

Uso:
    python -m etl.build_reference
"""
import logging

import pandas as pd

from etl.config import IBGE_ESTADOS_URL, IBGE_MUNICIPIOS_URL, MUNICIPIOS_REFERENCE_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def build_reference() -> pd.DataFrame:
    municipios = pd.read_csv(IBGE_MUNICIPIOS_URL)
    estados = pd.read_csv(IBGE_ESTADOS_URL)

    df = municipios.merge(estados, on="codigo_uf", how="left", suffixes=("_municipio", "_uf"))

    df = df.rename(
        columns={
            "codigo_ibge": "codigo_ibge_7",
            "nome_municipio": "nome_municipio",
            "uf": "uf_sigla",
            "nome_uf": "nome_uf",
        }
    )

    # A ANEEL as vezes reporta o codigo IBGE sem o digito verificador (6
    # digitos em vez de 7) -- guardamos os dois para permitir o join com
    # fallback em etl/ibge.py.
    df["codigo_ibge_6"] = df["codigo_ibge_7"].astype(str).str[:6]

    colunas_finais = [
        "codigo_ibge_7",
        "codigo_ibge_6",
        "nome_municipio",
        "uf_sigla",
        "nome_uf",
        "regiao",
    ]
    df = df[colunas_finais].sort_values("codigo_ibge_7").reset_index(drop=True)

    logger.info("Tabela de referencia construida: %d municipios", len(df))
    return df


def main() -> None:
    df = build_reference()
    MUNICIPIOS_REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(MUNICIPIOS_REFERENCE_PATH, index=False)
    logger.info("Salvo em %s", MUNICIPIOS_REFERENCE_PATH)


if __name__ == "__main__":
    main()
