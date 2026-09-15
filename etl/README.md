# etl/

Ingestão e limpeza dos dados de interrupções de energia da ANEEL.

## Módulos

- `config.py` — caminhos e constantes (URLs da ANEEL, nomes de colunas do schema real).
- `build_reference.py` — constrói `data/reference/municipios.csv` (código IBGE → UF/região) a partir do repositório público [`kelvins/municipios-brasileiros`](https://github.com/kelvins/municipios-brasileiros). Usado hoje só como lookup auxiliar de **região** — ver `ibge.py`.
- `download.py` — baixa os Parquet anuais da ANEEL para `data/raw/`, e o bridge conjunto→município (`data/raw/indqual_municipio.csv`). Idempotente (compara o tamanho do arquivo antes de rebaixar).
- `ibge.py` — cruza conjunto de unidades consumidoras (`IdeConjuntoUnidadeConsumidora` -- o dataset de interrupções não publica município/UF diretamente) com o dataset **"IndQual Município"** da ANEEL, que faz esse de-para. Um mesmo conjunto pode atender mais de um município (40,5% dos casos reais) — `fanout_municipio` distribui a linha (já agregada, ver `aggregate.py`) para cada município atendido, com um peso (`peso_evento = 1/n_municipios_no_conjunto`) para não inflar o total nacional. Ver o docstring do módulo para o histórico completo dessa descoberta e a decisão de projeto.
- `clean.py` — calcula duração de cada interrupção, deriva `ano`/`mes` de `DatInicioInterrupcao`, sinaliza interrupções programadas (sem descartar), e normaliza o campo de causa (`DscFatoGeradorInterrupcao`, que vem com formatação inconsistente). Não faz o cruzamento com município -- isso é responsabilidade de `aggregate.py`/`ibge.py`, depois de uma primeira agregação (ver abaixo).
- `aggregate.py` — agrega o dataset limpo em **dois níveis**: primeiro evento → conjunto × mês (poucas centenas de milhares de linhas), depois faz o fan-out para município (`etl.ibge.fanout_municipio`) e agrega de novo para o grão **município × mês**, com indicadores próprios (`fec_aprox`, `dec_aprox_horas`) e contagem ponderada de causas por origem. Fazer o fan-out direto no nível evento (~19 milhões de linhas) estourou a memória de uma máquina comum ao rodar contra o dataset real -- ver docstring do módulo e `docs/DEVLOG.md`.
- `pipeline.py` — orquestra tudo: lê os Parquet baixados, limpa, agrega (com o bridge), e escreve `data/processed/municipio_mes.{parquet,csv}`.

## ⚠️ Sobre o schema real dos dados

O pipeline foi desenhado inicialmente a partir da documentação oficial da ANEEL, que descreve campos como `CodMunicipioIBGE`, `QtdConsumidoresAfetados`/`QtdConsumidoresAtivos` e `AnoCompetencia`/`MesCompetencia`. **Ao processar o Parquet real, nenhum desses campos existe** — o schema publicado de fato é outro (18 colunas: `IdeConjuntoUnidadeConsumidora`, `NumUnidadeConsumidora`, `NumConsumidorConjunto`, `DscTipoInterrupcao`, `IdeMotivoInterrupcao`, `DscFatoGeradorInterrupcao`, etc.). O código em `config.py`/`clean.py`/`ibge.py`/`aggregate.py` já reflete o schema real, confirmado rodando `python -m etl.download` + `python -m etl.pipeline` contra o servidor de verdade. O histórico completo dessa descoberta (e das decisões tomadas por causa dela) está em `docs/DEVLOG.md`.

Limitações que seguem documentadas como decisões de projeto, não bugs:
- **Fan-out conjunto→município**: quando um conjunto atende mais de um município, o mesmo evento é contado fracionado (`peso_evento`) em cada um — ver `ibge.py` e `docs/REQUISITOS.md`.
- **"Programada" no lugar de "expurgado"**: não existe `DscMotivoExpurgo` no schema real; `DscTipoInterrupcao` é o filtro análogo disponível, mas não é semanticamente idêntico ao conceito oficial de expurgo da ANEEL.
- **`IdeMotivoInterrupcao`** é mantido bruto (código numérico sem dicionário de dados publicado) — não decodificado.

Se o download falhar com 404, os IDs de recurso da ANEEL em `config.py` provavelmente rotacionaram — confira o [dataset no portal](https://dadosabertos.aneel.gov.br/dataset/interrupcoes-de-energia-eletrica-nas-redes-de-distribuicao) e atualize `ANEEL_PARQUET_RESOURCE_IDS`.

O bridge conjunto→município (`ANEEL_INDQUAL_MUNICIPIO_*` em `config.py`) já tem `resource_id` confirmado — `python -m etl.download` baixa `data/raw/indqual_municipio.csv` automaticamente, junto com os Parquet anuais. Se falhar com 404, o portal provavelmente rotacionou o `resource_id`; confira em [dadosabertos.aneel.gov.br/dataset/indqual-municipio](https://dadosabertos.aneel.gov.br/dataset/indqual-municipio) e atualize `config.py`.

## Como rodar

```bash
pip install -r etl/requirements.txt

python -m etl.download --anos 2024,2025      # baixa os Parquet + o bridge conjunto->municipio -> data/raw/
python -m etl.pipeline --anos 2024,2025      # cruza + limpa + agrega -> data/processed/
```

(o `make download ANOS=2024,2025` e `make ingest ANOS=2024,2025` fazem a mesma coisa)

`data/reference/municipios.csv` já vem pronto no repositório — só rode `make reference` se quiser reconstruí-lo.

## Testes

```bash
pytest tests/test_clean.py tests/test_aggregate.py -v
```

Os testes não dependem de rede — usam fixtures sintéticas (`tests/fixtures/sample_raw_interrupcoes.csv` e `tests/fixtures/sample_indqual_municipio.csv`, já no schema real) e a tabela real de municípios/região já commitada. Cobrem especificamente as decisões de projeto documentadas em `docs/REQUISITOS.md`: interrupções programadas e com data inválida são mantidas (não descartadas); conjuntos que atendem mais de um município são distribuídos (fan-out) sem inflar o total nacional de eventos; municípios sem correspondência no join não somem silenciosamente da agregação (isso já pegou um bug real de `groupby` descartando grupos com chave nula por padrão). `tests/test_ibge.py` cobre a bridge e o fan-out isoladamente.
