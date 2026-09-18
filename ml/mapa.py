"""Mapa geográfico real de clusters de qualidade de serviço por município --
pedido explícito do usuário: "eu queria que você criasse um mapa mesmo,
usando um arquivo KML gerado a partir de alguma clusterização nos dados,
depois incorpore no site".

**O que é clusterizado**: as mesmas duas métricas normalizadas por
consumidor já usadas em `ml/priorizacao.py::hotspots_geograficos` --
`fec_aprox` médio (frequência) e `dec_aprox_horas` médio (duração) na
mesma janela dos últimos N meses. Reaproveitar essas métricas (em vez de
inventar outras) mantém a mesma leitura de "má qualidade de serviço, não
apenas escala" que já é a decisão de design documentada para hotspots --
o mapa é essa mesma análise, agora colocada no espaço.

**Como o KMeans é usado**: as duas métricas têm escalas bem diferentes
(fec_aprox é uma taxa pequena; dec_aprox_horas é em horas), então os dados
são padronizados por z-score antes do KMeans -- sem isso, a duração
dominaria a distância euclidiana sozinha. O id de cluster que o KMeans
atribui é arbitrário (depende só da inicialização aleatória, ver
`random_state` fixo para reprodutibilidade); por isso os clusters são
RE-ROTULADOS por severidade (crítico/alto/moderado/baixo) ordenando os
centroides pela soma das duas métricas padronizadas -- o cluster com o pior
centroide é sempre "crítico", nunca "cluster 2" ou outro id sem sentido.

**Fonte das coordenadas**: `data/reference/municipios.csv`
(`etl/build_reference.py`), a mesma tabela já usada no pipeline para
resolver região/UF -- estendida para carregar também `latitude`/`longitude`
(sede do município, já vinham no CSV bruto da fonte
`kelvins/municipios-brasileiros`, só não eram usadas até agora). Mesmo
fallback de código IBGE de 7 -> 6 dígitos de `etl/ibge.py::_resolver_regiao`.

**Limitação, mesma linha do resto do produto**: a coordenada é da SEDE do
município (a granularidade do próprio dado da ANEEL usado neste projeto,
que não identifica subestação/alimentador -- ver docstring de
`ml/priorizacao.py`), não o ponto exato de uma ocorrência de interrupção.
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
from sklearn.cluster import KMeans

from ml.priorizacao import COL_ID, TARGET, _janela_ultimos_meses

# Caminho resolvido localmente (em vez de importado de `etl.config`) --
# `ml/` nunca dependeu de `etl/` (ver `ml/analises.py`, que le seus proprios
# artefatos com caminho passado por parametro/resolvido localmente), e o
# container Docker da API so copia `api/` e `ml/` (ver `api/Dockerfile`),
# nao `etl/`. Importar `etl.config` aqui quebrou a API em produção
# (`ModuleNotFoundError: No module named 'etl'`) -- o `data/reference/`
# agora tambem e copiado para a imagem (ver `api/Dockerfile`), entao o
# caminho abaixo resolve corretamente tanto localmente quanto no container.
MUNICIPIOS_REFERENCE_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "municipios.csv"

N_CLUSTERS = 4
SEMENTE_ALEATORIA = 42

# Ordem do pior para o melhor -- reatribuída por severidade real do
# centroide (nao pelo id arbitrario do KMeans, ver docstring do modulo).
ROTULOS_SEVERIDADE = ["critico", "alto", "moderado", "baixo"]

# Cor no formato KML (aabbggrr -- alpha, azul, verde, vermelho, NAO rgb).
CORES_SEVERIDADE = {
    "critico": "ff0000d4",  # vermelho
    "alto": "ff0080ff",  # laranja
    "moderado": "ff00d7ff",  # amarelo
    "baixo": "ff2ecc40",  # verde
}


def carregar_coordenadas(path=MUNICIPIOS_REFERENCE_PATH) -> pd.DataFrame:
    """Lat/lon por município (sede), da tabela de referência versionada."""
    ref = pd.read_csv(path, dtype={"codigo_ibge_7": str, "codigo_ibge_6": str})
    return ref[["codigo_ibge_7", "codigo_ibge_6", "latitude", "longitude"]]


def _resolver_coordenadas(codigos: pd.Series, referencia: pd.DataFrame) -> pd.DataFrame:
    """Mesmo fallback de 7 -> 6 dígitos de `etl/ibge.py::_resolver_regiao`,
    aplicado aqui para resolver latitude/longitude a partir do
    `codigo_ibge_resolvido` do painel (que às vezes só tem 6 dígitos)."""
    ref_7 = referencia.set_index("codigo_ibge_7")[["latitude", "longitude"]]
    ref_6 = referencia.drop_duplicates("codigo_ibge_6").set_index("codigo_ibge_6")[["latitude", "longitude"]]

    codigos = codigos.astype(str)
    codigo_6 = codigos.str[:6]
    match_7 = codigos.map(ref_7.to_dict("index"))
    match_6 = codigo_6.map(ref_6.to_dict("index"))
    resolved = match_7.where(match_7.notna(), match_6)

    latitude = resolved.map(lambda v: v["latitude"] if isinstance(v, dict) else None)
    longitude = resolved.map(lambda v: v["longitude"] if isinstance(v, dict) else None)
    return pd.DataFrame({"latitude": latitude, "longitude": longitude})


def clusterizar_municipios(
    painel: pd.DataFrame,
    referencia_coordenadas: pd.DataFrame | None = None,
    ultimos_n_meses: int = 12,
    n_clusters: int = N_CLUSTERS,
    minimo_meses: int = 3,
    semente: int = SEMENTE_ALEATORIA,
) -> pd.DataFrame:
    """Clusteriza município por qualidade de serviço (fec_aprox/dec_aprox_horas
    médios, últimos `ultimos_n_meses`, mesma janela/métrica de
    `hotspots_geograficos`) via KMeans padronizado por z-score.

    Municípios sem coordenada resolvível na tabela de referência, ou com
    menos de `minimo_meses` de dado na janela, são excluídos -- não faz
    sentido colocar no mapa um ponto sem posição, nem estimar qualidade de
    serviço com dado insuficiente (mesmo cuidado de `hotspots_geograficos`).
    """
    if referencia_coordenadas is None:
        referencia_coordenadas = carregar_coordenadas()

    janela = _janela_ultimos_meses(painel, ultimos_n_meses)
    agregado = (
        janela.groupby(COL_ID)
        .agg(
            nome_municipio=("nome_municipio", "last"),
            uf_sigla=("uf_sigla", "last"),
            regiao=("regiao", "last"),
            fec_aprox_medio=(TARGET, "mean"),
            dec_aprox_horas_medio=("dec_aprox_horas", "mean"),
            n_meses=(TARGET, "count"),
        )
        .reset_index()
    )
    agregado = agregado[agregado["n_meses"] >= minimo_meses].copy()

    coords = _resolver_coordenadas(agregado[COL_ID], referencia_coordenadas)
    agregado = pd.concat([agregado.reset_index(drop=True), coords.reset_index(drop=True)], axis=1)
    agregado = agregado.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)

    colunas_saida = [
        COL_ID, "nome_municipio", "uf_sigla", "regiao", "fec_aprox_medio",
        "dec_aprox_horas_medio", "latitude", "longitude", "cluster", "severidade",
    ]
    if agregado.empty:
        return pd.DataFrame(columns=colunas_saida)

    X = agregado[["fec_aprox_medio", "dec_aprox_horas_medio"]].to_numpy()
    media, desvio = X.mean(axis=0), X.std(axis=0)
    desvio[desvio == 0] = 1.0
    X_padronizado = (X - media) / desvio

    k = max(1, min(n_clusters, agregado[COL_ID].nunique()))
    kmeans = KMeans(n_clusters=k, random_state=semente, n_init=10)
    agregado["cluster"] = kmeans.fit_predict(X_padronizado)

    # soma das duas metricas padronizadas do centroide: quanto maior, pior
    # (fec_aprox e dec_aprox_horas medios sao "quanto maior, pior" os dois).
    score_centroide = pd.Series(kmeans.cluster_centers_.sum(axis=1))
    ordem_do_pior_para_o_melhor = score_centroide.sort_values(ascending=False).index
    rotulos = ROTULOS_SEVERIDADE[:k] if k <= len(ROTULOS_SEVERIDADE) else [f"grupo_{i + 1}" for i in range(k)]
    mapa_rotulo = dict(zip(ordem_do_pior_para_o_melhor, rotulos))
    agregado["severidade"] = agregado["cluster"].map(mapa_rotulo)

    return agregado[colunas_saida].sort_values(
        ["severidade", "fec_aprox_medio"], ascending=[True, False]
    ).reset_index(drop=True)


def gerar_kml(
    clusters: pd.DataFrame, titulo: str = "Continua -- clusters de qualidade de servico por municipio"
) -> str:
    """Gera o XML de um arquivo KML de verdade -- um Placemark por
    município, agrupado em pastas por severidade e estilizado por cor
    (crítico=vermelho .. baixo=verde), pronto para abrir no Google
    Earth/Maps ou ser servido pela API para o mapa do site.

    Ordem das coordenadas é `longitude,latitude[,altitude]`, conforme a
    especificação OGC do KML -- INVERTIDA em relação à ordem usual
    "latitude, longitude" que o resto do produto usa; erro fácil de
    cometer, por isso registrado aqui explicitamente.
    """
    blocos_estilo = []
    for rotulo, cor in CORES_SEVERIDADE.items():
        blocos_estilo.append(
            f'    <Style id="estilo_{rotulo}">\n'
            f"      <IconStyle>\n"
            f"        <color>{cor}</color>\n"
            f"        <scale>1.0</scale>\n"
            f"        <Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>\n"
            f"      </IconStyle>\n"
            f"    </Style>"
        )

    blocos_pasta = []
    for rotulo in ROTULOS_SEVERIDADE:
        grupo = clusters[clusters["severidade"] == rotulo]
        if grupo.empty:
            continue
        placemarks = []
        for row in grupo.to_dict(orient="records"):
            nome = escape(str(row["nome_municipio"]))
            descricao = escape(
                f"UF: {row['uf_sigla']} | Regiao: {row['regiao']} | "
                f"fec_aprox medio: {row['fec_aprox_medio']:.4f} | "
                f"dec_aprox_horas medio: {row['dec_aprox_horas_medio']:.2f}h"
            )
            placemarks.append(
                f"      <Placemark>\n"
                f"        <name>{nome}</name>\n"
                f"        <styleUrl>#estilo_{rotulo}</styleUrl>\n"
                f"        <description>{descricao}</description>\n"
                f"        <ExtendedData>\n"
                f'          <Data name="codigo_ibge"><value>{escape(str(row[COL_ID]))}</value></Data>\n'
                f'          <Data name="uf"><value>{escape(str(row["uf_sigla"]))}</value></Data>\n'
                f'          <Data name="regiao"><value>{escape(str(row["regiao"]))}</value></Data>\n'
                f'          <Data name="fec_aprox_medio"><value>{row["fec_aprox_medio"]:.5f}</value></Data>\n'
                f'          <Data name="dec_aprox_horas_medio"><value>{row["dec_aprox_horas_medio"]:.3f}</value></Data>\n'
                f'          <Data name="severidade"><value>{rotulo}</value></Data>\n'
                f"        </ExtendedData>\n"
                f"        <Point>\n"
                f"          <coordinates>{row['longitude']:.6f},{row['latitude']:.6f},0</coordinates>\n"
                f"        </Point>\n"
                f"      </Placemark>"
            )
        blocos_pasta.append(
            f"    <Folder>\n"
            f"      <name>{rotulo.capitalize()} ({len(grupo)} municipios)</name>\n"
            + "\n".join(placemarks)
            + "\n    </Folder>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "  <Document>\n"
        f"    <name>{escape(titulo)}</name>\n"
        + "\n".join(blocos_estilo)
        + "\n"
        + "\n".join(blocos_pasta)
        + "\n  </Document>\n</kml>"
    )


def mapa_clusters_kml(painel: pd.DataFrame, ultimos_n_meses: int = 12, n_clusters: int = N_CLUSTERS) -> dict:
    """Monta o payload completo do mapa: clusteriza, gera o KML e um resumo
    por cluster -- usado tanto pela API (`GET /mapa`, `GET /mapa/kml`)
    quanto pelo script que gera o artefato committed
    (`ml/scripts/exportar_mapa_kml.py`)."""
    clusters = clusterizar_municipios(painel, ultimos_n_meses=ultimos_n_meses, n_clusters=n_clusters)
    kml = gerar_kml(clusters)

    resumo = (
        clusters.groupby("severidade")
        .agg(
            n_municipios=(COL_ID, "count"),
            fec_aprox_medio=("fec_aprox_medio", "mean"),
            dec_aprox_horas_medio=("dec_aprox_horas_medio", "mean"),
        )
        .reindex(ROTULOS_SEVERIDADE)
        .dropna(how="all")
        .reset_index()
    )

    return {
        "janela_meses": ultimos_n_meses,
        "n_clusters": int(clusters["severidade"].nunique()),
        "n_municipios_no_mapa": int(len(clusters)),
        "municipios": [
            {
                "codigo_ibge": row[COL_ID],
                "nome": row["nome_municipio"],
                "uf": row["uf_sigla"],
                "regiao": row["regiao"],
                "latitude": round(float(row["latitude"]), 6),
                "longitude": round(float(row["longitude"]), 6),
                "fec_aprox_medio": round(float(row["fec_aprox_medio"]), 5),
                "dec_aprox_horas_medio": round(float(row["dec_aprox_horas_medio"]), 3),
                "severidade": row["severidade"],
            }
            for row in clusters.to_dict(orient="records")
        ],
        "resumo_por_cluster": [
            {
                "severidade": row["severidade"],
                "n_municipios": int(row["n_municipios"]),
                "fec_aprox_medio": round(float(row["fec_aprox_medio"]), 5),
                "dec_aprox_horas_medio": round(float(row["dec_aprox_horas_medio"]), 3),
            }
            for row in resumo.to_dict(orient="records")
        ],
        "kml": kml,
        "nota_metodologica": (
            # Versao enxuta (ver docs/DEVLOG.md, "reorganizacao em paginas +
            # tema escuro") -- mesma substancia, sem as clausulas de
            # justificativa/referencia interna que so repetiam o que
            # desempenho_geografico.nota_metodologica ja explica.
            f"Clusterizacao via KMeans (k={n_clusters}, z-score) sobre fec_aprox/dec_aprox_horas medios por "
            f"municipio -- mesmas metricas de desempenho_geografico.hotspots, ultimos {ultimos_n_meses} meses. "
            "Severidade e atribuida pelos CENTROIDES do cluster (pior -> melhor), nao pelo id arbitrario do "
            "KMeans. Coordenada e da sede do municipio -- mesma limitacao de granularidade dos hotspots (dado da "
            "ANEEL nao identifica subestacao/alimentador). Municipios sem coordenada ou com menos de 3 meses de "
            "dado na janela ficam de fora do mapa."
        ),
    }
