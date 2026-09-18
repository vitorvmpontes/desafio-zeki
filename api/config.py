"""Configuração da API: onde estão o banco e os artefatos do modelo.

Tudo vem de variável de ambiente (com `.env` carregado automaticamente, se
existir -- ver `.env.example` na raiz do repositório), com um default
sensato para rodar localmente sem configurar nada além do Postgres.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
ML_ARTIFACTS_DIR = ROOT_DIR / "ml" / "artifacts"

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://continua:continua@localhost:5432/continua")

MODELO_PATH = Path(os.environ.get("MODELO_PATH", ML_ARTIFACTS_DIR / "modelo_final.joblib"))
MODELO_METADATA_PATH = Path(
    os.environ.get("MODELO_METADATA_PATH", ML_ARTIFACTS_DIR / "modelo_final_metadata.json")
)
IMPORTANCIA_FEATURES_PATH = Path(
    os.environ.get("IMPORTANCIA_FEATURES_PATH", ML_ARTIFACTS_DIR / "importancia_features.json")
)
MODELAGEM_METRICAS_PATH = Path(
    os.environ.get("MODELAGEM_METRICAS_PATH", ML_ARTIFACTS_DIR / "modelagem_metricas.json")
)
BASELINE_METRICAS_PATH = Path(
    os.environ.get("BASELINE_METRICAS_PATH", ML_ARTIFACTS_DIR / "baseline_metricas.json")
)
