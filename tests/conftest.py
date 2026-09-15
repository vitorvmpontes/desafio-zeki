from pathlib import Path

import pandas as pd
import pytest

from etl.ibge import load_conjunto_municipio_bridge, load_municipios_reference

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def raw_df() -> pd.DataFrame:
    return pd.read_csv(FIXTURES_DIR / "sample_raw_interrupcoes.csv", dtype=str)


@pytest.fixture
def referencia() -> pd.DataFrame:
    return load_municipios_reference()


@pytest.fixture
def bridge() -> pd.DataFrame:
    return load_conjunto_municipio_bridge(FIXTURES_DIR / "sample_indqual_municipio.csv")
