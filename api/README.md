# api/

Backend em FastAPI: expõe os indicadores históricos, o ranking de risco previsto e a explicação por trás de cada previsão.

**Status:** planejado para o Dia 5 — ver [`docs/DEVLOG.md`](../docs/DEVLOG.md).

## Endpoints previstos

- `GET /municipios` — lista de municípios cobertos.
- `GET /municipios/{codigo_ibge}/historico` — série histórica de indicadores do município.
- `GET /municipios/{codigo_ibge}/previsao` — previsão de risco para o mês seguinte + causas dominantes.
- `GET /ranking?ano=&mes=` — ranking de municípios por risco previsto no período.

Documentação interativa (Swagger) disponível em `/docs` assim que a API subir.

## Como vai rodar

```bash
docker compose up -d db api
```

Detalhes completos (variáveis de ambiente, migrations) serão adicionados aqui conforme o código for implementado.
