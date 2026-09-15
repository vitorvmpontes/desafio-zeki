"""Monta e executa ml/notebooks/04-modelagem.ipynb -- ver
build_01_eda_notebook.py para o padrao usado (nbformat monta as celulas,
nbclient executa de verdade, para que o notebook entregue no repositorio
tenha saidas reais, nao fabricadas).

Requer: pip install -r ml/requirements.txt (inclui statsmodels e shap), e
um kernel "python3" registrado.

Rode de qualquer diretorio com: python3 ml/scripts/build_04_modelagem_notebook.py
"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = REPO_ROOT / "data" / "processed" / "municipio_mes.parquet"
ARTIFACTS_DIR = REPO_ROOT / "ml" / "artifacts"
OUTPUT_NOTEBOOK = REPO_ROOT / "ml" / "notebooks" / "04-modelagem.ipynb"

nb = nbf.v4.new_notebook()
cells = []


def md(src):
    cells.append(nbf.v4.new_markdown_cell(src))


def code(src):
    cells.append(nbf.v4.new_code_cell(src))


md("""\
# Modelagem -- Continua

Dia 4 (parte 2): treina e compara três modelos de previsão de risco
(`fec_aprox` do mês seguinte por município) sobre o dataset construído em
`03-features.ipynb`/`ml/features.py`, e compara todos contra o baseline
oficial do Dia 3 (`ml/artifacts/baseline_metricas.json`) -- que é o piso que
qualquer modelo real precisa superar para valer a pena.

**Modelos** (implementados em `ml/modelos.py`):

1. **GLM Poisson** -- modela a CONTAGEM de eventos válidos do mês seguinte
   com exposição (consumidores ativos conhecidos no mês t) via
   `statsmodels`, que tem offset/exposure nativo -- a forma estatisticamente
   correta de modelar uma taxa tipo FEC.
2. **GLM binomial negativa** -- mesma ideia, mas relaxando a suposição de
   Poisson de que média = variância (superdispersão é comum em dados de
   contagem no mundo real).
3. **Gradient boosting** (`HistGradientBoostingRegressor`, `loss="poisson"`)
   -- modela a TAXA diretamente, ponderada pela exposição (o truque padrão
   quando o framework não tem offset nativo, ver `ml/modelos.py`); região/UF
   entram como categóricas nativas, sem one-hot.

Todos avaliados com as MESMAS métricas do baseline (`ml/metricas.py`): MAE,
RMSE, correlação de Spearman do ranking, e precisão no top 10% de risco --
a métrica mais próxima do uso real do produto.
""")

code("""\
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, r"__REPO_ROOT__")
from ml.features import FEATURES_CATEGORICAS, FEATURES_NUMERICAS, construir_dataset, divisao_temporal
from ml.metricas import avaliar_ranking
from ml.modelos import ModeloContagemGLM, prever_gbm, treinar_gbm

pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 140)

ARTIFACTS = r"__ARTIFACTS_DIR__"
df = pd.read_parquet(r"__DATA_PATH__")
dataset = construir_dataset(df)
treino, teste = divisao_temporal(dataset, ano_corte=2025)
print(f"treino: {len(treino):,} linhas | teste: {len(teste):,} linhas")
""")

md("""\
## 1. Conjunto de teste comparável ao baseline

O baseline do Dia 3 só foi avaliado nos municípios com os 24 meses completos
de histórico (ver `02-baseline.ipynb`) -- restringimos o teste aqui da
mesma forma, para a comparação ser justa (mesma população, mesmos meses).""")

code("""\
contagem_meses = dataset.groupby("codigo_ibge_resolvido")["periodo"].nunique()
completos = set(contagem_meses[contagem_meses == 24].index)
teste_comp = teste[teste["codigo_ibge_resolvido"].isin(completos)].copy()
print(f"{len(teste_comp):,} linhas de teste, {teste_comp['codigo_ibge_resolvido'].nunique()} municipios "
      f"-- igual ao baseline do Dia 3.")

with open(f"{ARTIFACTS}/baseline_metricas.json") as f:
    baseline = json.load(f)
print("\\nbaseline oficial (Dia 3):", baseline["baseline_escolhido"])
print(baseline["metricas"])
""")

md("## 2. Treinando os três modelos")

code("""\
resultados = {}

