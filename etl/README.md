# etl/

Ingestão e limpeza dos dados de interrupções de energia da ANEEL.

## Módulos

- `config.py` — caminhos e constantes (URLs da ANEEL, nomes de colunas).
- `build_reference.py` — constrói `data/reference/municipios.csv` (código IBGE → UF/região) a partir do repositório público [`kelvins/municipios-brasileiros`](https://github.com/kelvins/municipios-brasileiros). Raramente precisa ser rodado de novo — municípios brasileiros não mudam com frequência.
- `download.py` — baixa os Parquet anuais da ANEEL para `data/raw/`. Idempotente (compara o tamanho do arquivo antes de rebaixar).
- `ibge.py` — cruza `CodMunicipioIBGE` com a tabela de referência, com *fallback* de 7 para 6 dígitos (ver docstring de `join_municipio`).
- `clean.py` — calcula duração de cada interrupção, sinaliza expurgados e registros com data inválida (sem descartar nenhum), e aplica o join de município.
- `aggregate.py` — agrega o dataset limpo (nível evento) para o grão **município × mês**, com indicadores próprios (`fec_aprox`, `dec_aprox_horas`) e contagem de causas por origem.
- `pipeline.py` — orquestra tudo: lê os Parquet baixados, limpa, agrega, e escreve `data/processed/municipio_mes.{parquet,csv}`.

## ⚠️ Sobre rodar isso de verdade

`download.py` precisa de acesso real à internet para `dadosabertos.aneel.gov.br`. Esse acesso **não está disponível** no ambiente onde este pipeline foi escrito (um sandbox de rede restrita) — por isso `clean.py` e `aggregate.py` foram desenvolvidos e testados inteiramente com uma fixture sintética (`tests/fixtures/sample_raw_interrupcoes.csv`, com o schema real de 26 colunas da ANEEL, mas eventos fictícios), enquanto `download.py` ainda precisa ser validado contra o servidor real — o que exige rodá-lo num ambiente com internet sem essa restrição (sua máquina, ou o GitHub Actions).

Se o download falhar com 404, os IDs de recurso da ANEEL em `config.py` provavelmente rotacionaram — confira o [dataset no portal](https://dadosabertos.aneel.gov.br/dataset/interrupcoes-de-energia-eletrica-nas-redes-de-distribuicao) e atualize `ANEEL_PARQUET_RESOURCE_IDS`.

## Como rodar

```bash
pip install -r etl/requirements.txt

python -m etl.download --anos 2024,2025      # baixa os Parquet -> data/raw/
python -m etl.pipeline --anos 2024,2025      # limpa + agrega -> data/processed/
```

(o `make download ANOS=2024,2025` e `make ingest ANOS=2024,2025` fazem a mesma coisa)

`data/reference/municipios.csv` já vem pronto no repositório — só rode `make reference` se quiser reconstruí-lo.

## Testes

```bash
pytest tests/test_clean.py tests/test_aggregate.py -v
```

Os testes não dependem de rede — usam a fixture sintética e a tabela real de municípios já commitada. Cobrem especificamente as decisões de projeto documentadas em `docs/REQUISITOS.md`: registros expurgados e com data inválida são mantidos (não descartados); o mesmo município com código IBGE de 6 ou 7 dígitos não vira duas linhas diferentes; municípios sem correspondência no join não somem silenciosamente da agregação (isso já pegou um bug real de `groupby` descartando grupos com chave nula por padrão).
