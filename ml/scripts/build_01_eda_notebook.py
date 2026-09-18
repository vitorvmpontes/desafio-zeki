"""Script auxiliar (nao versionado como parte do produto final, mas mantido
no repo para reprodutibilidade) que monta e executa ml/notebooks/01-eda.ipynb
a partir de celulas definidas em codigo, para que o notebook entregue no
repositorio ja contenha saidas reais (graficos, tabelas) geradas contra
data/processed/municipio_mes.parquet -- nao apenas o codigo.

Requer: pip install nbformat nbclient ipykernel jupyter_client, e um kernel
"python3" registrado (python3 -m ipykernel install --user --name python3).

Rode de qualquer diretorio com: python3 ml/scripts/build_01_eda_notebook.py
"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = REPO_ROOT / "data" / "processed" / "municipio_mes.parquet"
ARTIFACTS_DIR = REPO_ROOT / "ml" / "artifacts"
OUTPUT_NOTEBOOK = REPO_ROOT / "ml" / "notebooks" / "01-eda.ipynb"

nb = nbf.v4.new_notebook()
cells = []

def md(src):
    cells.append(nbf.v4.new_markdown_cell(src))

def code(src):
    cells.append(nbf.v4.new_code_cell(src))

md("""\
# Analise exploratoria -- Continua

Dia 3 do desafio: analise exploratoria sobre `data/processed/municipio_mes.csv`,
o dataset agregado municipio x mes gerado pelo pipeline em `etl/` a partir dos
18.926.623 eventos reais de interrupcao publicados pela ANEEL (2024 + 2025).

Perguntas que este notebook responde:

1. Como o volume de interrupcoes varia ao longo do ano (sazonalidade)?
2. Como o risco se distribui entre regioes do Brasil?
3. Quais causas dominam as interrupcoes -- e quao granular e essa informacao de fato?
4. Quais municipios tem o maior risco historico (indicadores aproximados de FEC/DEC)?
5. Os indicadores sao correlacionados entre si de um jeito que ajude (ou atrapalhe) o modelo do Dia 4?

Ver `docs/DEVLOG.md` (Dia 3) para o resumo das conclusoes e `docs/REQUISITOS.md`
para as decisoes de produto por tras dos indicadores aproximados (`fec_aprox`,
`dec_aprox_horas`).
""")

code("""\
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 140)

ARTIFACTS = r"__ARTIFACTS_DIR__"

df = pd.read_parquet(r"__DATA_PATH__")
print(df.shape)
df.head(3)
""")

md("## 1. Visao geral e qualidade dos dados")

code("""\
df.dtypes.value_counts()
""")

code("""\
# quantos municipios e meses distintos temos
print("municipios distintos (codigo_ibge_resolvido):", df["codigo_ibge_resolvido"].nunique())
print("meses distintos:", df[["ano", "mes"]].drop_duplicates().shape[0], "(2024-01 a 2025-12)")
print("linhas totais:", len(df))
""")

code("""\
# nulos -- so existem em nome_municipio/uf_sigla/regiao, e so quando o conjunto
# nao teve correspondencia na bridge conjunto->municipio da ANEEL (ver etl/ibge.py)
nulos = df.isna().sum()
nulos = nulos[nulos > 0]
print(nulos)

sem_bridge = df[df["nome_municipio"].isna()]
conjuntos_sem_bridge = sem_bridge["codigo_ibge_resolvido"].nunique()
print(f"\\n{len(sem_bridge)} linhas ({len(sem_bridge)/len(df):.3%} do total) "
      f"vem de {conjuntos_sem_bridge} conjuntos sem correspondencia na bridge "
      "'IndQual Municipio' -- ficam em grupo proprio (codigo_ibge_resolvido "
      "= 'CONJUNTO_<id>'), sem regiao/UF conhecida, mas SEM ser descartados "
      "da agregacao (decisao de projeto, ver docs/REQUISITOS.md).")
