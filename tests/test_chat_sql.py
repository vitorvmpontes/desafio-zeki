"""Testes de api/chat_sql.py -- o módulo mais sensível deste projeto (SQL
gerado por um LLM a partir de texto não confiável, ver a docstring do módulo
para a justificativa da defesa em profundidade).

Duas partes bem separadas:

1. Testes UNITÁRIOS de `validar_sql`/`_extrair_tabelas` -- não tocam rede
   nem banco, rodam em qualquer CI. Cobrem exatamente os casos usados na
   auto-revisão adversarial manual que encontrou os dois bugs documentados
   em `docs/DEVLOG.md` (join por vírgula e subquery aninhada escapando da
   whitelist de tabelas), agora formalizados como regressão.
2. Um teste de INTEGRAÇÃO de `executar_sql_seguro` contra um Postgres real
   (`continua_readonly`, ver `db/readonly_role.sql`) -- pulado com
   `pytest.skip` se esse Postgres não estiver acessível, mesmo padrão já
   usado em `tests/test_load_db.py`/`docs/DEVLOG.md` para não acoplar o CI a
   infraestrutura externa.

Nenhum teste aqui chama o Gemini de verdade -- `gerar_sql` faz uma chamada de
rede (bloqueada neste sandbox de desenvolvimento, ver docs/DEVLOG.md) e é
testado só quanto ao caminho de erro que não depende de rede (chave ausente).
"""
import pytest
from sqlalchemy import create_engine, text

from api import chat_sql
from api.chat_sql import SqlInvalidoError, _extrair_tabelas, executar_sql_seguro, validar_sql

# --------------------------------------------------------------------------
# validar_sql / _extrair_tabelas -- unitários, sem banco
# --------------------------------------------------------------------------


def test_consulta_valida_com_limit_dentro_do_maximo_passa_inalterada():
    sql = "SELECT nome_municipio, fec_aprox FROM municipio_mes WHERE ano = 2025 LIMIT 10"
    assert validar_sql(sql) == sql


def test_consulta_sem_limit_recebe_limit_padrao():
    sql = "SELECT nome_municipio FROM municipio_mes WHERE uf_sigla = 'SP'"
    resultado = validar_sql(sql)
    assert resultado == f"{sql} LIMIT {chat_sql.LIMITE_LINHAS_PADRAO}"


def test_consulta_com_limit_acima_do_maximo_e_capada():
    sql = "SELECT * FROM municipio_mes LIMIT 999999"
    resultado = validar_sql(sql)
    assert f"LIMIT {chat_sql.LIMITE_LINHAS_MAXIMO}" in resultado
    assert "999999" not in resultado


def test_join_explicito_com_tabela_nao_permitida_e_rejeitado():
    sql = "SELECT a.* FROM municipio_mes a JOIN pg_stat_activity b ON a.ano = b.pid"
    with pytest.raises(SqlInvalidoError):
        validar_sql(sql)


def test_join_por_virgula_com_tabela_nao_permitida_e_rejeitado():
    """Regressão do primeiro bug encontrado na auto-revisão: a versão
    anterior de `_extrair_tabelas` só pegava o identificador imediatamente
    depois de FROM/JOIN, então `FROM a, b` (join por vírgula) deixava `b`
    passar sem ser visto."""
    sql = "SELECT * FROM municipio_mes, pg_shadow LIMIT 5"
    with pytest.raises(SqlInvalidoError, match="pg_shadow"):
        validar_sql(sql)


def test_subquery_aninhada_com_tabela_nao_permitida_e_rejeitada():
    """Regressão do segundo bug: a primeira versão via sqlparse só
    percorria o nível superior da árvore de tokens, então uma tabela dentro
    de `WHERE x IN (SELECT ...)` (dentro de um grupo `Parenthesis`/`Where`)
    escapava da whitelist."""
    sql = "SELECT * FROM municipio_mes WHERE codigo_ibge_resolvido IN (SELECT codigo FROM outra_tabela) LIMIT 5"
    with pytest.raises(SqlInvalidoError, match="outra_tabela"):
        validar_sql(sql)


def test_subquery_duplamente_aninhada_e_rejeitada():
    sql = (
        "SELECT * FROM municipio_mes WHERE codigo_ibge_resolvido IN ("
        "SELECT codigo FROM a WHERE valor IN (SELECT id FROM b)"
        ") LIMIT 5"
    )
    tabelas = _extrair_tabelas(sql)
    assert {"municipio_mes", "a", "b"} <= tabelas
    with pytest.raises(SqlInvalidoError):
        validar_sql(sql)


def test_union_com_tabela_nao_permitida_e_rejeitado():
    sql = "SELECT codigo_ibge_resolvido FROM municipio_mes UNION SELECT usename FROM pg_user LIMIT 5"
    with pytest.raises(SqlInvalidoError, match="pg_user"):
        validar_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO municipio_mes (ano) VALUES (2099)",
        "UPDATE municipio_mes SET ano = 9999",
        "DELETE FROM municipio_mes",
        "DROP TABLE municipio_mes",
        "SELECT * FROM municipio_mes; DROP TABLE municipio_mes",
        "SELECT pg_sleep(10)",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM pg_catalog.pg_tables",
    ],
)
def test_consultas_perigosas_sao_rejeitadas(sql):
    with pytest.raises(SqlInvalidoError):
        validar_sql(sql)


