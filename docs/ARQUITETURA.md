# Arquitetura

Quatro camadas — dados, ML, backend e frontend — conectadas por um único fluxo, atualizado mensalmente.

```mermaid
flowchart LR
    ANEEL["ANEEL\nParquet mensal"] --> ETL["ETL\nlimpeza · join IBGE"]
    ETL --> DB[("Postgres\nmunicípio × mês")]
    DB --> TRAIN["Treino do modelo\noffline · notebooks"]
    TRAIN --> API["API — FastAPI\nindicadores · ranking"]
    DB --> API
    API --> WEB["Frontend\nranking + detalhe"]
    ACTIONS["GitHub Actions\ncron mensal"] -.dispara.-> ETL
```

## Camadas

**ETL (`etl/`)** — baixa os arquivos Parquet publicados anualmente pela ANEEL, limpa e valida os registros, calcula a duração de cada interrupção (a partir de `DatInicioInterrupcao`/`DatFimInterrupcao`, que não vêm prontos), cruza o conjunto de unidades consumidoras de cada evento (`IdeConjuntoUnidadeConsumidora`) com o dataset "IndQual Município" para obter UF/nome do município — distribuindo (fan-out) o evento entre todos os municípios do conjunto quando ele atende mais de um —, e agrega tudo em um dataset município × mês. A ingestão é idempotente: pode ser executada de novo com segurança quando a ANEEL publica uma atualização mensal.

**ML (`ml/`)** — exploração dos dados e treino do modelo de previsão de risco (volume esperado de interrupções por município no mês seguinte). Comparação obrigatória contra um baseline ingênuo (persistência sazonal), validação por corte temporal (nunca embaralhar meses entre treino e teste), e interpretabilidade (importância de features / SHAP) ligada diretamente às recomendações de mitigação.

**API (`api/`)** — FastAPI servindo os indicadores históricos, o ranking de risco previsto e a explicação por trás de cada previsão, lendo do Postgres e do artefato do modelo treinado.

**Web (`web/`)** — frontend mínimo consumindo a API: ranking de municípios por risco e uma tela de detalhe com histórico real vs. previsto e causas dominantes.

**Automação (`.github/workflows/`)** — workflow agendado mensalmente que reexecuta o ETL contra os dados atualizados da ANEEL e republica o ranking, sem depender de infraestrutura paga rodando continuamente durante a avaliação do desafio.

## Decisões de engenharia

- **Município resolvido via bridge conjunto→município**, não via código IBGE direto: o dataset de interrupções só publica o conjunto de unidades consumidoras (`IdeConjuntoUnidadeConsumidora`) — o de-para para município vem do dataset separado "IndQual Município" (ver `etl/ibge.py`).
- **Fan-out para conjuntos compartilhados entre municípios**: 40,5% dos conjuntos reais atendem mais de um município. Cada evento é distribuído entre todos eles, com peso `1/n_municipios_no_conjunto`, para não escolher arbitrariamente um "município principal" nem inflar o total nacional de eventos.
- **Interrupções programadas** (`DscTipoInterrupcao`): mantidas com uma flag em vez de descartadas, para não distorcer silenciosamente os indicadores — substitui o conceito de "expurgado" da documentação oficial, que não tem campo equivalente no schema real.
- **Grão município-mês**: reduz um dataset de milhões de eventos brutos para dezenas de milhares de linhas agregadas — permite usar o histórico completo (2017–2026) sem custo computacional relevante.
- **Validação temporal**: treino até o mês T, teste em T+1 em diante.
- **Recorrência sem infraestrutura paga**: pipeline idempotente + workflow mensal demonstrável via disparo manual (`workflow_dispatch`).

Esta arquitetura evolui conforme o projeto avança — mudanças relevantes são registradas em [`DEVLOG.md`](DEVLOG.md).
