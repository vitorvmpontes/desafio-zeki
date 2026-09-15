# Continua

Plataforma de análise e previsão de risco de interrupção de energia elétrica, construída sobre os dados públicos de interrupções da ANEEL — desenvolvida como desafio técnico do processo seletivo da Zeki.

> Transforma os despejos anuais e brutos da ANEEL em um ranking mensal de risco por município, com a previsão do mês seguinte, o histórico real e as causas que mais pesam — para priorizar fiscalização e manutenção preventiva antes do problema acontecer.

## Status do projeto

Este projeto está em desenvolvimento ativo (prazo de 7 dias corridos). O checklist abaixo é atualizado a cada etapa concluída — veja o histórico detalhado em [`docs/DEVLOG.md`](docs/DEVLOG.md).

- [x] Análise de requisitos e escopo (`docs/REQUISITOS.md`)
- [x] Esqueleto do repositório, Docker Compose e CI básico
- [x] Pipeline de ingestão e limpeza dos dados da ANEEL (`etl/`) — testado com fixture sintética; download ainda por validar contra o servidor real
- [ ] Análise exploratória e modelo de previsão de risco (`ml/`)
- [ ] API — indicadores, ranking e explicação (`api/`)
- [ ] Frontend — ranking e detalhe do município (`web/`)
- [ ] Automação mensal (GitHub Actions)
- [ ] Vídeo de demonstração

## O problema

A ANEEL disponibiliza dados públicos de interrupções de energia, mas em arquivos anuais brutos (ZIP/Parquet de até ~260 MB, 26 colunas com siglas pouco autoexplicativas, sem UF e sem duração calculada) e sem nenhuma API de consulta. Quem precisa entender e priorizar risco de interrupção — um analista de fiscalização da ANEEL, um gestor de manutenção de uma distribuidora — só enxerga indicadores históricos, medidos depois do problema já ter acontecido.

## A solução

O Continua ingere os dados da ANEEL mensalmente, calcula indicadores de continuidade por município, e usa um modelo de aprendizado de máquina para prever o risco de interrupção do mês seguinte — expondo tudo isso por uma API e um painel simples, com a explicação (causas dominantes) por trás de cada previsão.

A análise completa de problema, público, escopo e decisões está em [`docs/REQUISITOS.md`](docs/REQUISITOS.md), e a arquitetura técnica em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).

## Como rodar do zero

> Esta seção é mantida honesta durante o desenvolvimento: só documenta o que já funciona hoje. O objetivo final é `docker compose up` subir tudo (banco, API e frontend) com os dados de amostra já carregados.

Pré-requisitos: Docker e Docker Compose, Python 3.11+.

```bash
git clone https://github.com/vitorvmpontes/desafio-zeki.git
cd desafio-zeki
cp .env.example .env
docker compose up -d db

# pipeline de dados
pip install -r etl/requirements.txt -r requirements-dev.txt
python -m etl.download --anos 2024,2025    # precisa de internet ate dadosabertos.aneel.gov.br
python -m etl.pipeline --anos 2024,2025    # gera data/processed/municipio_mes.parquet
pytest                                      # roda a suite de testes (nao depende de rede)
```

Os demais serviços (`api`, `web`) serão adicionados aos comandos acima conforme forem implementados — acompanhe o checklist no topo deste README e o [`docs/DEVLOG.md`](docs/DEVLOG.md).

## Estrutura do repositório

```
desafio-zeki/
├── docs/            análise de requisitos, arquitetura e log de desenvolvimento
├── etl/             ingestão, limpeza e agregação dos dados da ANEEL
├── ml/              exploração de dados e treino do modelo de risco
├── api/             backend (FastAPI) — indicadores, ranking e previsão
├── web/             frontend — ranking e detalhe do município
├── tests/           testes automatizados (fixtures sintéticas, sem dependência de rede)
└── data/            dados (raw/processed ignorados pelo git; reference e sample versionadas)
```

## Fonte de dados

[Interrupções de Energia Elétrica nas Redes de Distribuição](https://dadosabertos.aneel.gov.br/dataset/interrupcoes-de-energia-eletrica-nas-redes-de-distribuicao) — Portal de Dados Abertos da ANEEL.

## Uso de IA no desenvolvimento

Ferramentas de IA (Claude) foram usadas como apoio ao desenvolvimento — aceleração de boilerplate e documentação. As decisões de produto, modelagem de dados e arquitetura são registradas e justificadas em `docs/`.
