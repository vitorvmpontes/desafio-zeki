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
CONJUNTO_MUNICIPIO_PATH = RAW_DIR / "indqual_municipio.csv"

# --- Fonte: ANEEL — interrupções ------------------------------------------
# Dataset "Interrupcoes de Energia Eletrica nas Redes de Distribuicao"
# https://dadosabertos.aneel.gov.br/dataset/interrupcoes-de-energia-eletrica-nas-redes-de-distribuicao
ANEEL_PACKAGE_ID = "ccb25653-f07b-4f28-84c2-62a89d1f5a56"

# IDs de recurso (Parquet) por ano, levantados manualmente no portal em
# setembro/2026. Confirmado funcionando contra o servidor real (ver
# docs/DEVLOG.md). O portal da ANEEL ocasionalmente rotaciona esses IDs
# quando publica uma atualizacao mensal -- se o download falhar com 404,
# confira o ID atual em:
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


# --- Fonte: ANEEL — bridge conjunto -> município ("IndQual Município") ---
# O Parquet de interrupções NÃO publica município nem UF diretamente --
# apenas o conjunto de unidades consumidoras (`IdeConjuntoUnidadeConsumidora`).
# Isso só foi descoberto ao processar o dado real: a documentação oficial da
# ANEEL usada para desenhar este pipeline descrevia um `CodMunicipioIBGE`
# que não existe no arquivo publicado (ver docs/DEVLOG.md, "Dia 2 —
# descoberta do schema real"). O de-para conjunto -> município é publicado
# à parte, no dataset "IndQual Município":
# https://dadosabertos.aneel.gov.br/dataset/indqual-municipio
#
# TODO(vitor): confirmar o resource_id do recurso CSV mais recente desse
# dataset (o mesmo processo manual usado para ANEEL_PARQUET_RESOURCE_IDS) e
# preencher abaixo, para que `python -m etl.download` baixe esse arquivo
# também. Até lá, baixe manualmente em
# https://dadosabertos.aneel.gov.br/dataset/indqual-municipio e salve em
# `data/raw/indqual_municipio.csv` -- é exatamente onde o pipeline espera
# encontrá-lo.
ANEEL_INDQUAL_MUNICIPIO_DATASET_URL = "https://dadosabertos.aneel.gov.br/dataset/indqual-municipio"
ANEEL_INDQUAL_MUNICIPIO_PACKAGE_ID: str | None = None
ANEEL_INDQUAL_MUNICIPIO_RESOURCE_ID: str | None = None


def aneel_indqual_municipio_url() -> str:
    if not ANEEL_INDQUAL_MUNICIPIO_PACKAGE_ID or not ANEEL_INDQUAL_MUNICIPIO_RESOURCE_ID:
        raise ValueError(
            "ANEEL_INDQUAL_MUNICIPIO_PACKAGE_ID/RESOURCE_ID ainda nao foram preenchidos em "
            "etl/config.py. Baixe manualmente o CSV mais recente em "
            f"{ANEEL_INDQUAL_MUNICIPIO_DATASET_URL} e salve em {CONJUNTO_MUNICIPIO_PATH}, "
            "ou preencha os IDs aqui para automatizar o download."
        )
    return (
        f"https://dadosabertos.aneel.gov.br/dataset/{ANEEL_INDQUAL_MUNICIPIO_PACKAGE_ID}"
        f"/resource/{ANEEL_INDQUAL_MUNICIPIO_RESOURCE_ID}/download/indqual-municipio.csv"
    )


# --- Fonte: IBGE (municípios) ---------------------------------------------
# Tabela pública de municípios/UFs, usada como lookup auxiliar de REGIÃO a
# partir do código IBGE resolvido -- o dataset "IndQual Município" dá
# município/UF diretamente, mas não região. Ver etl/build_reference.py.
IBGE_MUNICIPIOS_URL = (
    "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv"
)
IBGE_ESTADOS_URL = (
    "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/estados.csv"
)

# --- Colunas do dataset de interrupções (schema real, confirmado contra o
# Parquet baixado -- ver docs/DEVLOG.md para o histórico da descoberta) ----
COL_CONJUNTO_ID = "IdeConjuntoUnidadeConsumidora"
COL_CONJUNTO_DESC = "DscConjuntoUnidadeConsumidora"
COL_AGENTE_SIGLA = "SigAgente"
COL_INICIO = "DatInicioInterrupcao"
COL_FIM = "DatFimInterrupcao"
COL_TIPO_INTERRUPCAO = "DscTipoInterrupcao"  # "Programada" | "Não Programada"
COL_MOTIVO_ID = "IdeMotivoInterrupcao"  # codigo numerico, significado ainda nao decodificado
COL_CONSUMIDORES_AFETADOS = "NumUnidadeConsumidora"  # unidades consumidoras atingidas pelo evento
COL_CONSUMIDORES_ATIVOS = "NumConsumidorConjunto"  # total de consumidores do conjunto no periodo
COL_FATO_GERADOR = "DscFatoGeradorInterrupcao"  # causa em texto livre, formatacao inconsistente

# --- Colunas do bridge "IndQual Município" --------------------------------
COL_BRIDGE_CONJUNTO_ID = "IdeConjUnidConsumidoras"
COL_BRIDGE_COD_MUNICIPIO = "CodMunicipio"
COL_BRIDGE_NOME_MUNICIPIO = "NomMunicipio"
COL_BRIDGE_UF = "SigUF"
