# Análise de requisitos

O desafio técnico da Zeki deixa problema, solução, público, experiência, tecnologia, dados e uso de IA em aberto — nenhum requisito vem pronto. Este documento é o artefato que registra o trabalho de transformar isso em escopo executável, e é atualizado sempre que uma decisão de escopo muda.

## Problema

Hoje não existe uma forma simples de responder "como está a qualidade de energia no meu município, e como isso deve evoluir no próximo mês?". Os dados da ANEEL são publicados como despejos anuais brutos (arquivos de até ~260 MB, 26 colunas com códigos pouco autoexplicativos, sem UF e sem duração calculada), sem API de consulta — e mesmo quem processa esses dados só enxerga indicadores **históricos**, medidos depois do problema já ter acontecido.

## Personas

**Primária — analista de fiscalização/planejamento da ANEEL.** Hoje só tem acesso a indicadores de continuidade históricos (DEC/FEC) e precisa priorizar manualmente onde direcionar atenção regulatória.

**Secundária — gestor de manutenção de uma distribuidora.** Quer antecipar onde investir em poda e inspeção preventiva antes da próxima janela de risco, em vez de reagir depois da interrupção.

## Critério de sucesso

Um usuário consegue, em poucos cliques, ver quais municípios têm maior risco previsto para o mês seguinte, entender por quê (causas dominantes), e comparar a previsão anterior com o que de fato aconteceu — confiança suficiente para embasar priorização sem precisar entender o modelo por baixo.

## Escopo (MoSCoW)

| Prioridade | Item |
|---|---|
| **Must** | Pipeline de ingestão idempotente: ANEEL → limpeza → agregado município-mês |
| **Must** | Modelo de risco por município/mês com baseline, validação temporal e interpretabilidade |
| **Must** | API (FastAPI) expondo indicadores históricos, ranking previsto e explicação |
| **Must** | Frontend mínimo: ranking + detalhe do município (histórico vs. previsto, causas) |
| **Must** | README com problema, decisões e "como rodar do zero" + vídeo |
| **Should** | Docker Compose de um comando (API + banco + frontend) |
| **Should** | Testes automatizados do ETL e da API |
| **Should** | GitHub Actions mensal: reprocessa dados e republica o ranking |
| **Could** | Enriquecimento com clima (INMET) na análise explicativa |
| **Could** | Visualização geográfica (mapa) além da tabela |
| **Could** | Comparação entre distribuidoras |
| **Won't** (nesta rodada) | Granularidade por alimentador/subestação, contas de usuário, app mobile, hospedagem permanente |

## Premissas e riscos assumidos

- Municípios com poucos eventos históricos terão previsão menos confiável — o modelo usa um *fallback* para a média histórica regional nesses casos, e isso fica explícito na explicação exibida ao usuário.
- **O dataset de interrupções não identifica o município diretamente** (isso só foi descoberto ao processar o Parquet real — a documentação oficial da ANEEL descrevia um `CodMunicipioIBGE` que não existe no arquivo publicado; ver `docs/DEVLOG.md`). O município é obtido cruzando o conjunto de unidades consumidoras (`IdeConjuntoUnidadeConsumidora`) com o dataset separado "IndQual Município". A taxa de conjuntos sem correspondência nesse cruzamento é medida e reportada pelo pipeline, não escondida.
- **Um conjunto pode atender mais de um município** — nos dados reais de 2024/2025, 40,5% dos conjuntos (6.135 de 15.162) atendem mais de um. Em vez de escolher arbitrariamente um "município principal" por conjunto, cada evento é distribuído (fan-out) entre todos os municípios do seu conjunto, com peso `1/n_municipios_no_conjunto` — o total nacional de eventos não é inflado, mas a resolução fica mais grosseira exatamente nesses conjuntos compartilhados. Essa é uma limitação real do dado publicado pela ANEEL (que não reporta em qual parte do conjunto o evento ocorreu), não do pipeline, e é reportada como tal (`n_municipios_no_conjunto`) em vez de escondida atrás de uma escolha arbitrária.
- Clima real do mês seguinte não pode entrar como variável preditiva (vazamento de informação) — só normais climatológicas históricas, se houver tempo, ou como análise explicativa separada, nunca como feature de previsão.
- **Não existe campo equivalente a "expurgado"** no schema real (o campo `DscMotivoExpurgo` descrito na documentação oficial não está no Parquet publicado). O filtro análogo disponível é `DscTipoInterrupcao` (Programada / Não Programada): interrupções programadas são mantidas com uma flag (`programada`) em vez de descartadas, mas esse conceito não é semanticamente idêntico ao expurgo oficial da ANEEL (que também exclui, por exemplo, eventos de força maior) — é a aproximação honesta possível com os campos realmente publicados.
- O código de motivo da interrupção (`IdeMotivoInterrupcao`) é mantido bruto — não há dicionário de dados publicado junto do Parquet decodificando seus valores, e decodificá-lo por suposição inventaria uma interpretação não verificada.