def test_string_vazia_e_rejeitada():
    with pytest.raises(SqlInvalidoError):
        validar_sql("")


def test_consulta_sem_from_e_rejeitada():
    """Sem FROM/JOIN não há como confirmar que só `municipio_mes` foi
    referenciada -- rejeitar por padrão (fail-closed), não assumir que está ok."""
    with pytest.raises(SqlInvalidoError):
        validar_sql("SELECT 1")


def test_instrucao_nao_select_e_rejeitada_mesmo_sem_palavra_proibida():
    """`EXPLAIN`/`SHOW` não caem na regex de palavras proibidas, mas também
    não são SELECT -- get_type() precisa pegar isso independentemente."""
    with pytest.raises(SqlInvalidoError):
        validar_sql("EXPLAIN SELECT * FROM municipio_mes")


def test_consulta_legitima_com_agregacao_e_group_by_passa():
    sql = (
        "SELECT uf_sigla, AVG(fec_aprox) AS media FROM municipio_mes "
        "WHERE ano = 2025 GROUP BY uf_sigla ORDER BY media DESC LIMIT 27"
    )
    assert validar_sql(sql) == sql


def test_gerar_sql_sem_chave_configurada_levanta_erro_claro(monkeypatch):
    monkeypatch.setattr(chat_sql.config, "GEMINI_API_KEY", "")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        chat_sql.gerar_sql("quantos municipios existem?")


# --------------------------------------------------------------------------
# executar_sql_seguro -- integração contra Postgres real (pulado se
# indisponível, mesmo padrão de tests/test_load_db.py)
# --------------------------------------------------------------------------

_URL_READONLY_TESTE = "postgresql://continua_readonly:continua_readonly@localhost:5432/continua"
_URL_ESCRITA_TESTE = "postgresql://continua:continua@localhost:5432/continua"


def _acessivel(url: str) -> bool:
    try:
        with create_engine(url).connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def engine_leitura_real():
    if not _acessivel(_URL_READONLY_TESTE):
        pytest.skip(
            "Postgres local com o role 'continua_readonly' indisponivel (rode "
            "db/readonly_role.sql contra um Postgres real primeiro, ver docs/DEVLOG.md) "
            "-- teste de integracao pulado, sem depender de infra externa no CI."
        )
    return create_engine(_URL_READONLY_TESTE)


def test_executar_sql_seguro_retorna_dados_reais(engine_leitura_real):
    resultado = executar_sql_seguro(
        "SELECT codigo_ibge_resolvido, nome_municipio, fec_aprox FROM municipio_mes "
        "WHERE codigo_ibge_resolvido = '1100015' ORDER BY ano, mes LIMIT 5",
        engine_leitura_real,
    )
    assert resultado.colunas == ["codigo_ibge_resolvido", "nome_municipio", "fec_aprox"]
    assert 0 < len(resultado.linhas) <= 5
    assert all(linha["codigo_ibge_resolvido"] == "1100015" for linha in resultado.linhas)
    # fec_aprox vem do Postgres como Decimal -- confirma que _valor_serializavel
    # converteu para float (json.dumps quebraria com Decimal).
    assert all(isinstance(linha["fec_aprox"], (float, type(None))) for linha in resultado.linhas)


def test_executar_sql_seguro_aplica_limit_padrao_quando_ausente(engine_leitura_real):
    resultado = executar_sql_seguro("SELECT codigo_ibge_resolvido FROM municipio_mes", engine_leitura_real)
    assert f"LIMIT {chat_sql.LIMITE_LINHAS_PADRAO}" in resultado.sql
    assert len(resultado.linhas) <= chat_sql.LIMITE_LINHAS_PADRAO


def test_executar_sql_seguro_rejeita_tabela_nao_permitida_sem_tocar_no_banco(engine_leitura_real):
    """A validação roda ANTES de abrir a conexão -- confirma que uma
    consulta reprovada nunca chega a ser executada (e não só que ela falha
    com algum erro genérico do driver)."""
    with pytest.raises(SqlInvalidoError):
        executar_sql_seguro("SELECT * FROM pg_stat_activity LIMIT 5", engine_leitura_real)


def test_role_readonly_nao_consegue_escrever_mesmo_bypassando_validar_sql(engine_leitura_real):
    """Prova a camada 3 (role Postgres dedicado, ver db/readonly_role.sql)
    de forma independente de `validar_sql` -- mesmo chamando o Postgres
    direto, sem passar pela validação estática do módulo, a permissão do
    role sozinha já impede a escrita. Complementa (não substitui) os testes
    de `validar_sql` acima, que garantem que esse caminho nem é alcançado
    em uso normal."""
    with pytest.raises(Exception, match="permission denied"):
        with engine_leitura_real.connect() as conexao:
            with conexao.begin():
                conexao.execute(text("INSERT INTO municipio_mes (codigo_ibge_resolvido) VALUES ('0000000')"))


def test_role_readonly_nao_consegue_dropar_tabela(engine_leitura_real):
    with pytest.raises(Exception, match="must be owner|permission denied"):
        with engine_leitura_real.connect() as conexao:
            with conexao.begin():
                conexao.execute(text("DROP TABLE municipio_mes"))
