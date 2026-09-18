import xml.etree.ElementTree as ET

import pandas as pd

from ml.mapa import ROTULOS_SEVERIDADE, clusterizar_municipios, gerar_kml, mapa_clusters_kml

KML_NS = {"k": "http://www.opengis.net/kml/2.2"}


def _linha(municipio, nome, uf, regiao, ano, mes, fec_aprox, dec_aprox_horas, consumidores=1000):
    return {
        "codigo_ibge_resolvido": municipio,
        "nome_municipio": nome,
        "uf_sigla": uf,
        "regiao": regiao,
        "ano": ano,
        "mes": mes,
        "n_eventos_validos": 10,
        "consumidores_ativos_max": consumidores,
        "fec_aprox": fec_aprox,
        "dec_aprox_horas": dec_aprox_horas,
    }


def _referencia(codigos_e_coords: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """Tabela de referência sintética (mesmas colunas de
    `data/reference/municipios.csv`), para não depender do arquivo real
    nos testes unitários -- só o essencial para `_resolver_coordenadas`."""
    linhas = [
        {"codigo_ibge_7": codigo, "codigo_ibge_6": codigo[:6], "latitude": lat, "longitude": lon}
        for codigo, (lat, lon) in codigos_e_coords.items()
    ]
    return pd.DataFrame(linhas)


def _painel_dois_grupos() -> pd.DataFrame:
    linhas = []
    # Grupo RUIM: fec_aprox e dec_aprox_horas altos -- deveria virar o cluster "critico"
    for codigo in ("1100015", "1100023", "1100031"):
        for mes in range(1, 13):
            linhas.append(_linha(codigo, f"Ruim-{codigo}", "RO", "Norte", 2025, mes, 0.09, 5.0))
    # Grupo BOM: fec_aprox e dec_aprox_horas baixos -- deveria virar o cluster "baixo"
    for codigo in ("3550308", "3550100", "3509502"):
        for mes in range(1, 13):
            linhas.append(_linha(codigo, f"Bom-{codigo}", "SP", "Sudeste", 2025, mes, 0.01, 0.2))
    return pd.DataFrame(linhas)


REFERENCIA_PADRAO = _referencia(
    {
        "1100015": (-11.93, -61.99),
        "1100023": (-9.91, -63.03),
        "1100031": (-9.71, -63.19),
        "3550308": (-23.55, -46.63),
        "3550100": (-23.51, -46.62),
        "3509502": (-22.90, -47.06),
    }
)


# --------------------------------------------------------------------------
# clusterizar_municipios
# --------------------------------------------------------------------------
def test_clusteriza_por_severidade_do_centroide_nao_pelo_id_arbitrario():
    resultado = clusterizar_municipios(
        _painel_dois_grupos(), referencia_coordenadas=REFERENCIA_PADRAO, n_clusters=2
    )
    por_municipio = {row["codigo_ibge_resolvido"]: row for row in resultado.to_dict(orient="records")}

    # independente do id de cluster que o KMeans atribuiu internamente, o
    # grupo com fec_aprox/dec_aprox_horas maiores tem que virar "critico"
    # (primeiro rotulo da lista, o pior) e o outro "alto" (k=2 so tem 2 rotulos).
    for codigo in ("1100015", "1100023", "1100031"):
        assert por_municipio[codigo]["severidade"] == "critico"
    for codigo in ("3550308", "3550100", "3509502"):
        assert por_municipio[codigo]["severidade"] == "alto"


def test_clusteriza_exclui_municipio_sem_coordenada_resolvivel():
    referencia_incompleta = REFERENCIA_PADRAO[REFERENCIA_PADRAO["codigo_ibge_7"] != "1100015"]
    resultado = clusterizar_municipios(
        _painel_dois_grupos(), referencia_coordenadas=referencia_incompleta, n_clusters=2
    )
    assert "1100015" not in resultado["codigo_ibge_resolvido"].tolist()
    assert len(resultado) == 5  # os outros 5 municipios continuam


def test_clusteriza_exige_minimo_de_meses_na_janela():
    linhas = _painel_dois_grupos().to_dict(orient="records")
    # deixa "1100015" com so 2 meses de dado -- abaixo do minimo_meses padrao (3)
    linhas = [linha for linha in linhas if not (linha["codigo_ibge_resolvido"] == "1100015" and linha["mes"] > 2)]
    resultado = clusterizar_municipios(
        pd.DataFrame(linhas), referencia_coordenadas=REFERENCIA_PADRAO, n_clusters=2
    )
    assert "1100015" not in resultado["codigo_ibge_resolvido"].tolist()


def test_severidade_usa_rotulos_conhecidos():
    resultado = clusterizar_municipios(
        _painel_dois_grupos(), referencia_coordenadas=REFERENCIA_PADRAO, n_clusters=4
    )
    assert set(resultado["severidade"]).issubset(set(ROTULOS_SEVERIDADE))


# --------------------------------------------------------------------------
# gerar_kml
# --------------------------------------------------------------------------
def test_gerar_kml_produz_xml_valido_com_coordenadas_em_ordem_lon_lat():
    clusters = clusterizar_municipios(_painel_dois_grupos(), referencia_coordenadas=REFERENCIA_PADRAO, n_clusters=2)
    kml = gerar_kml(clusters)

    raiz = ET.fromstring(kml)  # levanta excecao se o XML for invalido
    placemarks = raiz.findall(".//k:Placemark", KML_NS)
    assert len(placemarks) == len(clusters)

    por_nome = {p.find("k:name", KML_NS).text: p for p in placemarks}
    linha_referencia = clusters[clusters["codigo_ibge_resolvido"] == "1100015"].iloc[0]
    coords_texto = por_nome[linha_referencia["nome_municipio"]].find("k:Point/k:coordinates", KML_NS).text
    lon_str, lat_str, _alt = coords_texto.split(",")
    # ordem KML e longitude,latitude -- INVERTIDA da ordem usual lat/lon
    assert abs(float(lon_str) - linha_referencia["longitude"]) < 1e-4
    assert abs(float(lat_str) - linha_referencia["latitude"]) < 1e-4


def test_gerar_kml_agrupa_em_pastas_por_severidade():
    clusters = clusterizar_municipios(_painel_dois_grupos(), referencia_coordenadas=REFERENCIA_PADRAO, n_clusters=2)
    kml = gerar_kml(clusters)
    raiz = ET.fromstring(kml)
    pastas = raiz.findall(".//k:Folder", KML_NS)
    nomes_pastas = {p.find("k:name", KML_NS).text for p in pastas}
    assert any(nome.startswith("Critico") for nome in nomes_pastas)
    assert any(nome.startswith("Alto") for nome in nomes_pastas)


# --------------------------------------------------------------------------
# mapa_clusters_kml
# --------------------------------------------------------------------------
def test_mapa_clusters_kml_monta_payload_completo(monkeypatch):
    import ml.mapa as mapa_module

    monkeypatch.setattr(mapa_module, "carregar_coordenadas", lambda: REFERENCIA_PADRAO)
    resultado = mapa_clusters_kml(_painel_dois_grupos(), n_clusters=2)

    assert resultado["n_municipios_no_mapa"] == 6
    assert resultado["n_clusters"] == 2
    assert len(resultado["municipios"]) == 6
    assert sum(item["n_municipios"] for item in resultado["resumo_por_cluster"]) == 6
    assert "<kml" in resultado["kml"]
    assert all("severidade" in item for item in resultado["municipios"])
