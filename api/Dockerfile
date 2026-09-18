# Build a partir da RAIZ do repositorio: docker compose faz isso
# automaticamente (ver docker-compose.yml, servico "api", context: .) porque
# a API importa modulos de ml/ (features.py, baseline.py, modelos.py) alem
# do proprio pacote api/.
FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY api/ ./api/
COPY ml/ ./ml/
# ml/mapa.py (mapa de clusters geograficos, Dia 6 extensao) le
# data/reference/municipios.csv (lat/lon por municipio) direto do disco na
# inicializacao -- so essa subpasta pequena e versionada, nao data/raw ou
# data/processed (grandes e ignorados pelo git).
COPY data/reference/ ./data/reference/

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
