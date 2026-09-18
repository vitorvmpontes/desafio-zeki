-- Cria um usuário Postgres READ-ONLY dedicado ao chatbot text-to-SQL
-- (api/chat_sql.py) -- ele NUNCA deve usar o usuário principal (POSTGRES_USER
-- do .env), que tem permissão de escrita e é quem a automação mensal usa
-- pra recriar a tabela `municipio_mes` (ver .github/workflows/atualizacao-mensal.yml).
--
-- Rode este script UMA VEZ contra o banco (ajuste usuário/banco se você
-- mudou os defaults do .env):
--
--   Com docker compose (Postgres em container):
--     docker compose exec -T db psql -U continua -d continua < db/readonly_role.sql
--
--   Sem Docker (Postgres local, como usado pra validar este script):
--     psql -h localhost -U continua -d continua -f db/readonly_role.sql
--
-- Depois de rodar, defina no seu .env (ver .env.example):
--   DATABASE_URL_READONLY=postgresql://continua_readonly:continua_readonly@localhost:5432/continua
-- (trocando a senha abaixo por uma sua, se quiser -- o valor default aqui é
-- só pra rodar local, igual ao restante das credenciais deste desafio).
--
-- Requer que o usuário que roda este script tenha o atributo CREATEROLE
-- (no Postgres oficial do Docker Hub, o usuário definido em POSTGRES_USER já
-- nasce superuser, então isso funciona de primeira via `docker compose exec`).
-- Se dar "permission denied to create role", rode como o superuser do
-- cluster (ex.: `psql -U postgres`) -- foi o caso ao validar este script
-- neste ambiente de teste, onde o usuário "continua" não tinha CREATEROLE.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'continua_readonly') THEN
        CREATE ROLE continua_readonly LOGIN PASSWORD 'continua_readonly';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE continua TO continua_readonly;
GRANT USAGE ON SCHEMA public TO continua_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO continua_readonly;

-- IMPORTANTE, e fácil de esquecer: `etl.load_db` RECRIA a tabela
-- `municipio_mes` todo mês (if_exists="replace", ver etl/load_db.py) --
-- DROP + CREATE gera um objeto NOVO no Postgres, que NÃO herda o GRANT
-- acima na próxima atualização mensal (só valeria pra a tabela atual).
-- `ALTER DEFAULT PRIVILEGES` resolve isso de vez: concede SELECT
-- AUTOMATICAMENTE em qualquer tabela nova que o usuário "continua" (quem
-- roda etl.load_db, dono da tabela) criar dali em diante no schema public --
-- sobrevive a toda automação mensal futura, sem precisar rodar este script
-- de novo. Validado manualmente contra o Postgres real deste ambiente,
-- simulando um DROP + CREATE da tabela (ver docs/DEVLOG.md).
ALTER DEFAULT PRIVILEGES FOR ROLE continua IN SCHEMA public GRANT SELECT ON TABLES TO continua_readonly;