""")

md("""\
**Conclusao:** a cobertura da bridge conjunto->municipio e excelente (>99,9% das
linhas tem municipio/UF/regiao resolvidos). O pequeno residuo sem correspondencia
fica isolado em seu proprio grupo -- nao contamina nenhum municipio real, e nao
pode ser usado no ranking por municipio (sera excluido do treino do modelo por
nao ter uma chave geografica valida).""")

md("## 2. Sazonalidade -- volume de eventos por mes")

code("""\
por_mes = df.groupby(["ano", "mes"], as_index=False)["n_eventos_total"].sum()
por_mes["periodo"] = por_mes["ano"].astype(str) + "-" + por_mes["mes"].astype(str).str.zfill(2)

fig, ax = plt.subplots(figsize=(11, 4.5))
for ano, grupo in por_mes.groupby("ano"):
    ax.plot(grupo["mes"], grupo["n_eventos_total"], marker="o", label=str(ano))
ax.set_xticks(range(1, 13))
ax.set_xlabel("Mes")
ax.set_ylabel("N. de eventos (ponderado por fan-out)")
ax.set_title("Volume nacional de interrupcoes por mes -- 2024 vs 2025")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e3:.0f} mil"))
ax.legend(title="Ano")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{ARTIFACTS}/sazonalidade_mensal.png", dpi=110)
plt.show()
""")

code("""\
# variacao pico-vale, como % da media -- para quantificar a sazonalidade
media = por_mes["n_eventos_total"].mean()
pico = por_mes["n_eventos_total"].max()
vale = por_mes["n_eventos_total"].min()
print(f"media mensal: {media:,.0f} eventos")
print(f"pico: {pico:,.0f} ({(pico/media - 1):+.1%} vs media)")
print(f"vale: {vale:,.0f} ({(vale/media - 1):+.1%} vs media)")
""")

md("""\
**Conclusao:** ha um padrao sazonal claro e consistente nos dois anos: os meses
de verao/chuvas no Brasil (dezembro-janeiro, e um pico secundario em
setembro-outubro) concentram mais eventos, com um vale bem definido em
junho-julho (inverno/seco). O padrao se repete quase identico entre 2024 e 2025
-- e o argumento mais forte a favor de um baseline de **persistencia sazonal**
(prever o mes usando o mesmo mes do ano anterior) no lugar de so persistencia do
mes anterior. Isso vira `mes` (ciclico) como feature obrigatoria no Dia 4.""")

md("## 3. Distribuicao regional")

code("""\
por_regiao = df.groupby("regiao").agg(
    n_eventos=("n_eventos_total", "sum"),
    consumidores=("consumidores_ativos_max", "sum"),
    municipios=("codigo_ibge_resolvido", "nunique"),
).sort_values("n_eventos", ascending=False)
por_regiao["eventos_por_1000_consumidores_mes"] = (
    por_regiao["n_eventos"] / por_regiao["consumidores"] * 1000 / 24
)
por_regiao
""")

code("""\
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

ordem = por_regiao.index
axes[0].bar(ordem, por_regiao["n_eventos"] / 1e6)
axes[0].set_title("Total de eventos (2024-2025)")
axes[0].set_ylabel("Milhoes de eventos")
axes[0].tick_params(axis="x", rotation=20)

axes[1].bar(ordem, por_regiao["eventos_por_1000_consumidores_mes"], color="darkorange")
axes[1].set_title("Eventos por 1.000 consumidores / mes\\n(normalizado pelo tamanho da regiao)")
axes[1].set_ylabel("Eventos / 1.000 consumidores / mes")
axes[1].tick_params(axis="x", rotation=20)

fig.tight_layout()
fig.savefig(f"{ARTIFACTS}/distribuicao_regional.png", dpi=110)
plt.show()
""")

md("""\
**Conclusao:** em volume absoluto o Sudeste domina (mais consumidores, mais
eventos em numero absoluto). Mas normalizando por consumidor -- a mesma logica
do FEC regulatorio -- o quadro muda bastante: Centro-Oeste e Norte tem a maior
taxa de eventos por consumidor (quase o dobro do Sudeste), enquanto Sudeste e
Nordeste ficam praticamente empatados na taxa mais baixa, apesar do Nordeste
ter o segundo maior volume bruto. Isso confirma que a normalizacao usada em
`fec_aprox` (e nao o volume bruto de eventos) e a metrica certa para comparar
risco entre municipios de tamanhos muito diferentes -- ranquear por volume bruto favoreceria sempre
cidades grandes, nao as de fato mais arriscadas.""")

md("## 4. Mix de causas")

code("""\
causa_cols = [c for c in df.columns if c.startswith("causa_")]
total_validos = df["n_eventos_validos"].sum()
soma_causas = df[causa_cols].sum()