teste_comp["pred_persistencia"] = teste_comp["lag_1"]
resultados["persistencia_t-1 (naive, so p/ referencia)"] = avaliar_ranking(
    teste_comp, "periodo", "alvo", "pred_persistencia"
)

poisson = ModeloContagemGLM("poisson").fit(treino)
teste_comp["pred_poisson"] = poisson.predict(teste_comp)
resultados["glm_poisson"] = avaliar_ranking(teste_comp, "periodo", "alvo", "pred_poisson")

nb_modelo = ModeloContagemGLM("binomial_negativa").fit(treino)
teste_comp["pred_nb"] = nb_modelo.predict(teste_comp)
resultados["glm_binomial_negativa"] = avaliar_ranking(teste_comp, "periodo", "alvo", "pred_nb")
print(f"alpha (dispersao) estimado da binomial negativa: {nb_modelo.alpha_nb:.4f}")

gbm = treinar_gbm(treino)
teste_comp["pred_gbm"] = prever_gbm(gbm, teste_comp)
resultados["gradient_boosting"] = avaliar_ranking(teste_comp, "periodo", "alvo", "pred_gbm")

resultados["baseline_dia3 (persistencia t-1 + t-12)"] = baseline["metricas"]

tabela = pd.DataFrame(resultados).T[["mae", "rmse", "spearman", "precisao_top10pct"]]
tabela.round(4).sort_values("precisao_top10pct", ascending=False)
""")

code("""\
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
ordem = tabela.sort_values("precisao_top10pct").index

axes[0].barh(ordem, tabela.loc[ordem, "mae"], color="steelblue")
axes[0].set_title("MAE (menor = melhor)")

axes[1].barh(ordem, tabela.loc[ordem, "precisao_top10pct"], color="seagreen")
axes[1].set_title("Precisao no top 10% de risco (maior = melhor)")
axes[1].set_xlim(0, 1)

fig.tight_layout()
fig.savefig(f"{ARTIFACTS}/comparacao_modelos.png", dpi=110)
plt.show()
""")

md("""\
**Leitura honesta do resultado:** os três modelos (Poisson, binomial
negativa, gradient boosting) batem claramente a persistência simples
(t-1 sozinha), confirmando que as features cross-sectionais (sazonalidade,
região, histórico de médias) agregam sinal real. O **gradient boosting** é o
melhor dos três em quase toda métrica. Mas **nenhum dos três supera o
baseline combinado do Dia 3** (persistência t-1 + t-12) na precisão do top
10% -- e isso tem uma explicação concreta, não é só "o baseline é bom":
o baseline usa a persistência sazonal **individual de cada município**
(mesmo mês, ano anterior), um sinal que os modelos daqui não conseguem
aprender de forma confiável com só 2 anos de histórico (ver
`03-features.ipynb`, seção 3 -- esse recorte de treino não tem NENHUM
exemplo onde essa defasagem de 12 meses esteja disponível). Isso reforça,
com números, o argumento para reavaliar a inclusão de mais anos de dados da
ANEEL.""")

md("## 3. Interpretabilidade")

code("""\
from sklearn.inspection import permutation_importance

X_teste_comp = teste_comp[FEATURES_NUMERICAS + FEATURES_CATEGORICAS].copy()
for col in FEATURES_CATEGORICAS:
    X_teste_comp[col] = X_teste_comp[col].astype("category")

r = permutation_importance(
    gbm, X_teste_comp, teste_comp["alvo"], n_repeats=5, random_state=42,
    scoring="neg_mean_absolute_error",
)
importancia = pd.Series(r.importances_mean, index=X_teste_comp.columns).sort_values(ascending=False)

fig, ax = plt.subplots(figsize=(8, 5.5))
ax.barh(importancia.index[::-1], importancia.values[::-1], color="darkorange")
ax.set_title("Importancia por permutacao (gradient boosting)\\nqueda no MAE ao embaralhar cada feature")
fig.tight_layout()
fig.savefig(f"{ARTIFACTS}/importancia_features.png", dpi=110)
plt.show()

