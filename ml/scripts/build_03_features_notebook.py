"""Monta e executa ml/notebooks/03-features.ipynb -- ver
build_01_eda_notebook.py para o padrao usado (nbformat monta as celulas,
nbclient executa de verdade contra data/processed/municipio_mes.parquet e
contra ml/features.py, para que o notebook entregue no repositorio tenha
saidas reais, nao fabricadas).

Requer: pip install -r ml/requirements.txt, e um kernel "python3" registrado
(python3 -m ipykernel install --user --name python3).

Rode de qualquer diretorio com: python3 ml/scripts/build_03_features_notebook.py
"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = REPO_ROOT / "data" / "processed" / "municipio_mes.parquet"
ARTIFACTS_DIR = REPO_ROOT / "ml" / "artifacts"
OUTPUT_NOTEBOOK = REPO_ROOT / "ml" / "notebooks" / "03-features.ipynb"

nb = nbf.v4.new_notebook()
cells = []


def md(src):
    cells.append(nbf.v4.new_markdown_cell(src))


def code(src):
    cells.append(nbf.v4.new_code_cell(src))


md("""\
# Engenharia de features -- Continua

Dia 4 (parte 1): transforma `data/processed/municipio_mes.parquet` (uma
linha por município x mês) num dataset supervisionado -- uma linha por
"(município, mês t)", com features calculadas usando só o que já era
conhecido até o mês t, e alvo = `fec_aprox` observado em t+1. A lógica mora
em `ml/features.py` (reaproveitada por este notebook, por
`04-modelagem.ipynb` e por `ml/train.py`) -- este notebook existe para
VALIDAR e justificar essas escolhas com números reais, não para reimplementar
a lógica.

Ver o docstring de `ml/features.py` para a justificativa completa de cada
feature -- resumo:

- Sazonalidade entra via `mes_sin`/`mes_cos` (cíclica), não via uma defasagem
  individual de 12 meses -- com só 24 meses de histórico, essa defasagem
  sazonal não teria quase nenhum dado de TREINO disponível antes da janela
  de teste (ver seção 4).
- Persistência de curto prazo entra via `lag_1`/`lag_2`/`lag_3` e médias
  móveis.
- Causa entra agregada e grosseira (proporção genérica vs. ambiental), não
  como as ~46 colunas originais -- ~95% dos eventos só têm causa genérica
  (achado do Dia 3).
""")

code("""\
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, r"__REPO_ROOT__")
from ml.features import FEATURES_NUMERICAS, construir_dataset, divisao_temporal, filtrar_utilizaveis

pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 140)

ARTIFACTS = r"__ARTIFACTS_DIR__"
df = pd.read_parquet(r"__DATA_PATH__")
dataset = construir_dataset(df)
dataset.shape
""")

md("""\
## 1. Um bug real pego construindo este dataset

A primeira versão de `construir_dataset` calculava `lag_1`/`lag_2`/... por
POSIÇÃO dentro de cada município (`.shift(1)`, `.shift(2)`...), sem levar em
conta se os meses eram realmente consecutivos no calendário. Isso escondia
dois problemas -- só descobertos comparando os números deste notebook
contra o baseline do Dia 3 (que usa um pivô largo por mês-calendário, não
por posição):

1. **Off-by-one:** como o alvo é o mês t+1, "1 mês antes do alvo" é o
   próprio mês t -- não t-1. Uma primeira versão usava `shift(1)` para
   `lag_1`, que na verdade apontava 2 meses antes do alvo.
2. **Buracos no meio do histórico:** município com um mês faltando no meio
   (não no início/fim) fazia o `.shift()` por posição "pular" o buraco e
   tratar dois meses não-consecutivos como vizinhos.

O segundo problema não é hipotético -- é real neste dado:
""")

code("""\
completo = df.dropna(subset=["nome_municipio"]).copy()
completo["periodo"] = pd.to_datetime(
    {"year": completo["ano"], "month": completo["mes"], "day": 1}
).dt.to_period("M")


def tem_buraco_no_meio(serie_periodos):
    ordenado = serie_periodos.sort_values()
    esperado = pd.period_range(ordenado.min(), ordenado.max(), freq="M")
    return len(esperado) != len(ordenado)


tem_buraco = completo.groupby("codigo_ibge_resolvido")["periodo"].apply(tem_buraco_no_meio)
print(f"{tem_buraco.sum()} de {len(tem_buraco)} municipios "
      f"({tem_buraco.mean():.1%}) tem pelo menos um mes faltando NO MEIO "
      "do historico (nao so no inicio/fim) -- longe de ser caso de borda.")
""")

md("""\
`construir_dataset` corrige os dois problemas reindexando cada município
para o calendário completo do painel antes de calcular qualquer defasagem
(ver o docstring da função) -- os testes em `tests/test_ml_features.py`
fixam esse comportamento (inclusive um teste que constrói um município com
um buraco no meio de propósito, para não regredir).""")

md("## 2. O dataset supervisionado resultante")

code("""\
print(f"{len(dataset):,} linhas (uma por municipio x mes com nome resolvido)")
dataset[["codigo_ibge_resolvido", "ano", "mes", "lag_1", "lag_2", "alvo", "exposicao"]].head(8)
""")

code("""\
utilizaveis = filtrar_utilizaveis(dataset)
print(f"{len(utilizaveis):,} linhas utilizaveis (tem lag_1 e alvo -- so o ultimo mes de cada "
      f"municipio fica de fora, por nao ter 'mes seguinte' observado ainda)")