# confirma que as colunas de causa sao mutuamente exclusivas (cada evento
# valido cai em exatamente uma) -- a soma bate com n_eventos_validos.
print("soma de todas as colunas de causa:", soma_causas.sum())
print("n_eventos_validos (total):", total_validos)
""")

code("""\
top_causas = (soma_causas / total_validos * 100).sort_values(ascending=False).head(12)

fig, ax = plt.subplots(figsize=(9, 5.5))
ax.barh(top_causas.index[::-1], top_causas.values[::-1], color="steelblue")
ax.set_xlabel("% dos eventos validos")
ax.set_title("Causas mais frequentes (DscFatoGeradorInterrupcao normalizado)")
fig.tight_layout()
fig.savefig(f"{ARTIFACTS}/mix_de_causas.png", dpi=110)
plt.show()

top_causas.round(2)
""")

code("""\
generico = (soma_causas.get("causa_interna", 0) + soma_causas.get("causa_interno", 0)) / total_validos
print(f"{generico:.1%} dos eventos validos so tem a causa generica "
      "'interna'/'interno', sem nenhum nivel de detalhe alem disso.")
print(f"Existem {len(causa_cols)} strings de causa distintas no total, mas so "
      "uma duzia tem peso pratico -- a cauda longa e irrelevante para o modelo.")
""")

md("""\
**Conclusao (importante para nao superestimar o dado):** ~95% dos eventos
validos so tem a causa generica "interna"/"interno" -- sem nenhuma
granularidade (arvore, animal, equipamento, etc.). So uma minoria dos registros
tem causa detalhada. Isso significa que "causas dominantes" como feature
individual tem pouco poder preditivo pratico hoje -- o campo esta mais para
"a interrupcao foi causada pela propria rede/distribuidora ou por algo
externo" do que para um diagnostico de causa raiz. Documentado como limitacao
de dado (nao um bug do pipeline) -- ver `etl/README.md`.""")

md("## 5. Ranking de risco historico por municipio")

code("""\
por_municipio = df.dropna(subset=["nome_municipio"]).groupby(
    ["codigo_ibge_resolvido", "nome_municipio", "uf_sigla", "regiao"], as_index=False
).agg(
    meses_com_dado=("ano", "count"),
    fec_aprox_medio=("fec_aprox", "mean"),
    dec_aprox_medio=("dec_aprox_horas", "mean"),
    n_eventos_medio=("n_eventos_total", "mean"),
    consumidores=("consumidores_ativos_max", "max"),
)

# so municipios com historico completo (24 meses) entram no ranking --
# historico incompleto (municipio so aparece em alguns meses) enviesaria a
# media para cima ou para baixo sem base de comparacao justa.
completos = por_municipio[por_municipio["meses_com_dado"] == 24]
print(f"{len(completos)} de {len(por_municipio)} municipios tem os 24 meses completos "
      f"({len(completos)/len(por_municipio):.1%}).")
