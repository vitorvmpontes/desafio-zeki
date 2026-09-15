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

## Dia 1 (atualização) — renomeação do produto

- Repositório remoto criado no GitHub como `desafio-zeki` (público).
- Produto renomeado de "Radar de Continuidade" para **Continua** — mais curto, e joga com o termo regulatório da própria ANEEL ("indicadores de continuidade"). Atualizado em `README.md` e nas variáveis do `.env.example` (banco de dados `continua`).
- Ajustadas as instruções de "como rodar do zero" no README para refletir o nome real do repositório (`desafio-zeki`), já que é diferente do nome do produto.

## Dia 2 — Pipeline de ingestão

- Construída `data/reference/municipios.csv`: tabela de municípios/UF/região (fonte: [`kelvins/municipios-brasileiros`](https://github.com/kelvins/municipios-brasileiros)), usada para resolver o que a ANEEL não publica — UF e nome do município a partir do `CodMunicipioIBGE`. Documentada a escolha de uma tabela estática versionada em vez de consultar a API do IBGE em tempo real (`etl/build_reference.py`).
- Implementado `etl/clean.py`: cálculo de duração a partir de início/fim, sinalização (não descarte) de registros expurgados e de registros com data inválida.
- Implementado `etl/ibge.py`: join do código IBGE com *fallback* de 7 para 6 dígitos, com uma chave canônica (`codigo_ibge_resolvido`) — necessária para não contar o mesmo município duas vezes quando ele aparece com códigos de tamanhos diferentes em meses diferentes.
- Implementado `etl/aggregate.py`: agregação para o grão município × mês, com indicadores próprios (`fec_aprox`, `dec_aprox_horas`) e contagem de causas por origem.
- Implementado `etl/download.py`: download idempotente dos Parquet anuais da ANEEL (URLs reais levantadas manualmente no portal).
- Escrita uma suite de 13 testes (`tests/test_clean.py`, `tests/test_aggregate.py`) usando uma fixture sintética com o schema real de 26 colunas da ANEEL — **os testes já pegaram e corrigiram dois bugs reais**: (1) o agrupamento estava usando o código IBGE bruto em vez da chave canônica, o que duplicaria municípios reportados com 6 e 7 dígitos em meses diferentes; (2) o `groupby` do pandas descarta por padrão qualquer grupo cuja chave contenha `NaN`, o que estava fazendo municípios sem correspondência no join sumirem silenciosamente da agregação — violando a decisão de nunca descartar esses registros (`docs/REQUISITOS.md`).
- **Limitação conhecida e documentada:** o ambiente de desenvolvimento não tem acesso de rede a `dadosabertos.aneel.gov.br` (nem à API do IBGE) — por isso `clean.py`/`aggregate.py` foram validados com dados sintéticos, e `download.py` ainda precisa ser rodado num ambiente com internet irrestrita (a máquina de quem for rodar o projeto, ou o GitHub Actions) para ser validado contra o servidor real. Ver `etl/README.md`.

**Próximo passo (Dia 3):** análise exploratória sobre os dados reais (assim que o download for validado) e baseline do modelo de risco.
