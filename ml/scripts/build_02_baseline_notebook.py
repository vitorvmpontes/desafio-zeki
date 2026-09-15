"""Monta e executa ml/notebooks/02-baseline.ipynb -- ver
build_01_eda_notebook.py para o padrao usado (nbformat monta as celulas,
nbclient executa de verdade contra data/processed/municipio_mes.parquet, para
que o notebook entregue no repositorio tenha saidas reais, nao fabricadas).

Requer: pip install nbformat nbclient ipykernel jupyter_client, e um kernel
"python3" registrado (python3 -m ipykernel install --user --name python3).

Rode de qualquer diretorio com: python3 ml/scripts/build_02_baseline_notebook.py
"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = REPO_ROOT / "data" / "processed" / "municipio_mes.parquet"
ARTIFACTS_DIR = REPO_ROOT / "ml" / "artifacts"
OUTPUT_NOTEBOOK = REPO_ROOT / "ml" / "notebooks" / "02-baseline.ipynb"

nb = nbf.v4.new_notebook()
cells = []

def md(src):
    cells.append(nbf.v4.new_markdown_cell(src))

def code(src):
    cells.append(nbf.v4.new_code_cell(src))

md("""\
# Baseline de previsao de risco -- Continua

Dia 3 (parte 2): antes de treinar qualquer modelo real (Dia 4 -- GLM/GBM), este
notebook estabelece um **baseline ingenuo** para prever o risco de interrupcao
(`fec_aprox`) do mes seguinte por municipio. Todo modelo do Dia 4 so e
considerado valido se bater esse baseline (`docs/REQUISITOS.md` e
`ml/README.md` ja documentavam esse principio antes de qualquer numero
existir -- aqui ele vira numero).

**Alvo escolhido:** `fec_aprox` (frequencia aproximada de interrupcao por
consumidor, ver `etl/aggregate.py`) -- normalizado por consumidor, e por isso
comparavel entre municipios de tamanhos diferentes (ver conclusao da secao 3
de `01-eda.ipynb`: ranquear por volume bruto de eventos favoreceria sempre
cidades grandes).

**Regra de validacao:** sempre corte temporal, nunca embaralhar meses --
treinamos/calibramos usando 2024 e avaliamos contra 2025 (ver
`ml/README.md`).
""")

code("""\
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 140)

ARTIFACTS = r"__ARTIFACTS_DIR__"

df = pd.read_parquet(r"__DATA_PATH__")
df = df.dropna(subset=["nome_municipio"]).copy()
df["periodo"] = pd.to_datetime({"year": df["ano"], "month": df["mes"], "day": 1}).dt.to_period("M")
df.shape
""")

md("""\
## 1. Painel municipio x mes

Para comparar previsao com valor real mes a mes por municipio, precisamos de
um painel **completo** (sem meses faltando) -- senao "prever o mes seguinte"
nao faz sentido para quem tem buracos no historico. Municipios sem os 24
meses completos (o residuo sem correspondencia na bridge, ou algum caso raro
de cobertura incompleta) ficam de fora desta avaliacao -- mas continuam
disponiveis para o modelo final servir previsao assim que tiverem historico
suficiente (ver `etl/README.md`).""")

code("""\
contagem_meses = df.groupby("codigo_ibge_resolvido")["periodo"].nunique()
completos = contagem_meses[contagem_meses == 24].index
print(f"{len(completos)} de {contagem_meses.shape[0]} municipios tem os 24 meses completos "
      f"({len(completos) / contagem_meses.shape[0]:.1%}) -- usados na avaliacao do baseline.")

painel = df[df["codigo_ibge_resolvido"].isin(completos)].sort_values(["codigo_ibge_resolvido", "periodo"])
wide = painel.set_index(["codigo_ibge_resolvido", "periodo"])["fec_aprox"].unstack("periodo")
wide.shape
""")

md("## 2. Tres baselines ingenuos")

md("""\
- **Persistencia mes anterior (t-1):** preve `fec_aprox` do mes M usando o
  valor real do mes M-1 do mesmo municipio. Mais simples possivel, captura
  autocorrelacao de curto prazo.
- **Persistencia sazonal (t-12):** preve o mes M usando o MESMO mes do ano
  anterior. So funciona a partir do segundo ano de historico (2025, usando
  2024) -- captura o padrao sazonal visto em `01-eda.ipynb`.
- **Media historica expandida:** preve o mes M usando a media de todos os
  meses anteriores do municipio (ate M-1). Mais suave, menos sensivel a um
  mes atipico isolado.
""")

code("""\
pred_t1 = wide.shift(1, axis=1)
pred_t12 = wide.shift(12, axis=1)
pred_media_expandida = wide.T.expanding().mean().T.shift(1, axis=1)
pred_blend = (pred_t1 + pred_t12) / 2  # ver secao 4
""")

md("""\
## 3. Metricas de avaliacao

Como o produto e um **ranking mensal de risco**, erro absoluto (MAE/RMSE) nao
conta a historia toda -- o que importa e se o modelo acerta QUEM sao os
municipios de maior risco. Por isso, alem de MAE/RMSE, avaliamos:

- **Correlacao de Spearman** entre o ranking previsto e o ranking real de
  `fec_aprox` no mes.
- **Precisao no top 10%:** dos municipios que o baseline coloca no top 10% de
  risco previsto, quantos realmente estavam no top 10% de risco real naquele
  mes. E a metrica mais proxima do uso real do produto (priorizar
  fiscalizacao/manutencao nos municipios de maior risco).

