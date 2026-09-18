"""Constroi a tabela de referencia de municipios (data/reference/municipios.csv).

Municipio/UF de cada interrupcao vem do bridge conjunto->municipio da
propria ANEEL ("IndQual Municipio", ver `etl/ibge.py`) -- mas esse bridge
nao publica REGIAO, e essa tabela e usada so para esse lookup auxiliar
(codigo IBGE -> regiao), com o mesmo fallback de 7->6 digitos ja usado
historicamente no join.

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

Também carrega `latitude`/`longitude` (sede do município) do mesmo CSV bruto
da fonte -- usadas pelo mapa de clusters de qualidade de serviço
(`ml/mapa.py`, pedido do usuário: "criar um mapa de verdade, usando um
arquivo KML gerado a partir de alguma clusterização"). Não havia necessidade
de coordenadas para nenhum outro cálculo do produto até agora, por isso
ficavam de fora de `colunas_finais`.
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

    # estados.csv TAMBEM tem latitude/longitude (do centroide do ESTADO, nao
    # do municipio) -- por isso o merge acima gera sufixo em ambas as
    # colunas (`_municipio`/`_uf`); a coordenada que queremos e a do
    # municipio (sede), nao a do estado.
    df = df.rename(
        columns={
            "codigo_ibge": "codigo_ibge_7",
            "nome_municipio": "nome_municipio",
            "uf": "uf_sigla",
            "nome_uf": "nome_uf",
            "latitude_municipio": "latitude",
            "longitude_municipio": "longitude",
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
        "latitude",
        "longitude",
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
