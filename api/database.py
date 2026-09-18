"""Acesso ao Postgres.

O painel município x mês é pequeno (~132 mil linhas, ~60 MB) -- em vez de
montar uma query SQL diferente para cada endpoint, a API lê a tabela
inteira UMA VEZ (na inicialização) para um DataFrame em memória e resolve
todas as consultas com pandas, igual ao resto do projeto (`ml/`). O
Postgres continua sendo a fonte de verdade / o jeito de outros consumidores
(ex.: a automação mensal do Dia 7) lerem os dados sem depender da API -- só
não faz sentido pagar uma query de rede por requisição para um dataset
desse tamanho.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from api.config import DATABASE_URL, DATABASE_URL_READONLY

TABELA = "municipio_mes"


def criar_engine(database_url: str = DATABASE_URL) -> Engine:
    return create_engine(database_url)


def criar_engine_leitura(database_url: str | None = None) -> Engine | None:
    """Engine SEPARADA de `criar_engine`, dedicada ao chatbot text-to-SQL
    (`api/chat_sql.py`) -- deve apontar pro role Postgres somente-leitura
    criado por `db/readonly_role.sql` (`continua_readonly`), nunca pro
    usuário de escrita que a automação mensal usa para recriar a tabela.

    Diferente de `criar_engine`, não tem um default "sensato": um role
    read-only só existe depois de alguém rodar `db/readonly_role.sql`
    manualmente uma vez, então sem `DATABASE_URL_READONLY` configurada isso
    devolve `None` -- o chat fica desabilitado com um erro claro (ver
    `api/servico.py::responder_chat`) em vez de silenciosamente usar a
    engine de escrita."""
    url = database_url if database_url is not None else DATABASE_URL_READONLY
    if not url:
        return None
    return create_engine(url)


def carregar_painel(engine: Engine) -> pd.DataFrame:
    """Lê a tabela `municipio_mes` inteira do banco."""
    with engine.connect() as conn:
        return pd.read_sql(f"SELECT * FROM {TABELA}", conn)