## Histórico de decisões

| Data | Decisão | Motivo |
|---|---|---|
| Dia 1 | Grão de previsão definido como município × mês | Equilíbrio entre robustez estatística e utilidade acionável; alimentador/subestação tem ruído maior e fica fora do escopo desta rodada |
| Dia 1 | Entrega de ML como notebooks + modelo servido pela API, sem retraining em tempo real | O retrain é mensal (via pipeline agendado), não é necessário servir treino sob demanda |
| Dia 2 (atualização) | Município resolvido via bridge conjunto→município (dataset "IndQual Município"), não mais via `CodMunicipioIBGE` direto | O schema real do Parquet de interrupções não tem esse campo — só foi descoberto ao rodar o pipeline contra o servidor de verdade e receber `KeyError` |
| Dia 2 (atualização) | Conjuntos que atendem mais de um município têm seus eventos distribuídos (fan-out, peso `1/n`) entre todos eles, em vez de atribuídos a um único município "principal" | 40,5% dos conjuntos reais atendem mais de um município — escolher um único seria uma decisão arbitrária sem base nos dados; o fan-out ponderado mantém o total nacional consistente e reporta a perda de resolução explicitamente |
| Dia 2 (atualização) | Conceito de "expurgado" substituído por "programada" (`DscTipoInterrupcao`) | `DscMotivoExpurgo` não existe no schema real; `DscTipoInterrupcao` é o filtro documentalmente mais próximo disponível |
| Dia 3 | Alvo do modelo de risco definido como `fec_aprox` (frequência aproximada por consumidor), não volume bruto de eventos | EDA (`ml/notebooks/01-eda.ipynb`) mostrou que o volume bruto de eventos é dominado pelo tamanho do município (mais consumidores, mais eventos); normalizar por consumidor é o que de fato mede risco comparável entre municípios de tamanhos diferentes |
| Dia 3 | Baseline oficial definido como a média entre a persistência do mês anterior e a persistência sazonal (mesmo mês do ano anterior) | Testado contra os 12 meses de 2025 (`ml/notebooks/02-baseline.ipynb`): essa combinação supera cada persistência isolada e a média histórica expandida em MAE, RMSE, correlação de ranking (Spearman) e precisão no top 10% de risco — vira o piso de comparação obrigatório para os modelos do Dia 4 |
| Dia 3 | Avaliação de risco por município só considera municípios com os 24 meses completos de histórico (~93% dos municípios reais) | "Prever o mês seguinte" exige um histórico contínuo para comparar; municípios com buracos no histórico (incluindo o resíduo sem correspondência na bridge) ficam fora da validação do baseline, mas não são descartados do pipeline de dados — tratamento deles (provável fallback por média regional) é ponto em aberto para o Dia 4 |
| Dia 4 | Sazonalidade entra no modelo via `mes_sin`/`mes_cos` (codificação cíclica), não via uma defasagem individual de 12 meses por município | Com só 24 meses de histórico, uma defasagem sazonal (t-12) só existiria a partir do 13º mês de cada município — deixando o treino (meses-alvo de 2024) sem nenhum exemplo dessa feature, já que só passaria a existir a partir de jan/2025 (o próprio período de teste). A codificação cíclica captura o efeito sazonal agregado (visto na EDA) a partir de qualquer ponto do histórico |
| Dia 4 | GLM Poisson/binomial negativa modelam a CONTAGEM de eventos do mês seguinte com exposição (consumidores conhecidos), não `fec_aprox` diretamente | É a forma estatisticamente correta de modelar uma taxa tipo FEC (via `statsmodels`, que tem offset/exposure nativo); a previsão final em taxa é sempre contagem prevista dividida pela exposição |
| Dia 4 | Modelo escolhido para a API (Dia 5): gradient boosting, mesmo sem superar o baseline combinado do Dia 3 na precisão do top 10% | É o melhor dos três modelos "de verdade" treinados (Spearman quase empatado com o baseline), lida nativamente com valores faltantes e categóricas; o baseline do Dia 3 continua exposto ao lado da previsão como referência, e a diferença remanescente é atribuída à falta de profundidade histórica para a defasagem sazonal individual — não a uma limitação do modelo em si |
| Dia 4 | Avaliação de interpretabilidade usa importância por permutação como principal, não SHAP | SHAP (`TreeExplainer`) não roda com as categóricas no formato nativo do `HistGradientBoostingRegressor`, e mesmo recodificado devolve um ranking instável (diferente da permutação) por causa da forte colinearidade entre as features de defasagem — permutação, medida direto no erro final, é mais confiável aqui; ver `ml/notebooks/04-modelagem.ipynb` |
