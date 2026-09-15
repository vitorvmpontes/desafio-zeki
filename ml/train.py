"""Treina o modelo final de previsão de risco e salva o artefato consumido
pela API (Dia 5).

Diferente da avaliação em `ml/notebooks/04-modelagem.ipynb` (que separa
treino/teste por corte temporal para poder COMPARAR modelos de forma
honesta), este script treina o modelo escolhido (gradient boosting, ver
DEVLOG Dia 4) usando TODO o histórico disponível -- porque o objetivo aqui
não é validar, é produzir o melhor modelo possível para prever o mês
seguinte ao último mês do dataset, que é o uso real do produto.

Como rodar:

    python -m ml.train
    python -m ml.train --dados data/processed/municipio_mes.parquet --saida ml/artifacts

Gera:
    ml/artifacts/modelo_final.joblib      -- o modelo treinado (sklearn)
    ml/artifacts/modelo_final_metadata.json -- features, período de treino,
        métricas de validação de referência (do Dia 4) para a API expor
        junto com a previsão.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

from ml.features import (
    EXPOSURE,
    FEATURES_CATEGORICAS,
    FEATURES_NUMERICAS,
    TARGET,
    construir_dataset,
    filtrar_utilizaveis,
)
from ml.modelos import treinar_gbm

REPO_ROOT = Path(__file__).resolve().parent.parent
DADOS_PADRAO = REPO_ROOT / "data" / "processed" / "municipio_mes.parquet"
SAIDA_PADRAO = REPO_ROOT / "ml" / "artifacts"


def treinar(caminho_dados: Path, dir_saida: Path) -> None:
    df = pd.read_parquet(caminho_dados)
    dataset = construir_dataset(df)
    utilizaveis = filtrar_utilizaveis(dataset)

    print(f"{len(utilizaveis):,} linhas utilizáveis, alvo entre "
          f"{(utilizaveis['periodo'] + 1).min()} e {(utilizaveis['periodo'] + 1).max()}")

    modelo = treinar_gbm(utilizaveis)

    dir_saida.mkdir(parents=True, exist_ok=True)
    caminho_modelo = dir_saida / "modelo_final.joblib"
    joblib.dump(modelo, caminho_modelo)

    metadata = {
        "modelo": "HistGradientBoostingRegressor (loss=poisson)",
        "alvo": TARGET,
        "exposicao": EXPOSURE,
        "features_numericas": FEATURES_NUMERICAS,
        "features_categoricas": FEATURES_CATEGORICAS,
        "treinado_em_utc": datetime.now(timezone.utc).isoformat(),
        "linhas_treino": len(utilizaveis),
        "periodo_treino_alvo": {
            "inicio": str((utilizaveis["periodo"] + 1).min()),
            "fim": str((utilizaveis["periodo"] + 1).max()),
        },
        "metricas_de_validacao_referencia": (
            "ver ml/artifacts/modelagem_metricas.json (Dia 4) e "
            "ml/artifacts/baseline_metricas.json (Dia 3) -- este modelo foi "
            "validado por corte temporal ANTES deste treino final com todos "
            "os dados; os números lá continuam valendo como estimativa de "
            "desempenho esperado."
        ),
    }
    caminho_metadata = dir_saida / "modelo_final_metadata.json"
    with open(caminho_metadata, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"Modelo salvo em {caminho_modelo}")
    print(f"Metadata salva em {caminho_metadata}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dados", type=Path, default=DADOS_PADRAO, help="Caminho do municipio_mes.parquet")
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help="Diretório onde salvar o modelo e a metadata")
    args = parser.parse_args()
    treinar(args.dados, args.saida)


if __name__ == "__main__":
    main()
