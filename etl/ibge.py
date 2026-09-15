"""Join do codigo IBGE da ANEEL com a tabela de referencia de municipios/UF."""
import logging

import pandas as pd

from etl.config import COL_MUNICIPIO_IBGE, MUNICIPIOS_REFERENCE_PATH

logger = logging.getLogger(__name__)

_CAMPOS_REFERENCIA = ["codigo_ibge_7", "nome_municipio", "uf_sigla", "regiao"]


def load_municipios_reference(path=MUNICIPIOS_REFERENCE_PATH) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str)


def join_municipio(df: pd.DataFrame, referencia: pd.DataFrame) -> pd.DataFrame:
    """Adiciona codigo_ibge_resolvido / nome_municipio / uf_sigla / regiao.

    A ANEEL nem sempre usa o codigo IBGE de 7 digitos (com digito
    verificador) -- em alguns registros historicos vem truncado em 6. O join
    tenta primeiro o codigo completo (7 digitos) e, para quem nao casar,
    tenta de novo pelos 6 primeiros digitos.

    `codigo_ibge_resolvido` e a chave canonica (sempre o codigo de 7 digitos
    quando ha correspondencia) -- e ela que deve ser usada para agrupar por
    municipio depois, nunca o CodMunicipioIBGE bruto, para nao contar o
    mesmo municipio duas vezes so porque um mes veio com 6 digitos e outro
    com 7.

    Registros sem correspondencia mantêm o codigo bruto em
    `codigo_ibge_resolvido` e ficam com uf_sigla/nome_municipio/regiao nulos
    -- nunca sao descartados (ver docs/REQUISITOS.md), e a taxa de falha do
    join e sempre logada.
    """
    codigo = df[COL_MUNICIPIO_IBGE].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    codigo_6 = codigo.str[:6]

    ref_7 = referencia.set_index("codigo_ibge_7", drop=False)[_CAMPOS_REFERENCIA]
    ref_6 = referencia.drop_duplicates("codigo_ibge_6").set_index("codigo_ibge_6", drop=False)[_CAMPOS_REFERENCIA]

    match_7 = codigo.map(ref_7.to_dict("index"))
    match_6 = codigo_6.map(ref_6.to_dict("index"))
    resolved = match_7.where(match_7.notna(), match_6)

    def campo(nome, default=None):
        return resolved.map(lambda v, c=nome, d=default: v[c] if isinstance(v, dict) else d)

    out = df.copy()
    out["codigo_ibge_resolvido"] = campo("codigo_ibge_7")
    out["codigo_ibge_resolvido"] = out["codigo_ibge_resolvido"].fillna(codigo)
    out["nome_municipio"] = campo("nome_municipio")
    out["uf_sigla"] = campo("uf_sigla")
    out["regiao"] = campo("regiao")

    total = len(out)
    sem_match = out["uf_sigla"].isna().sum()
    taxa = 100 * sem_match / total if total else 0.0
    logger.info(
        "Join com municipios IBGE: %d/%d registros sem correspondencia (%.2f%%)",
        sem_match,
        total,
        taxa,
    )
    if taxa > 5:
        logger.warning(
            "Taxa de falha do join acima de 5%% -- vale investigar antes de seguir "
            "(ex: CodMunicipioIBGE fora do padrao, area de permissionaria excluida da tabela)."
        )

    return out