nulos = utilizaveis[FEATURES_NUMERICAS].isna().mean().sort_values(ascending=False)
nulos = nulos[nulos > 0]
print("\\n% de nulos por feature (esperado para defasagens mais longas no "
      "inicio do historico de cada municipio -- HistGradientBoostingRegressor "
      "lida nativamente, GLM usa mediana do treino, ver ml/modelos.py):")
nulos
""")

md("## 3. Corte temporal treino/teste")

code("""\
treino, teste = divisao_temporal(dataset, ano_corte=2025)
print(f"treino: {len(treino):,} linhas, alvo em {(treino['periodo']+1).min()} a {(treino['periodo']+1).max()}")
print(f"teste:  {len(teste):,} linhas, alvo em {(teste['periodo']+1).min()} a {(teste['periodo']+1).max()}")
assert (treino["periodo"] + 1).dt.year.max() < 2025
assert (teste["periodo"] + 1).dt.year.eq(2025).all()
print("\\nOK: nenhum mes de 2025 vaza para o treino.")
""")

md("""\
**Limitação registrada (importante para o Dia 4 e para a conversa sobre
incluir mais anos de dados):** com só 24 meses de histórico (2024+2025), o
treino cobre só 10 meses-alvo (mar/2024 a dez/2024) -- uma defasagem sazonal
individual por município (mesmo mês do ano anterior) só existiria a partir
de jan/2025, que já é o próprio período de teste. Por isso a sazonalidade
entra via `mes_sin`/`mes_cos` (funciona com qualquer profundidade de
histórico, porque aprende o padrão a partir da variação ENTRE municípios no
mesmo mês, não da história de um município individual) em vez de uma
defasagem de 12 meses -- ver `ml/features.py`.""")

md("## 4. Poder preditivo bruto de cada feature")

code("""\
correlacoes = utilizaveis[FEATURES_NUMERICAS + ["alvo"]].corr()["alvo"].drop("alvo")
correlacoes = correlacoes.sort_values(key=abs, ascending=False)

fig, ax = plt.subplots(figsize=(8, 5.5))
cores = ["firebrick" if v < 0 else "steelblue" for v in correlacoes.values]
ax.barh(correlacoes.index[::-1], correlacoes.values[::-1], color=cores[::-1])
ax.set_xlabel("Correlacao com o alvo (fec_aprox do mes seguinte)")
ax.set_title("Correlacao bruta de cada feature numerica com o alvo")
fig.tight_layout()
fig.savefig(f"{ARTIFACTS}/correlacao_features_alvo.png", dpi=110)
plt.show()

correlacoes.round(3)
""")

md("""\
**Leitura:** `lag_1` (o valor do proprio mes t) e de longe a feature mais
correlacionada com o alvo, seguida pelas outras defasagens/medias moveis --
consistente com o achado do Dia 3 de que o risco e persistente mes a mes.
`mes_sin`/`mes_cos` tem correlacao bem mais fraca ISOLADAMENTE (correlacao
linear simples nao captura bem um efeito ciclico -- o modelo de arvore do
Dia 4 consegue usar melhor essa informacao do que uma correlacao de Pearson
sozinha sugere). As features de causa (`prop_causa_*`) tem correlacao quase
nula -- reforca o achado do Dia 3 de que causa e um dado pouco informativo
na pratica.""")

md("## Resumo (Dia 4 -- features)")

md("""\
1. Um bug real de off-by-one e de buracos no meio do historico foi
   encontrado e corrigido comparando este pipeline contra o baseline do Dia
   3 -- fixado em testes automatizados (`tests/test_ml_features.py`).
2. O corte temporal treino/teste deixa só ~10 meses de treino -- uma
   limitacao real de ter so 2 anos de dados, que molda a escolha de
   features (sazonalidade ciclica, nao defasagem de 12 meses).
3. `lag_1` domina o poder preditivo bruto; causa contribui muito pouco --
   consistente com a EDA do Dia 3. Ver `04-modelagem.ipynb` para os modelos
   treinados em cima deste dataset.
""")

nb["cells"] = cells
for c in nb["cells"]:
    if c["cell_type"] == "code":
        c["source"] = (
            c["source"]
            .replace("__REPO_ROOT__", str(REPO_ROOT))
            .replace("__ARTIFACTS_DIR__", str(ARTIFACTS_DIR))
            .replace("__DATA_PATH__", str(DATA_PATH))
        )

ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)

client = NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(OUTPUT_NOTEBOOK.parent)}})
client.execute()

with open(OUTPUT_NOTEBOOK, "w", encoding="utf-8") as f:
    nbf.write(nb, f)

print(f"OK: {OUTPUT_NOTEBOOK} executado e salvo.")
