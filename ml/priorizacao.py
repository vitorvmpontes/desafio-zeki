"""Priorização de ação para o gestor de manutenção da distribuidora --
substitui a página de Análises (Dia 6, extensão) por uma visão orientada a
decisão de mitigação de quedas de energia.

Contexto da mudança (ver `docs/DEVLOG.md`, pivot "Priorização"): a página de
Análises anterior (`ml/analises.py`) mostrava o que o dado nacional revela
(sazonalidade, disparidade regional, mix de causas, persistência), mas não
respondia a pergunta de quem precisa AGIR: onde investir a fiscalização e
manutenção preventiva do mês, com qual ação, e quando se preparar. Este
módulo cobre as quatro entregas confirmadas com o usuário:

1. **Priorização por impacto real** (`impacto_esperado`) -- ranqueia por
   `previsao_modelo x consumidores_ativos_max`, não só pela taxa por
   consumidor (`fec_aprox`/`previsao_modelo` isolados). Dois municípios com o
   mesmo risco por consumidor não têm o mesmo impacto: um com 500 mil
   consumidores pesa muito mais que um com 500, e o ranking anterior
   (`/ranking`, por `previsao_modelo` isolado) não captura essa diferença --
   ver `docs/REQUISITOS.md` para a decisão registrada.
2. **Recomendação de ação por município** (`recomendar_acao`) -- baseada,
   PRIMARIAMENTE, no padrão de frequência (`fec_aprox`) x duração
   (`dec_aprox_horas`/MTTR) do município comparado ao percentil nacional dos
   últimos 12 meses (`padrao_frequencia_duracao`) -- não mais na causa
   reportada pela distribuidora. Motivo da mudança (ver `docs/DEVLOG.md`,
   "ação recomendada baseada em causa não ajudava"): a taxonomia de causa
   mais granular (`causas_taxonomia_acionavel`, mantida abaixo como sinal
   SECUNDÁRIO) só tem detalhe suficiente em ~10% dos municípios -- e,
   verificado com dado real, justamente NENHUM dos municípios do topo do
   ranking por impacto (as maiores cidades do país) está nesses 10%, o que
   fazia a ação recomendada repetir o mesmo texto genérico linha após linha
   exatamente onde ela mais precisava ser útil. `fec_aprox`/`dec_aprox_horas`,
   ao contrário da causa, existem para 100% dos municípios, então o padrão
   frequência x duração sempre tem algo concreto a dizer: distingue "muitos
   eventos curtos" (aponta pra vulnerabilidade física da rede -- proteção,
   vegetação) de "poucos eventos longos" (aponta pra gargalo logístico de
   reparo) de "crítico nas duas" de "dentro do padrão nacional". A causa
   detalhada, quando existe, continua aparecendo como evidência adicional na
   recomendação -- não foi descartada, só deixou de ser a única base.
3. **Calendário sazonal de preparação** (`calendario_sazonal`) -- reaproveita
   `sazonalidade_nacional` (`ml/analises.py`), a única peça da página antiga
   que sobrevive, reenquadrada como "quando antecipar a preparação" em vez de
   só "gráfico de volume por mês".
4. **Municípios piorando vs. melhorando** (`calcular_tendencia`) -- nível de
   risco sozinho (alto/médio/baixo) não diz se a situação está piorando ou
   estabilizando; um município "médio" que dobrou de risco em 3 meses é mais
   urgente para investigar do que um "alto" que já vem caindo.

Pedido adicional do usuário: uma seção "Desempenho geográfico e qualidade
regional", cobrindo:

5. **Mapeamento de hotspots** (`hotspots_geograficos`) -- municípios com maior
   frequência E duração de interrupções nos últimos meses. Diferente do
   ranking por impacto (prospectivo, usa a previsão do modelo), isto é
   retrospectivo: "onde o problema mais aconteceu de verdade" no histórico
   recente. **Limitação real de granularidade, confirmada com o usuário**: o
   dataset público da ANEEL usado neste projeto (Interrupções de Energia
   Elétrica nas Redes de Distribuição) só identifica o *conjunto de unidades
   consumidoras*, que o pipeline resolve para *município* (`etl/ibge.py`) --
   não existe coluna de subestação/alimentador no arquivo publicado, então
   hotspot aqui é por município, não por ativo da rede (decisão de grão
   registrada desde o Dia 1, `docs/REQUISITOS.md`).
6. **MTTR -- tempo médio de reparo** (`mttr_por_regiao`) -- `duracao_total_horas
   / n_eventos_validos` (média de horas por evento, não por consumidor como
   `dec_aprox_horas`) é uma proxy honesta de tempo de restabelecimento, mas
   **não temos uma classificação oficial urbano/rural por município** nos
   dados atuais (confirmado com o usuário) -- a comparação usa região
   (Norte/Nordeste/Sul/Sudeste/Centro-Oeste) e UF, que são reais e oficiais,
   em vez de inventar um proxy de urbano/rural.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.analises import sazonalidade_nacional

COL_ID = "codigo_ibge_resolvido"
TARGET = "fec_aprox"

# Ordem de prioridade na classificação: a primeira palavra-chave que bater no
# nome da coluna decide o balde. Escolhida inspecionando as 46 colunas reais
# de causa do dataset (`data/processed/municipio_mes.parquet`) -- ver
# `docs/DEVLOG.md` para a lista completa conferida manualmente.
TAXONOMIA_ACIONAVEL = (
    ("ambiental", "meio_ambiente"),
    ("equipamento", "proprias_do_sistema"),
    ("terceiros", "terceiros"),
    ("operacional", "falha_operacional"),
)

# Colunas de causa que sobram (genérica sem detalhe, cancelamentos,
# comunicação, manutenção/alteração PROGRAMADA -- não é um risco a mitigar,
# é uma interrupção planejada) caem em "generica_sem_detalhe": não sustentam
# nenhuma recomendação específica de ação corretiva.

ACOES_POR_CAUSA = {
    "ambiental": (
        "Priorizar poda de vegetação e reforço de proteção contra queda de árvores/galhos na rede aérea; "
        "inspecionar trechos com histórico de descarga atmosférica ou alagamento."
    ),
    "equipamento": (
        "Priorizar inspeção e troca preventiva de equipamentos e materiais de rede (transformadores, cabos, "
        "isoladores) -- indício de falha de material/equipamento ou sobrecarga recorrente."
    ),
    "terceiros": (
        "Reforçar fiscalização, sinalização e cercamento contra danos por terceiros (obras, vandalismo, "
        "ligações clandestinas, colisões) na área de concessão."
    ),
    "operacional": (
        "Revisar procedimentos operacionais e treinamento de equipe de campo -- indício de falha operacional "
        "recorrente nas interrupções recentes."
    ),
}


def causas_taxonomia_acionavel(painel_municipio: pd.DataFrame, ultimos_n_meses: int = 12) -> dict[str, float]:
    """Proporção de eventos válidos do município (últimos meses observados)
    em cada balde acionável, mais o resíduo "generica_sem_detalhe" -- mesma
    ideia de `api/servico.py::_causas_dominantes`, mas com granularidade
    suficiente para virar uma recomendação de ação, não só um rótulo."""
    df = painel_municipio.sort_values(["ano", "mes"]).tail(ultimos_n_meses)
    causa_cols = [c for c in df.columns if c.startswith("causa_")]
    total_validos = df["n_eventos_validos"].sum()
    if not total_validos or pd.isna(total_validos) or total_validos <= 0:
        return {}

    soma_causas = df[causa_cols].sum()
    classificado = pd.Series(0.0, index=["ambiental", "equipamento", "terceiros", "operacional"])
    usados: set[str] = set()

    for balde, palavra_chave in TAXONOMIA_ACIONAVEL:
        cols = [c for c in causa_cols if palavra_chave in c and c not in usados]
        classificado[balde] = soma_causas[cols].sum() if cols else 0.0
        usados.update(cols)

    generica = float(total_validos) - float(classificado.sum())
    resultado = {balde: round(float(valor) / float(total_validos), 4) for balde, valor in classificado.items()}
    resultado["generica_sem_detalhe"] = round(max(generica, 0.0) / float(total_validos), 4)
    return resultado


# Limiares do padrao frequencia x duracao -- percentis (0-100) contra TODOS
# os municipios do pais, mesma janela de 12 meses. 75 = quarto superior
# nacional (mesmo corte conceitual de "top 25%" usado em outros lugares do
# produto, ver risco.ts::classificarRisco); 20 pontos de diferenca entre as
# duas dimensoes e o que separa um municipio genuinamente "dominado" por uma
# das duas (frequencia OU duracao) de um municipio ruim nas duas ao mesmo
# tempo.
LIMIAR_PERCENTIL_CRITICO = 75.0
LIMIAR_PERCENTIL_MODERADO = 50.0
LIMIAR_GAP_DOMINANTE = 20.0

# Limiares da causa reportada, mantidos do desenho original (ver
# `causas_taxonomia_acionavel`) -- agora usados so para decidir se a causa
# entra na PROSA da recomendacao como evidencia adicional, nao mais como a
# unica base da recomendacao (ver docstring do modulo).
LIMIAR_CAUSA_ALTA = 0.40
LIMIAR_CAUSA_MEDIA = 0.15


def classificar_padrao_frequencia_duracao(percentil_frequencia: float | None, percentil_duracao: float | None) -> dict:
    """Classifica um município num de 5 padrões a partir de onde ele cai no
    percentil NACIONAL de frequência (`fec_aprox`) e duração
    (`dec_aprox_horas`) dos últimos 12 meses (ver `padrao_frequencia_duracao`
    para o cálculo dos percentis) -- a base da nova `recomendar_acao` (ver
    docstring do módulo para o porquê da mudança).

    Ao contrário da causa reportada, `fec_aprox`/`dec_aprox_horas` existem
    para 100% dos municípios -- por isso essa classificação nunca cai em
    "sem dado" a não ser que o município tenha histórico curto demais
    (`minimo_meses` de `padrao_frequencia_duracao`) para entrar na janela."""
    if percentil_frequencia is None or percentil_duracao is None or pd.isna(percentil_frequencia) or pd.isna(percentil_duracao):
        return {
            "padrao": "sem_dado",
            "confianca": "sem_dado",
            "texto": (
                "Sem meses suficientes no histórico recente para calcular o padrão de frequência/duração "
                "deste município."
            ),
            "percentil_frequencia": None,
            "percentil_duracao": None,
        }

    gap = percentil_frequencia - percentil_duracao

    if percentil_frequencia >= LIMIAR_PERCENTIL_CRITICO and percentil_duracao >= LIMIAR_PERCENTIL_CRITICO:
        padrao = "critico_ambos"
        confianca = "alta"
        texto = (
            f"Frequência E duração entre as piores do país nos últimos 12 meses (percentil "
            f"{percentil_frequencia:.0f} e {percentil_duracao:.0f}) -- caso crítico nas duas dimensões: "
            f"priorizar como urgência, com reforço de proteção da rede e revisão da logística de "
            f"resposta/reparo ao mesmo tempo."
        )
    elif percentil_frequencia >= LIMIAR_PERCENTIL_CRITICO and gap >= LIMIAR_GAP_DOMINANTE:
        padrao = "frequencia_dominante"
        confianca = "alta" if percentil_frequencia >= 90 else "media"
        texto = (
            f"Muitos eventos de curta duração: frequência entre as piores do país (percentil "
            f"{percentil_frequencia:.0f}), duração dentro da média (percentil {percentil_duracao:.0f}) -- "
            f"indício de vulnerabilidade física da rede (proteção, vegetação, sobrecarga), não de gargalo "
            f"logístico; priorizar inspeção preventiva e reforço de proteção mesmo sem causa detalhada "
            f"reportada pela distribuidora."
        )
    elif percentil_duracao >= LIMIAR_PERCENTIL_CRITICO and -gap >= LIMIAR_GAP_DOMINANTE:
        padrao = "duracao_dominante"
        confianca = "alta" if percentil_duracao >= 90 else "media"
        texto = (
            f"Poucos eventos, mas de longa duração: duração entre as piores do país (percentil "
            f"{percentil_duracao:.0f}), frequência dentro da média (percentil {percentil_frequencia:.0f}) -- "
            f"indício de gargalo no restabelecimento (deslocamento de equipe, disponibilidade de peças), "
            f"não de causa recorrente; priorizar revisão do tempo de resposta e reforço de equipes de campo."
        )
    elif percentil_frequencia >= LIMIAR_PERCENTIL_MODERADO or percentil_duracao >= LIMIAR_PERCENTIL_MODERADO:
        padrao = "atencao_moderada"
        confianca = "media"
        texto = (
            f"Frequência e/ou duração acima da mediana nacional nos últimos 12 meses (percentil "
            f"{percentil_frequencia:.0f} / {percentil_duracao:.0f}), sem um padrão extremo -- acompanhar de "
            f"perto e reavaliar junto com a tendência dos últimos meses (ver piorando/melhorando)."
        )
    else:
        padrao = "dentro_do_padrao"
        confianca = "baixa"
        texto = (
            f"Frequência e duração dentro da faixa mediana do país nos últimos 12 meses (percentil "
            f"{percentil_frequencia:.0f} / {percentil_duracao:.0f}) -- o impacto esperado alto vem "
            f"principalmente do volume de consumidores atendidos, não de um padrão local ruim; risco aqui é "
            f"mais de escala do que de qualidade de serviço."
        )

    return {
        "padrao": padrao,
        "confianca": confianca,
        "texto": texto,
        "percentil_frequencia": round(float(percentil_frequencia), 1),
        "percentil_duracao": round(float(percentil_duracao), 1),
    }


def recomendar_acao(
    percentil_frequencia: float | None, percentil_duracao: float | None, taxonomia: dict[str, float] | None = None
) -> dict:
    """Recomendação de ação para um município -- combina o padrão
    frequência x duração (base, sempre disponível, ver
    `classificar_padrao_frequencia_duracao`) com a causa reportada pela
    distribuidora, quando existir, como evidência ADICIONAL (não mais a
    única base -- ver docstring do módulo).

    `causa_dominante`/`percentual_causa_dominante` continuam preenchidos
    sempre que existe algum evento com causa acionável (>0%), mesmo abaixo
    do limiar de menção na prosa -- quem quiser conferir o sinal fraco
    ainda tem acesso ao número; só não polui a frase quando é fraco demais
    pra sustentar uma ação."""
    base = classificar_padrao_frequencia_duracao(percentil_frequencia, percentil_duracao)
    if base["padrao"] == "sem_dado":
        return {
            "acao_recomendada": base["texto"],
            "confianca_recomendacao": "sem_dado",
            "padrao_operacional": "sem_dado",
            "percentil_frequencia": None,
            "percentil_duracao": None,
            "causa_dominante": None,
            "percentual_causa_dominante": None,
        }

    texto = base["texto"]
    confianca = base["confianca"]
    causa_dominante = None
    percentual_causa = None

    acionaveis = {k: v for k, v in (taxonomia or {}).items() if k != "generica_sem_detalhe"}
    candidato = max(acionaveis, key=acionaveis.get) if acionaveis else None
    percentual = acionaveis.get(candidato, 0.0) if candidato else 0.0
    if candidato and percentual > 0:
        causa_dominante = candidato
        percentual_causa = round(percentual * 100, 1)
        if percentual >= LIMIAR_CAUSA_ALTA:
            confianca = "alta"
            texto += (
                f" Causa dominante reportada pela distribuidora: '{candidato}' ({percentual_causa:.0f}% dos "
                f"eventos) -- {ACOES_POR_CAUSA[candidato]}"
            )
        elif percentual >= LIMIAR_CAUSA_MEDIA:
            confianca = confianca if confianca == "alta" else "media"
            texto += f" Sinal adicional de causa reportada: '{candidato}' ({percentual_causa:.0f}% dos eventos)."
        # abaixo do limiar de media: campo fica preenchido para quem conferir,
        # mas o sinal e fraco demais pra entrar na prosa da recomendacao.

    return {
        "acao_recomendada": texto,
        "confianca_recomendacao": confianca,
        "padrao_operacional": base["padrao"],
        "percentil_frequencia": base["percentil_frequencia"],
        "percentil_duracao": base["percentil_duracao"],
        "causa_dominante": causa_dominante,
        "percentual_causa_dominante": percentual_causa,
    }


def adicionar_impacto_esperado(previsao: pd.DataFrame) -> pd.DataFrame:
    """Adiciona `impacto_esperado = previsao_modelo x exposicao` -- uma
    proxy de "interrupções-consumidor" esperadas no mês seguinte, não só a
    taxa por consumidor. `exposicao` já é `consumidores_ativos_max` bruto
    (ver `ml/features.py::COLUNAS_SAIDA`), então não precisa de merge com
    `estado.municipios` para ter essa coluna."""
    df = previsao.copy()
    df["impacto_esperado"] = df["previsao_modelo"] * df["exposicao"]
    return df


def calcular_tendencia(painel: pd.DataFrame) -> pd.DataFrame:
    """Compara a média de `fec_aprox` dos últimos 3 meses disponíveis de cada
    município com a média dos 3 meses imediatamente anteriores -- vetorizado
    (sem `.apply()` por município, ver nota de performance/correção em
    `ml/features.py` sobre `.apply()` e o Arrow backend do pandas 3.x).

    Exige os 6 meses mais recentes CONSECUTIVOS (sem buraco no meio) --
    município com histórico curto (<6 meses) ou com buraco nos últimos 6
    meses fica de fora, para não comparar janelas que na verdade pulam
    meses sem dado (mesmo cuidado de `ml/features.py::construir_dataset`
    com os buracos reais do dado, ver `docs/DEVLOG.md`, Dia 4)."""
    df = painel.dropna(subset=["nome_municipio", TARGET]).copy()
    # ordinal simples (ano*12 + mes) em vez de aritmetica de pd.Period -- a
    # subtracao de dois pd.Period vira um objeto DateOffset (`<5 * MonthEnds>`),
    # nao um int, entao comparar com `== 5` direto falha silenciosamente.
    df["_ordinal"] = df["ano"] * 12 + df["mes"]
    df = df.sort_values([COL_ID, "_ordinal"])

    g = df.groupby(COL_ID, sort=False)
    df["_posicao_do_fim"] = g.cumcount(ascending=False)  # 0 = mes mais recente do municipio
    ultimos_6 = df[df["_posicao_do_fim"] < 6].copy()

    contagem = ultimos_6.groupby(COL_ID)[TARGET].transform("size")
    ordinal_min = ultimos_6.groupby(COL_ID)["_ordinal"].transform("min")
    ordinal_max = ultimos_6.groupby(COL_ID)["_ordinal"].transform("max")
    consecutivos = (ordinal_max - ordinal_min) == 5  # 6 meses sem buraco = 5 "saltos" de 1 mes
    ultimos_6 = ultimos_6[(contagem == 6) & consecutivos]

    recentes = ultimos_6[ultimos_6["_posicao_do_fim"] < 3].groupby(COL_ID)[TARGET].mean()
    anteriores = ultimos_6[ultimos_6["_posicao_do_fim"] >= 3].groupby(COL_ID)[TARGET].mean()

    resultado = pd.DataFrame({"fec_aprox_medio_recente": recentes, "fec_aprox_medio_anterior": anteriores})
    resultado = resultado.dropna()
    denominador = resultado["fec_aprox_medio_anterior"].replace(0, np.nan)
    resultado["variacao_pct"] = (
        (resultado["fec_aprox_medio_recente"] - resultado["fec_aprox_medio_anterior"]) / denominador * 100
    )
    resultado = resultado.dropna(subset=["variacao_pct"]).reset_index()
    return resultado


def tendencia_top(painel: pd.DataFrame, municipios_info: pd.DataFrame, top_n: int = 10) -> dict:
    """Top N municípios piorando (maior alta de risco) e top N melhorando
    (maior queda) -- calculado uma vez (não depende do `limite` da
    requisição, ao contrário do ranking por impacto)."""
    tendencia = calcular_tendencia(painel)
    tendencia = tendencia.merge(municipios_info, on=COL_ID, how="left")

    def _formatar(df: pd.DataFrame) -> list[dict]:
        return [
            {
                "codigo_ibge": row[COL_ID],
                "nome": row["nome_municipio"],
                "uf": row["uf_sigla"],
                "regiao": row["regiao"],
                "variacao_pct": round(float(row["variacao_pct"]), 1),
                "fec_aprox_medio_recente": round(float(row["fec_aprox_medio_recente"]), 5),
                "fec_aprox_medio_anterior": round(float(row["fec_aprox_medio_anterior"]), 5),
            }
            for row in df.to_dict(orient="records")
        ]

    piorando = tendencia.sort_values("variacao_pct", ascending=False).head(top_n)
    melhorando = tendencia.sort_values("variacao_pct", ascending=True).head(top_n)
    return {"piorando": _formatar(piorando), "melhorando": _formatar(melhorando)}


# Meses de pico nacional conhecidos desde o EDA do Dia 3 (verão/vendaval
# set-jan) -- usados só para redigir a recomendação textual do calendário;
# os dados retornados (`sazonalidade_nacional`) são sempre recalculados do
# painel real, isso aqui não hardcoda número nenhum.
_MESES_NOME = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio", 6: "junho",
    7: "julho", 8: "agosto", 9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def calendario_sazonal(painel: pd.DataFrame, top_n_meses: int = 3) -> dict:
    """Reaproveita `sazonalidade_nacional` (`ml/analises.py`) -- agrega por
    mês do calendário (não ano/mês) para achar os meses historicamente mais
    críticos, e traduz isso numa recomendação de janela de preparação."""
    pontos = sazonalidade_nacional(painel)
    df = pd.DataFrame(pontos)
    por_mes_calendario = df.groupby("mes")["n_eventos_total"].mean().sort_values(ascending=False)
    meses_criticos = [int(m) for m in por_mes_calendario.head(top_n_meses).index]
    nomes_criticos = [_MESES_NOME[m] for m in sorted(meses_criticos)]

    recomendacao = (
        f"Historicamente, {', '.join(nomes_criticos)} concentram o maior volume de interrupções no país "
        f"(média mensal de eventos, 2024-2025) -- antecipar poda, inspeção de equipamento e reforço de "
        f"equipes de campo nos meses imediatamente anteriores reduz o risco na janela mais crítica do ano."
    )
    return {"pontos": pontos, "meses_criticos": sorted(meses_criticos), "recomendacao": recomendacao}


def _janela_ultimos_meses(painel: pd.DataFrame, ultimos_n_meses: int) -> pd.DataFrame:
    """Filtra o painel para os últimos N meses do CALENDÁRIO GLOBAL do
    dataset (não os últimos N meses de cada município) -- para comparar
    hotspots/MTTR entre municípios na mesma janela de tempo, não em janelas
    deslocadas por município."""
    df = painel.dropna(subset=["nome_municipio"]).copy()
    df["periodo"] = pd.to_datetime({"year": df["ano"], "month": df["mes"], "day": 1}).dt.to_period("M")
    ultimo_periodo = df["periodo"].max()
    return df[df["periodo"] > ultimo_periodo - ultimos_n_meses]


def _agregado_frequencia_duracao(painel: pd.DataFrame, ultimos_n_meses: int, minimo_meses: int) -> pd.DataFrame:
    """Agregação compartilhada por `hotspots_geograficos` E
    `padrao_frequencia_duracao`: frequência (`fec_aprox`) e duração
    (`dec_aprox_horas`) médias por município na janela, MAIS o percentil
    NACIONAL de cada uma (0-100, `rank(pct=True)`) -- calculado sobre TODOS
    os municípios da janela de uma vez, nunca por município isolado (um
    percentil só faz sentido contra a distribuição inteira). Retorna a
    tabela completa, sem truncar -- quem trunca por `top_n` é
    `hotspots_geograficos`; `padrao_frequencia_duracao` usa a tabela inteira,
    porque a ação recomendada precisa do percentil de qualquer município do
    ranking por impacto, não só dos piores 15."""
    janela = _janela_ultimos_meses(painel, ultimos_n_meses)
    agregado = janela.groupby(COL_ID).agg(
        nome_municipio=("nome_municipio", "last"),
        uf_sigla=("uf_sigla", "last"),
        regiao=("regiao", "last"),
        fec_aprox_medio=(TARGET, "mean"),
        dec_aprox_horas_medio=("dec_aprox_horas", "mean"),
        n_eventos_validos=("n_eventos_validos", "sum"),
        duracao_total_horas=("duracao_total_horas", "sum"),
        n_meses=(TARGET, "count"),
    )
    agregado = agregado[agregado["n_meses"] >= minimo_meses]
    agregado["mttr_horas"] = agregado["duracao_total_horas"] / agregado["n_eventos_validos"].replace(0, np.nan)
    agregado["percentil_frequencia"] = agregado["fec_aprox_medio"].rank(pct=True) * 100
    agregado["percentil_duracao"] = agregado["dec_aprox_horas_medio"].rank(pct=True) * 100
    agregado["indice_hotspot"] = (agregado["percentil_frequencia"] + agregado["percentil_duracao"]) / 2
    return agregado


def padrao_frequencia_duracao(painel: pd.DataFrame, ultimos_n_meses: int = 12, minimo_meses: int = 3) -> pd.DataFrame:
    """Tabela completa (todos os municípios, não só os piores) de percentil
    nacional de frequência e duração dos últimos `ultimos_n_meses` -- a base
    de dado da nova `recomendar_acao` (ver docstring do módulo). Pré-computada
    UMA VEZ em `montar_estado`, igual a `desempenho_geografico` (não depende
    do `limite` da requisição de `/priorizacao`).

    Indexada por `codigo_ibge_resolvido`, só com as colunas que
    `recomendar_acao` precisa -- município fora desta tabela (histórico
    curto demais, `minimo_meses`) não tem padrão calculável, e
    `classificar_padrao_frequencia_duracao` trata isso como "sem_dado", não
    como um erro."""
    agregado = _agregado_frequencia_duracao(painel, ultimos_n_meses, minimo_meses)
    return agregado[["percentil_frequencia", "percentil_duracao"]]


def hotspots_geograficos(
    painel: pd.DataFrame, ultimos_n_meses: int = 12, top_n: int = 15, minimo_meses: int = 3
) -> list[dict]:
    """Municípios com maior frequência E duração de interrupções nos últimos
    `ultimos_n_meses`, NORMALIZADAS por consumidor -- média de `fec_aprox`
    (frequência) e `dec_aprox_horas` (duração), os mesmos indicadores já
    usados no resto do produto, não o volume bruto de eventos.

    **Por que normalizado, não bruto**: o volume bruto de eventos/duração é
    dominado pelo tamanho do município (mais consumidores, mais eventos em
    número absoluto -- mesmo achado da disparidade regional do Dia 3). Um
    hotspot bruto seria só a lista das maiores cidades do país -- que já
    aparece no ranking por impacto (`ranking_por_impacto`, que é justamente
    sobre volume absoluto). Normalizando, o hotspot aqui identifica
    município com MÁ QUALIDADE de serviço (frequência/duração por
    consumidor), retrospectivo (o que já aconteceu), diferente do ranking
    por impacto (prospectivo, usa a previsão do modelo) -- os dois se
    complementam em vez de repetir a mesma lista de grandes cidades.

    `indice_hotspot` é a média dos percentis de frequência e duração média
    (0-100): um município só entra no topo se for ruim nas DUAS dimensões,
    não só numa. Municípios com menos de `minimo_meses` de dado na janela
    são excluídos (estimativa instável com poucos meses).

    Granularidade é município, não subestação/alimentador -- o dado público
    da ANEEL usado aqui não identifica esse nível (ver docstring do módulo)."""
    agregado = _agregado_frequencia_duracao(painel, ultimos_n_meses, minimo_meses)
    top = agregado.sort_values("indice_hotspot", ascending=False).head(top_n).reset_index()
    return [
        {
            "codigo_ibge": row[COL_ID],
            "nome": row["nome_municipio"],
            "uf": row["uf_sigla"],
            "regiao": row["regiao"],
            "fec_aprox_medio": round(float(row["fec_aprox_medio"]), 5),
            "dec_aprox_horas_medio": round(float(row["dec_aprox_horas_medio"]), 3),
            "n_eventos_validos": float(row["n_eventos_validos"]),
            "mttr_horas": round(float(row["mttr_horas"]), 2) if pd.notna(row["mttr_horas"]) else None,
            "indice_hotspot": round(float(row["indice_hotspot"]), 1),
        }
        for row in top.to_dict(orient="records")
    ]


def mttr_por_regiao(painel: pd.DataFrame, ultimos_n_meses: int = 12) -> list[dict]:
    """Tempo médio de reparo (horas por evento -- `duracao_total_horas /
    n_eventos_validos`, diferente de `dec_aprox_horas`, que é por consumidor)
    agregado por região -- comparação usa região/UF (dimensões reais e
    oficiais disponíveis no dado), não urbano/rural (não temos essa
    classificação por município, ver docstring do módulo)."""
    janela = _janela_ultimos_meses(painel, ultimos_n_meses)
    por_regiao = janela.dropna(subset=["regiao"]).groupby("regiao").agg(
        n_eventos_validos=("n_eventos_validos", "sum"),
        duracao_total_horas=("duracao_total_horas", "sum"),
    )
    por_regiao["mttr_horas"] = por_regiao["duracao_total_horas"] / por_regiao["n_eventos_validos"].replace(0, np.nan)
    por_regiao = por_regiao.sort_values("mttr_horas", ascending=False)
    return [
        {
            "regiao": regiao,
            "n_eventos_validos": float(row["n_eventos_validos"]),
            "duracao_total_horas": round(float(row["duracao_total_horas"]), 1),
            "mttr_horas": round(float(row["mttr_horas"]), 2) if pd.notna(row["mttr_horas"]) else None,
        }
        for regiao, row in por_regiao.iterrows()
    ]


def desempenho_geografico(painel: pd.DataFrame, ultimos_n_meses: int = 12, top_n_hotspots: int = 15) -> dict:
    """Monta o payload de "Desempenho geográfico e qualidade regional":
    hotspots por município + MTTR por região, na mesma janela dos últimos
    `ultimos_n_meses` meses -- pré-computado uma vez em `montar_estado`
    (não depende do `limite` da requisição, igual tendência/calendário)."""
    return {
        "janela_meses": ultimos_n_meses,
        "hotspots": hotspots_geograficos(painel, ultimos_n_meses, top_n_hotspots),
        "mttr_por_regiao": mttr_por_regiao(painel, ultimos_n_meses),
        "nota_metodologica": (
            # Versao enxuta (ver docs/DEVLOG.md, "reorganizacao em paginas +
            # tema escuro") -- mantem os 4 fatos que mudam a leitura do
            # numero (granularidade, formula do indice, formula do MTTR,
            # base da comparacao regional), corta a justificativa em prosa.
            "hotspots sao por MUNICIPIO (o dado publico da ANEEL nao identifica subestacao/alimentador). "
            "indice_hotspot e a media dos percentis de fec_aprox e dec_aprox_horas medios POR CONSUMIDOR na "
            "janela -- nao volume bruto, que so refletiria o tamanho do municipio; so entra no topo quem for "
            "ruim nas duas dimensoes. mttr_horas = duracao_total_horas / n_eventos_validos (por EVENTO -- o "
            "unico numero desta secao que NAO e normalizado por consumidor). Comparacao regional usa regiao/UF: "
            "nao ha classificacao urbano/rural por municipio nos dados atuais."
        ),
    }


def ranking_por_impacto(
    previsao_com_impacto: pd.DataFrame, painel: pd.DataFrame, padrao_operacional: pd.DataFrame, limite: int
) -> list[dict]:
    """Top N municípios por impacto esperado, com ação recomendada calculada
    SÓ para esse subconjunto -- computar a taxonomia de causa (sinal
    adicional, ver `recomendar_acao`) para os ~5500 municípios a cada
    requisição seria desperdício; o gestor só precisa da recomendação para
    quem está no topo da lista que ele vai realmente olhar.

    `padrao_operacional` é a tabela de percentil frequência x duração de
    TODOS os municípios (`padrao_frequencia_duracao`, pré-computada uma vez
    em `montar_estado`) -- só o lookup por município acontece aqui, o
    cálculo de percentil nacional não é refeito a cada requisição."""
    df = previsao_com_impacto.sort_values("impacto_esperado", ascending=False).head(limite).reset_index(drop=True)

    itens = []
    for i, row in enumerate(df.to_dict(orient="records")):
        painel_municipio = painel[painel[COL_ID] == row[COL_ID]]
        taxonomia = causas_taxonomia_acionavel(painel_municipio)
        if row[COL_ID] in padrao_operacional.index:
            percentil_frequencia = padrao_operacional.loc[row[COL_ID], "percentil_frequencia"]
            percentil_duracao = padrao_operacional.loc[row[COL_ID], "percentil_duracao"]
        else:
            percentil_frequencia = None
            percentil_duracao = None
        acao = recomendar_acao(percentil_frequencia, percentil_duracao, taxonomia)
        itens.append(
            {
                "posicao": i + 1,
                "codigo_ibge": row[COL_ID],
                "nome": row["nome_municipio"],
                "uf": row["uf_sigla"],
                "regiao": row["regiao"],
                "previsao_modelo": round(float(row["previsao_modelo"]), 5),
                "consumidores_ativos_estimados": float(row["exposicao"]) if pd.notna(row["exposicao"]) else None,
                "impacto_esperado": round(float(row["impacto_esperado"]), 2),
                "acao_recomendada": acao["acao_recomendada"],
                "confianca_recomendacao": acao["confianca_recomendacao"],
                "padrao_operacional": acao["padrao_operacional"],
                "percentil_frequencia": acao["percentil_frequencia"],
                "percentil_duracao": acao["percentil_duracao"],
                "causa_dominante": acao["causa_dominante"],
                "percentual_causa_dominante": acao["percentual_causa_dominante"],
            }
        )
    return itens


