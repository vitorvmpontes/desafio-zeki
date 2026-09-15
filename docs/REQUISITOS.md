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
