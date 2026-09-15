# etl/

Ingestão e limpeza dos dados de interrupções de energia da ANEEL.

**Status:** planejado para o Dia 2 — ver [`docs/DEVLOG.md`](../docs/DEVLOG.md).

## O que vai entrar aqui

- `download.py` — baixa os arquivos Parquet anuais publicados pela ANEEL.
- `clean.py` — limpeza e validação: cálculo de duração (`DatFimInterrupcao - DatInicioInterrupcao`), tratamento dos registros marcados em `DscMotivoExpurgo`, join de `CodMunicipioIBGE` com a tabela de municípios do IBGE para obter UF/nome.
- `aggregate.py` — agregação do dataset limpo (nível evento) para o grão município × mês usado pelo modelo e pela API.

## Como vai rodar

```bash
python -m etl.download --anos 2024,2025
python -m etl.clean
python -m etl.aggregate
```

Detalhes de execução completos serão adicionados aqui conforme o código for implementado.
