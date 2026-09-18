"""Gera ml/artifacts/importancia_features.json -- os números por trás da
análise de interpretabilidade da seção 3 de `04-modelagem.ipynb`
(fatorada em `ml/interpretabilidade.py`), para a API (Dia 5) consumir sem
recalcular nada em tempo de requisição.

Reproduz exatamente o recorte do notebook: treina o gradient boosting só
com o treino (corte temporal, ano_corte=2025), avalia a importância por
permutação no teste restrito aos municípios com histórico completo (mesma
população do baseline do Dia 3) -- NÃO usa `modelo_final.joblib` (esse é
treinado com todo o histórico, sem held-out, ver `ml/train.py`).

Rode de qualquer diretório com: python3 ml/scripts/exportar_importancia.py
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # permite rodar de qualquer diretorio, ex: python3 ml/scripts/exportar_importancia.py

import pandas as pd  # noqa: E402

from ml.features import construir_dataset, divisao_temporal  # noqa: E402
from ml.interpretabilidade import importancia_por_permutacao  # noqa: E402
from ml.modelos import treinar_gbm  # noqa: E402

DATA_PATH = REPO_ROOT / "data" / "processed" / "municipio_mes.parquet"
ARTIFACTS_DIR = REPO_ROOT / "ml" / "artifacts"
OUTPUT_JSON = ARTIFACTS_DIR / "importancia_features.json"


def main() -> None:
    df = pd.read_parquet(DATA_PATH)
    dataset = construir_dataset(df)
    treino, teste = divisao_temporal(dataset, ano_corte=2025)

    contagem_meses = dataset.groupby("codigo_ibge_resolvido")["periodo"].nunique()
    completos = set(contagem_meses[contagem_meses == 24].index)
    teste_comp = teste[teste["codigo_ibge_resolvido"].isin(completos)].copy()

    gbm = treinar_gbm(treino)
    importancia = importancia_por_permutacao(gbm, teste_comp)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "descricao": (
            "Importancia por permutacao do gradient boosting validado por corte "
            "temporal (treino ate 2024, teste em 2025, municipios com historico "
            "completo) -- NAO do modelo_final.joblib servido pela API, que e "
            "treinado com todo o historico e nao tem held-out. Ver "
            "ml/interpretabilidade.py e ml/notebooks/04-modelagem.ipynb."
        ),
        "metrica": "aumento no MAE ao embaralhar a feature (neg_mean_absolute_error)",
        "n_repeticoes": 5,
        "linhas_teste_avaliadas": len(teste_comp),
        "importancias": importancia.to_dict(orient="records"),
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"OK: {OUTPUT_JSON} salvo.")
    print(importancia.round(6).to_string(index=False))


if __name__ == "__main__":
    main()