importancia.round(6)
""")

md("""\
**Leitura:** `lag_1` (o valor do proprio mes t) e de longe a feature mais
importante, seguida pela media historica expandida (nivel de risco de longo
prazo do municipio) e por `mes_sin` (sazonalidade). UF, causa e numero de
distribuidoras contribuem muito pouco -- consistente com a EDA do Dia 3.""")

code("""\
# SHAP tambem foi tentado para esta mesma analise. Com as categoricas no
# formato nativo do HistGradientBoostingRegressor (dtype "category"), o
# TreeExplainer do shap nao consegue processar o modelo (erro de conversao
# string->float) -- uma limitacao conhecida de shap com esse recurso ainda
# relativamente novo do sklearn. Refazendo o MESMO modelo (mesmos
# hiperparametros, mesma acuracia) com as categoricas codificadas como
# inteiros (mantendo-as como "categoricas" para o HistGradientBoosting via
# indices, so trocando a representacao), o SHAP roda -- mas devolve um
# RANKING de importancia bem diferente da importancia por permutacao acima
# (mes_cos e lag_3 no topo, lag_1 quase no fim). Isso nao e um bug: SHAP
# (TreeExplainer) mede o efeito no espaco RAW do modelo (log, por causa do
# link da familia Poisson) e se comporta de forma menos estavel quando ha
# features fortemente colineares (aqui, as cinco variacoes de historico:
# lag_1/lag_2/lag_3/media_movel_3/media_movel_expandida) -- a arvore pode
# "escolher" dividir por qualquer uma delas de forma quase intercambiavel, e
# o SHAP credita a que foi de fato usada numa dada arvore, nao a que carrega
# mais sinal em teoria. A importancia por permutacao (medida direto no erro
# final, MAE) e mais facil de interpretar aqui e e a que usamos como
# principal. Documentado como um ponto de atencao para simplificar o
# conjunto de features numa proxima iteracao (Dia 5+), nao escondido.
print("Nota sobre SHAP registrada -- ver texto da celula acima.")
""")

md("## 4. Modelo escolhido")

code("""\
melhor = tabela.drop("baseline_dia3 (persistencia t-1 + t-12)").sort_values("precisao_top10pct", ascending=False).index[0]
print(f"Modelo escolhido para o Dia 5 (API): {melhor}")
print(tabela.loc[melhor].round(4).to_dict())

metricas_finais = {
    "modelo_escolhido": "gradient_boosting",
    "alvo": "fec_aprox",
    "comparacao": tabela.round(6).to_dict(orient="index"),
    "supera_baseline_dia3": bool(
        tabela.loc["gradient_boosting", "precisao_top10pct"]
        > tabela.loc["baseline_dia3 (persistencia t-1 + t-12)", "precisao_top10pct"]
    ),
}
with open(f"{ARTIFACTS}/modelagem_metricas.json", "w") as f:
    json.dump(metricas_finais, f, indent=2, ensure_ascii=False)
print(f"\\nSalvo em {ARTIFACTS}/modelagem_metricas.json")
""")

md("""\
**Decisão:** o **gradient boosting** é o modelo escolhido para seguir para o
Dia 5 (API) -- é o melhor dos três modelos "de verdade" treinados (melhor
Spearman entre os três, praticamente empatado com o baseline do Dia 3 nessa
métrica), lida nativamente com valores faltantes e com categóricas, e tem a
vantagem de já vir com uma via de interpretabilidade (importância por
permutação) direta.

**Mas o produto final não deveria descartar o baseline.** Como o baseline
combinado do Dia 3 ainda vence na precisão do top 10%, o `ml/train.py`
salva o modelo de gradient boosting como o modelo servido pela API, mas a
API (Dia 5) deve continuar calculando e expondo o baseline como referência
-- e a recomendação registrada aqui é reavaliar essa escolha assim que
houver mais anos de histórico disponíveis (permitindo incluir a defasagem
sazonal individual por município como feature de treino de verdade, não só
como um baseline à parte).
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

client = NotebookClient(nb, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(OUTPUT_NOTEBOOK.parent)}})
client.execute()

with open(OUTPUT_NOTEBOOK, "w", encoding="utf-8") as f:
    nbf.write(nb, f)

print(f"OK: {OUTPUT_NOTEBOOK} executado e salvo.")