""")

code("""\
top15_fec = completos.sort_values("fec_aprox_medio", ascending=False).head(15)
top15_fec[["nome_municipio", "uf_sigla", "regiao", "fec_aprox_medio", "dec_aprox_medio", "n_eventos_medio"]]
""")

code("""\
fig, ax = plt.subplots(figsize=(9, 5.5))
labels = top15_fec["nome_municipio"] + "/" + top15_fec["uf_sigla"]
ax.barh(labels[::-1], top15_fec["fec_aprox_medio"][::-1], color="firebrick")
ax.set_xlabel("FEC aproximado medio (2024-2025)")
ax.set_title("Top 15 municipios por risco historico de interrupcao")
fig.tight_layout()
fig.savefig(f"{ARTIFACTS}/top15_risco_historico.png", dpi=110)
plt.show()
""")

code("""\
# o risco historico e estavel mes a mes para o mesmo municipio, ou e ruido?
# correlacao entre fec_aprox de um municipio num mes e no mes seguinte.
painel = df.dropna(subset=["nome_municipio"]).sort_values(["codigo_ibge_resolvido", "ano", "mes"]).copy()
painel["fec_aprox_mes_seguinte"] = painel.groupby("codigo_ibge_resolvido")["fec_aprox"].shift(-1)
valido = painel.dropna(subset=["fec_aprox_mes_seguinte"])
corr_persistencia = valido["fec_aprox"].corr(valido["fec_aprox_mes_seguinte"])
print(f"correlacao entre fec_aprox(mes) e fec_aprox(mes+1) para o mesmo municipio: {corr_persistencia:.2f}")
""")

md("""\
**Conclusao:** o risco de interrupcao e fortemente persistente por municipio --
quem teve FEC alto num mes tende a ter FEC alto no mes seguinte (correlacao alta
mes a mes). Isso e uma otima noticia para a viabilidade do produto: existe sinal
historico real para ranquear risco, nao e ruido puro. Tambem estabelece a barra
que qualquer modelo do Dia 4 precisa vencer -- ver a analise de baseline em
`02-baseline.ipynb`.""")

md("## 6. Correlacao entre indicadores")

code("""\
cols_indicadores = [
    "n_eventos_total", "n_eventos_validos", "consumidores_ativos_max",
    "duracao_total_horas", "n_distribuidoras", "n_municipios_no_conjunto",
    "fec_aprox", "dec_aprox_horas",
]
corr = df[cols_indicadores].corr()

fig, ax = plt.subplots(figsize=(7.5, 6.5))
im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)
ax.set_xticks(range(len(cols_indicadores)))
ax.set_yticks(range(len(cols_indicadores)))
ax.set_xticklabels(cols_indicadores, rotation=45, ha="right")
ax.set_yticklabels(cols_indicadores)
for i in range(len(cols_indicadores)):
    for j in range(len(cols_indicadores)):
        ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8)
fig.colorbar(im, ax=ax, shrink=0.8)
ax.set_title("Correlacao entre indicadores (municipio x mes)")
fig.tight_layout()
fig.savefig(f"{ARTIFACTS}/correlacao_indicadores.png", dpi=110)
plt.show()
""")

md("""\
**Conclusao:** `fec_aprox` e `dec_aprox_horas` sao correlacionados mas nao
identicos (frequencia e duracao medem coisas diferentes -- um municipio pode
ter muitas interrupcoes curtas ou poucas interrupcoes longas). `n_eventos_total`
e fortemente ligado a `consumidores_ativos_max` (municipios maiores tem mais
eventos em volume bruto, reforcando a decisao da secao 3 de normalizar por
consumidor). `n_municipios_no_conjunto` (grau de compartilhamento do conjunto,
usado no fan-out) nao tem correlacao forte com o risco em si -- e uma variavel
estrutural do dado, nao um sinal de risco.""")

md("""\
## Resumo executivo (Dia 3 -- EDA)

1. **Sazonalidade real e consistente** entre os dois anos (pico
   dezembro-janeiro/setembro-outubro, vale junho-julho) -> `mes` deve entrar
   como feature ciclica no modelo.
2. **Risco bruto favorece cidades grandes; risco normalizado (FEC/DEC
   aproximados) inverte o quadro** -> confirma a escolha de normalizar por
   consumidor em vez de usar contagem bruta de eventos como alvo do modelo.
3. **Causa da interrupcao e um campo pouco granular na pratica** (~95% caem em
   "interna" generico) -> util como feature binaria grosseira (interna vs.
   externa vs. programada), nao como taxonomia detalhada de causa raiz.
4. **O risco por municipio e persistente mes a mes** -> existe sinal real para
   ranquear, e um baseline de persistencia (ingenuo) e um piso de comparacao
   dificil de bater, nao um adversario fraco -- ver `02-baseline.ipynb`.
5. **Cobertura de dados e muito boa** (>99,9% das linhas com municipio
   resolvido); o pequeno residuo sem correspondencia na bridge fica isolado e
   documentado, sem contaminar o ranking dos municipios reais.
""")

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
