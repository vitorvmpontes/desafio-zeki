# Log de desenvolvimento

Registro cronológico do que foi feito e por quê — serve tanto de memória do projeto quanto de matéria-prima para o README e para o roteiro do vídeo final.

## Dia 1 — Fundação e requisitos

- Definida a análise de requisitos completa: problema, personas, critério de sucesso, escopo priorizado em MoSCoW e premissas assumidas (`docs/REQUISITOS.md`).
- Criado o esqueleto do repositório: `etl/`, `ml/`, `api/`, `web/`, `tests/`, `docs/`, `data/` (com `raw` e `processed` ignorados pelo git e `sample` versionada).
- Documentada a arquitetura de quatro camadas (dados → ML → API → frontend), com diagrama Mermaid (`docs/ARQUITETURA.md`).
- `docker-compose.yml` com o serviço de banco (Postgres) funcional; serviços de `api` e `web` serão adicionados conforme forem implementados, para o compose nunca ficar quebrado.
- Workflow de CI básico no GitHub Actions (lint) configurado, pronto para crescer conforme o código real entrar.
- Convenção estabelecida: cada módulo (`etl/`, `ml/`, `api/`, `web/`) mantém seu próprio `README.md` com propósito e como rodar aquela parte isoladamente; este arquivo (`DEVLOG.md`) registra o histórico geral, dia a dia.

**Próximo passo (Dia 2):** pipeline de ingestão — download dos Parquet anuais da ANEEL, limpeza, decisão sobre registros expurgados, join com a tabela de municípios do IBGE, e geração do dataset agregado município-mês.
