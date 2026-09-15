"""Constantes e caminhos usados pelo pipeline de ingestão."""
from pathlib import Path

# --- Caminhos -----------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = DATA_DIR / "reference"
SAMPLE_DIR = DATA_DIR / "sample"

MUNICIPIOS_REFERENCE_PATH = REFERENCE_DIR / "municipios.csv"

# --- Fonte: ANEEL ---------------------------------------------------------
# Dataset "Interrupcoes de Energia Eletrica nas Redes de Distribuicao"
# https://dadosabertos.aneel.gov.br/dataset/interrupcoes-de-energia-eletrica-nas-redes-de-distribuicao
ANEEL_PACKAGE_ID = "ccb25653-f07b-4f28-84c2-62a89d1f5a56"

# IDs de recurso (Parquet) por ano, levantados manualmente no portal em
# setembro/2026. O portal da ANEEL ocasionalmente rotaciona esses IDs quando
# publica uma atualizacao mensal -- se o download falhar com 404, confira o
# ID atual em:
# https://dadosabertos.aneel.gov.br/dataset/interrupcoes-de-energia-eletrica-nas-redes-de-distribuicao
ANEEL_PARQUET_RESOURCE_IDS = {
    2024: "fc5ca52c-329c-4443-a2d6-08ccec711ade",
    2025: "691de320-cb3d-471b-b9ec-8c1b86af8c83",
}


def aneel_parquet_url(ano: int) -> str:
    """Monta a URL de download do Parquet anual da ANEEL para o ano dado."""
    try:
        resource_id = ANEEL_PARQUET_RESOURCE_IDS[ano]
    except KeyError as exc:
        raise ValueError(
            f"Nao tenho o resource_id do Parquet de {ano} em ANEEL_PARQUET_RESOURCE_IDS. "
            "Confira o ID no portal e adicione aqui."
        ) from exc
    return (
        f"https://dadosabertos.aneel.gov.br/dataset/{ANEEL_PACKAGE_ID}"
        f"/resource/{resource_id}/download/interrupcoes-energia-eletrica-{ano}.parquet"
    )


# --- Fonte: IBGE (municipios) --------------------------------------------
# Tabela publica de municipios/UFs, usada para obter UF e regiao a partir do
# CodMunicipioIBGE (a ANEEL nao publica UF diretamente). Ver
# etl/build_reference.py para como e por que essa fonte foi escolhida.
IBGE_MUNICIPIOS_URL = (
    "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv"
)
IBGE_ESTADOS_URL = (
    "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/estados.csv"
)

# --- Colunas relevantes do dataset de interrupcoes (ver dicionario de dados
# da ANEEL, resumido em docs/ARQUITETURA.md) ------------------------------
COL_MUNICIPIO_IBGE = "CodMunicipioIBGE"
COL_AGENTE_SIGLA = "SigAgente"
COL_INICIO = "DatInicioInterrupcao"
COL_FIM = "DatFimInterrupcao"
COL_MOTIVO_EXPURGO = "DscMotivoExpurgo"
COL_ANO_COMPETENCIA = "AnoCompetencia"
COL_MES_COMPETENCIA = "MesCompetencia"
COL_CONSUMIDORES_AFETADOS = "QtdConsumidoresAfetados"
COL_CONSUMIDORES_ATIVOS = "QtdConsumidoresAtivos"
COL_FATO_GERADOR_ORIGEM = "DscFatoGeradorOrigem"
