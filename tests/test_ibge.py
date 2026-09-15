import pandas as pd

from etl.ibge import fanout_municipio, load_conjunto_municipio_bridge


def test_bridge_marca_conjuntos_com_mais_de_um_municipio(bridge):
    assert set(bridge["conjunto_id"]) == {"CJ01", "CJ02"}
    cj01 = bridge[bridge["conjunto_id"] == "CJ01"]
    cj02 = bridge[bridge["conjunto_id"] == "CJ02"]
    assert (cj01["n_municipios_no_conjunto"] == 1).all()
    assert (cj02["n_municipios_no_conjunto"] == 2).all()


def test_bridge_carrega_com_encoding_latin1(bridge):
    """O CSV real da ANEEL vem em latin1 (confirmado processando o arquivo
    de verdade -- ver docs/DEVLOG.md); load_conjunto_municipio_bridge deve
    ler nomes acentuados corretamente."""
    assert "São Paulo" in set(bridge["nome_municipio"])


def test_fanout_municipio_resolve_conjunto_unico(referencia, bridge):
    df = pd.DataFrame({"conjunto_id": ["CJ01"], "ano": [2025], "mes": [1], "n_eventos_total": [2]})
    out = fanout_municipio(df, bridge, referencia)
    assert len(out) == 1
    linha = out.iloc[0]
    assert linha["nome_municipio"] == "Ariquemes"
    assert linha["uf_sigla"] == "RO"
    assert linha["n_municipios_no_conjunto"] == 1
    assert linha["peso_evento"] == 1.0


def test_fanout_municipio_distribui_conjunto_compartilhado(referencia, bridge):
    df = pd.DataFrame({"conjunto_id": ["CJ02"], "ano": [2025], "mes": [1], "n_eventos_total": [4]})
    out = fanout_municipio(df, bridge, referencia)
    assert len(out) == 2
    assert set(out["nome_municipio"]) == {"São Paulo", "Guarulhos"}
    assert (out["peso_evento"] == 0.5).all()
    assert (out["n_municipios_no_conjunto"] == 2).all()


def test_fanout_municipio_sem_correspondencia_mantem_linha(referencia, bridge):
    df = pd.DataFrame({"conjunto_id": ["CJ99"], "ano": [2025], "mes": [1], "n_eventos_total": [1]})
    out = fanout_municipio(df, bridge, referencia)
    assert len(out) == 1
    linha = out.iloc[0]
    assert linha["codigo_ibge_resolvido"] == "CONJUNTO_CJ99"
    assert pd.isna(linha["uf_sigla"])
    assert linha["peso_evento"] == 1.0


def test_load_conjunto_municipio_bridge_aceita_path_customizado(tmp_path):
    """Usado pelos testes com a fixture pequena, mas serve tambem para
    conferir que a funcao nao depende do caminho padrao de producao."""
    conteudo = (
        "DatGeracaoConjuntoDados,IdeConjUnidConsumidoras,CodMunicipio,NomMunicipio,SigUF\n"
        "2025-09-01,CJX,1100023,Ariquemes,RO\n"
    ).encode("latin1")
    caminho = tmp_path / "bridge.csv"
    caminho.write_bytes(conteudo)
    bridge = load_conjunto_municipio_bridge(caminho)
    assert list(bridge["conjunto_id"]) == ["CJX"]
    assert bridge.iloc[0]["n_municipios_no_conjunto"] == 1