Avaliado sempre contra os 12 meses de 2025 (para os tres baselines terem
exatamente o mesmo periodo de teste, ja que o sazonal so comeca a valer a
partir do mes 13 do painel).""")

code("""\
def avaliar(nome, actual_wide, pred_wide, meses):
    maes, rmses, spearmans, precisoes = [], [], [], []
    for m in meses:
        a, p = actual_wide[m], pred_wide[m]
        mask = a.notna() & p.notna()
        a2, p2 = a[mask], p[mask]
        if len(a2) < 10:
            continue
        erro = a2 - p2
        maes.append(erro.abs().mean())
        rmses.append(np.sqrt((erro ** 2).mean()))
        spearmans.append(a2.rank().corr(p2.rank()))
        k = max(1, int(len(a2) * 0.1))
        top_real = set(a2.sort_values(ascending=False).head(k).index)
        top_previsto = set(p2.sort_values(ascending=False).head(k).index)
        precisoes.append(len(top_real & top_previsto) / k)
    return {
        "baseline": nome,
        "mae": np.mean(maes),
        "rmse": np.mean(rmses),
        "spearman": np.mean(spearmans),
        "precisao_top10pct": np.mean(precisoes),
    }

meses_2025 = wide.columns[12:]
resultados = pd.DataFrame([
    avaliar("persistencia_t-1", wide, pred_t1, meses_2025),
    avaliar("persistencia_sazonal_t-12", wide, pred_t12, meses_2025),
    avaliar("media_historica_expandida", wide, pred_media_expandida, meses_2025),
    avaliar("blend_t-1_e_t-12", wide, pred_blend, meses_2025),
]).set_index("baseline")

resultados.round(4)
""")

code("""\
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
resultados["mae"].plot.barh(ax=axes[0], color="steelblue")
axes[0].set_title("MAE (menor = melhor)")
axes[0].invert_yaxis()

resultados["precisao_top10pct"].plot.barh(ax=axes[1], color="seagreen")
axes[1].set_title("Precisao no top 10% de risco (maior = melhor)")
axes[1].invert_yaxis()
axes[1].set_xlim(0, 1)

fig.tight_layout()
fig.savefig(f"{ARTIFACTS}/comparacao_baselines.png", dpi=110)
plt.show()
""")

md("""\
**Leitura dos resultados:** a persistencia de mes anterior (t-1) sozinha ja e
mais forte que a persistencia sazonal (t-12) sozinha -- o risco muda pouco de
um mes para o outro (sinal de curto prazo forte), e usar so "o mesmo mes do
ano passado" perde parte desse sinal recente. A media historica expandida
suaviza demais e perde precisao no top 10%, que e a metrica que mais importa
para o produto. O melhor dos quatro e a **combinacao (blend) de t-1 e t-12** --
bate os outros tres em toda metrica, porque junta o sinal de curto prazo (t-1)
com o padrao sazonal (t-12) sem exigir nenhum treino.""")

md("## 4. Baseline oficial para o Dia 4")

code("""\
melhor = resultados["mae"].idxmin()
print(f"Baseline escolhido como piso de comparacao para o Dia 4: {melhor}")
print(resultados.loc[melhor].round(4).to_dict())

# salva as metricas do baseline oficial para o Dia 4 comparar contra elas
with open(f"{ARTIFACTS}/baseline_metricas.json", "w") as f:
    json.dump(
        {
            "baseline_escolhido": melhor,
            "alvo": "fec_aprox",
            "periodo_teste": [str(m) for m in meses_2025],
            "metricas": resultados.loc[melhor].round(6).to_dict(),
            "todos_baselines": resultados.round(6).to_dict(orient="index"),
        },
        f,
        indent=2,
        ensure_ascii=False,
    )
print(f"\\nSalvo em {ARTIFACTS}/baseline_metricas.json")
""")

md("""\
**Definicao do baseline oficial:** `fec_aprox_previsto(municipio, mes) =
media( fec_aprox(municipio, mes-1), fec_aprox(municipio, mes-12) )`.
Nenhum parametro treinado -- so os dois valores historicos do proprio
municipio. Precisao no top 10% de risco em torno de **80%** nos 12 meses de
2025 testados. Qualquer modelo do Dia 4 (GLM/GBM com features de sazonalidade,
regiao, causa e defasagens) so e considerado uma melhoria real se superar
essas metricas no mesmo corte temporal -- nao so ter um numero "menor" no
treino.

**Limitacao explicita:** este baseline so cobre os municipios com os 24 meses
completos de historico (~93% dos municipios reais). Municipios novos ou com
buracos no historico (o residuo sem bridge, por exemplo) exigem uma estrategia
separada (provavelmente a media regional/nacional do mes como fallback) --
ponto em aberto para o Dia 4, registrado aqui e em `docs/DEVLOG.md`.""")

for c in cells:
    if c["cell_type"] == "code":
        c["source"] = (
            c["source"]
            .replace("__ARTIFACTS_DIR__", str(ARTIFACTS_DIR))
            .replace("__DATA_PATH__", str(DATA_PATH))
        )

nb["cells"] = cells

ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)

client = NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(OUTPUT_NOTEBOOK.parent)}})
client.execute()

with open(OUTPUT_NOTEBOOK, "w", encoding="utf-8") as f:
    nbf.write(nb, f)

print(f"OK: {OUTPUT_NOTEBOOK} executado e salvo.")
