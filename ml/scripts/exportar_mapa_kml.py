"""Gera ml/artifacts/mapa_clusters.kml -- o arquivo KML real de clusters de
qualidade de serviço por município, pedido explícito do usuário: "criar um
mapa mesmo, usando um arquivo KML gerado a partir de alguma clusterização
nos dados" (ver `ml/mapa.py` para a lógica completa).

A API também recalcula este mapa em memória a cada inicialização
(`api/servico.py::montar_estado`, sempre a partir do painel real carregado
do Postgres, igual a `desempenho_geografico`) -- este script existe para
deixar um artefato COMMITTED, inspecionável e abrível direto num
visualizador de KML (Google Earth, Google Maps "Meus mapas", QGIS), sem
precisar subir a API -- mesmo padrão de `exportar_importancia.py`.

Rode de qualquer diretório com: python3 ml/scripts/exportar_mapa_kml.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # permite rodar de qualquer diretorio

import pandas as pd  # noqa: E402

from ml.mapa import mapa_clusters_kml  # noqa: E402

DATA_PATH = REPO_ROOT / "data" / "processed" / "municipio_mes.parquet"
ARTIFACTS_DIR = REPO_ROOT / "ml" / "artifacts"
OUTPUT_KML = ARTIFACTS_DIR / "mapa_clusters.kml"


def main() -> None:
    painel = pd.read_parquet(DATA_PATH)
    resultado = mapa_clusters_kml(painel)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_KML.write_text(resultado["kml"], encoding="utf-8")

    print(
        f"OK: {OUTPUT_KML} salvo "
        f"({resultado['n_municipios_no_mapa']} municipios, {resultado['n_clusters']} clusters)."
    )
    for linha in resultado["resumo_por_cluster"]:
        print(
            f"  {linha['severidade']:>9}: {linha['n_municipios']:4d} municipios | "
            f"fec_aprox medio {linha['fec_aprox_medio']:.4f} | "
            f"dec_aprox_horas medio {linha['dec_aprox_horas_medio']:.2f}h"
        )


if __name__ == "__main__":
    main()
