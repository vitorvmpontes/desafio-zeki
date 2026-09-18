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

# Chatbot text-to-SQL (api/chat_sql.py) -- engine SEPARADA da DATABASE_URL
# acima, apontando pro role Postgres dedicado e somente-leitura criado por
# `db/readonly_role.sql` (NUNCA o usuario de escrita usado pela automacao
# mensal). Vazio por padrao: sem essa variavel, o chat fica desabilitado
# (ver api/servico.py::responder_chat) em vez de usar um default que
# apontaria, por engano, pro mesmo usuario com permissao de escrita.
DATABASE_URL_READONLY = os.environ.get("DATABASE_URL_READONLY", "")

# Google Gemini (google-genai) -- usado só por api/chat_sql.py::gerar_sql.
# Sem GEMINI_API_KEY, o chat responde com um erro claro em vez de travar a
# API inteira (ver README.md, secao do chatbot, pra como obter uma chave).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

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
