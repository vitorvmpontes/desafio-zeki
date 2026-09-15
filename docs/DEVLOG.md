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

## Dia 2 (atualização) — descoberta do schema real e reescrita do join de município

- `python -m etl.download --anos 2024,2025` rodou com sucesso contra o servidor real da ANEEL (18.926.623 eventos brutos carregados, 2024+2025). Essa parte do pipeline estava correta desde o Dia 2.
- `python -m etl.pipeline --anos 2024,2025` **falhou** com `KeyError: 'QtdConsumidoresAfetados'`. Investigação (comparando `df.columns` reais com as constantes assumidas em `etl/config.py`) revelou que a documentação oficial da ANEEL usada para desenhar o pipeline descreve um schema que **não é o schema realmente publicado no Parquet**: não existe `CodMunicipioIBGE`, `QtdConsumidoresAfetados`/`QtdConsumidoresAtivos`, `AnoCompetencia`/`MesCompetencia`, nem a quebra de causa em 4 colunas. O schema real (18 colunas, idêntico em 2024 e 2025) usa `IdeConjuntoUnidadeConsumidora`, `NumUnidadeConsumidora`, `NumConsumidorConjunto`, `NumAno`, `DscTipoInterrupcao`, `IdeMotivoInterrupcao`, `DscFatoGeradorInterrupcao` (causa em texto livre único), entre outros.
- **Maior implicação**: sem `CodMunicipioIBGE`, o dataset de interrupções não identifica município nenhum diretamente — só o conjunto de unidades consumidoras. Localizado o dataset separado da ANEEL ["IndQual Município"](https://dadosabertos.aneel.gov.br/dataset/indqual-municipio), que publica o de-para conjunto → município/UF (mas não região).
- **Achado não previsto ao decidir usar esse bridge**: a relação conjunto → município **não é 1:1**. Dos 15.162 conjuntos, 6.135 (40,5%) atendem mais de um município (distribuição: 9.027 atendem exatamente 1; 1.681 atendem 2; 1.076 atendem 3; caindo progressivamente até 179 que atendem 10). Ou seja, um único conjunto frequentemente cobre uma cidade e partes de cidades vizinhas — não é um caso de borda, é quase metade dos casos.
- **Decisão tomada**: em vez de escolher arbitrariamente um "município principal" por conjunto (o que enviesaria o ranking de risco sem base nenhuma nos dados), cada evento é distribuído (fan-out) para todos os municípios do seu conjunto na hora do join, com um peso `peso_evento = 1/n_municipios_no_conjunto`. Na agregação, contagens de eventos e números de consumidores (grandezas "extensivas") são somados ponderados por esse peso — o total nacional de eventos não fica inflado —, enquanto a duração da interrupção (grandeza "intensiva") entra inteira em cada município afetado. Implementado em `etl/ibge.py` (`join_conjunto_municipio`) e `etl/aggregate.py`.
- **Outras adaptações do schema real**:
  - `ano`/`mes` passaram a ser derivados de `DatInicioInterrupcao` (não existe campo de competência separado).
  - O conceito de "registro expurgado" (`DscMotivoExpurgo`) não tem equivalente no schema real — substituído por uma flag `programada`, derivada de `DscTipoInterrupcao` (Programada / Não Programada). Documentado explicitamente que essa não é a mesma coisa que o expurgo oficial da ANEEL (`docs/REQUISITOS.md`).
  - `IdeMotivoInterrupcao` (código numérico) é mantido bruto — sem dicionário de dados publicado, decodificá-lo seria inventar uma interpretação.
  - `DscFatoGeradorInterrupcao` (causa) chega em texto livre com formatação real inconsistente — mesma causa escrita como `"INTERNA;NAO PROGRAMADA;PROPRIAS DO SISTEMA;FALHA DE MATERIAL OU EQUIPAMENTO"` e como `"Interna-Não programada-Próprias do sistema-Falha de material ou equipamento"`. Implementada `etl.clean.normalizar_causa` (maiúsculas, sem acento, separador único) antes de qualquer contagem por causa.
  - `SigAgente` vem com espaços em branco à direita nos dados reais — adicionado `.str.strip()`.
- Toda a suite de testes (fixtures + `test_clean.py`/`test_aggregate.py`) foi reconstruída do zero com o schema real de 18 colunas (incluindo um caso de conjunto compartilhado entre dois municípios, para exercitar o fan-out) — 17 testes, `pytest`/`ruff` passando.
- **Limitação ainda aberta**: o `resource_id` de download automático do dataset "IndQual Município" ainda não foi confirmado em `etl/config.py` (`ANEEL_INDQUAL_MUNICIPIO_RESOURCE_ID`) — até lá, o arquivo precisa ser baixado manualmente e salvo em `data/raw/indqual_municipio.csv` (ver `etl/README.md`).

**Próximo passo:** confirmar o `resource_id` do bridge "IndQual Município" para automatizar seu download, rodar `python -m etl.pipeline --anos 2024,2025` contra os 18,9M de eventos reais para validar o pipeline reescrito de ponta a ponta, e então seguir para o Dia 3 (análise exploratória e baseline do modelo).
