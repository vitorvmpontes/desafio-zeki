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
- O cruzamento de código IBGE → UF pode ter exceções pontuais; a taxa de falha do join é medida e reportada pelo pipeline, não escondida.
- Clima real do mês seguinte não pode entrar como variável preditiva (vazamento de informação) — só normais climatológicas históricas, se houver tempo, ou como análise explicativa separada, nunca como feature de previsão.
- Registros marcados como expurgados (`DscMotivoExpurgo`) são mantidos com uma flag em vez de descartados, para não distorcer silenciosamente os indicadores.

## Histórico de decisões

| Data | Decisão | Motivo |
|---|---|---|
| Dia 1 | Grão de previsão definido como município × mês | Equilíbrio entre robustez estatística e utilidade acionável; alimentador/subestação tem ruído maior e fica fora do escopo desta rodada |
| Dia 1 | Entrega de ML como notebooks + modelo servido pela API, sem retraining em tempo real | O retrain é mensal (via pipeline agendado), não é necessário servir treino sob demanda |
