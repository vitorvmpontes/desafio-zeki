# Continua — frontend (`web/`)

Painel web do Continua, em tema escuro, dividido em 4 páginas focadas: ranking de municípios por risco de interrupção de energia, a tela de detalhe de cada município (histórico real vs. previsão, causas dominantes, importância das features) e três páginas de apoio à decisão para o gestor de manutenção da distribuidora -- Priorização ("onde agir agora"), Tendências ("para onde está indo") e Geografia ("onde acontece de verdade", com um mapa real de clusters gerado a partir de um arquivo KML). Consome exclusivamente a API (`api/`) — não fala com o Postgres nem com os artefatos de ML diretamente.

## Stack

- **React + Vite + TypeScript** — escolhido com o usuário no início do Dia 6 (opção recomendada).
- **react-router-dom** — roteamento client-side, seis rotas: `/` (ranking), `/municipios/:codigoIbge` (detalhe), `/priorizacao` (ação imediata), `/tendencias` (piorando/melhorando + calendário sazonal) e `/geografia` (mapa + hotspots + MTTR por região).
- **Recharts** — gráfico de linha (histórico real vs. previsão do modelo vs. baseline) e gráficos de barra (calendário sazonal, MTTR por região) — escolhido junto com a stack (opção recomendada para React).
- **Leaflet + react-leaflet** (Dia 6, extensão "mapa") — mapa de `Geografia.tsx` (`components/MapaClusters.tsx`), com tiles escuros do CARTO Dark Matter (sem chave de API, mesma filosofia de zero-custo do resto do projeto, escolhidos para combinar com o tema escuro do site) — `react-leaflet@5` é a primeira versão com suporte a React 19 (`peerDependencies: react ^19.0.0`), por isso a versão fixada.
- **Google Fonts (Inter)**, carregada via `<link>` em `index.html` (não só declarada em CSS) — pesos 400/500/600/700.
- Sem gerenciador de estado externo (Redux/Zustand/etc.) — o estado é local a cada página (`useState`/`useEffect`), suficiente para telas que só leem dados de uma API read-only.

## Estrutura

```
web/
├── src/
│   ├── lib/
│   │   ├── api.ts       cliente HTTP tipado para os endpoints da API
│   │   └── risco.ts     classificação de nível de risco (percentil) e formatação de fec_aprox
│   ├── components/
│   │   ├── BadgeRisco.tsx
│   │   └── MapaClusters.tsx      mapa real (Leaflet + CARTO Dark Matter) dos clusters de qualidade de servico, a partir do KML gerado pela API
│   ├── pages/
│   │   ├── Ranking.tsx           tabela de ranking (previsto / histórico observado)
│   │   ├── MunicipioDetalhe.tsx  gráfico + explicação da previsão de um município
│   │   ├── Priorizacao.tsx       "onde agir agora": ranking por impacto + ação recomendada por município
│   │   ├── Tendencias.tsx        "para onde está indo": piorando/melhorando (3 vs. 3 meses) + calendário sazonal
│   │   └── Geografia.tsx         "onde acontece de verdade": mapa de clusters (KML) + mapeamento de hotspots + MTTR por região
│   └── App.tsx          roteamento + layout (header/footer)
├── Dockerfile            multi-stage: build (node) -> serve estático (nginx)
├── nginx.conf            fallback de SPA (qualquer rota cai em index.html)
└── .env.example          VITE_API_URL
```

## Como rodar

**Via Docker Compose (recomendado, junto com o resto do projeto):** ver a seção "Como rodar do zero" do README raiz. Resumindo, com a API já de pé em `http://localhost:8000`:

```bash
docker compose up -d --build web   # http://localhost:3000
```

**Em modo de desenvolvimento, isolado (hot-reload):**

```bash
cd web
npm install
cp .env.example .env      # ajuste VITE_API_URL se a API não estiver em localhost:8000
npm run dev                # http://localhost:5173, com hot-reload
```

**Build de produção manual (sem Docker):**

```bash
npm run build    # gera web/dist/ (tsc -b && vite build)
npm run preview  # serve o build de produção localmente, para testar antes de empacotar
```

## Decisões de design

- **`VITE_API_URL` é injetada em tempo de BUILD, não de execução.** É assim que o Vite funciona: a variável de ambiente fica embutida no JavaScript estático gerado por `vite build`, então não pode ser trocada só reiniciando o container — precisa rebuildar a imagem (`docker compose up -d --build web`). No `docker-compose.yml`, isso é repassado como `ARG` do `web/Dockerfile`, valendo o endereço que o **navegador do usuário** alcança (`http://localhost:8000` por padrão) — não o nome interno `api` da rede do compose, que só existe para chamadas servidor-a-servidor.
- **Nível de risco (alto/médio-alto/médio/baixo) é calculado por percentil dentro do ranking atual**, não por um limiar absoluto de `fec_aprox` (`src/lib/risco.ts`). Top 10% = alto, próximos até 35% = médio-alto, até 70% = médio, resto = baixo — o mesmo corte de "top 10%" usado em toda a avaliação do modelo desde o Dia 3. Um limiar absoluto perderia sentido se a distribuição de risco mudar com mais anos de dado.
- **CORS liberado (`allow_origins=["*"]`) na API**, não no frontend — decisão e motivo documentados em `api/main.py`/`docs/REQUISITOS.md`. Sem isso, o navegador bloqueia toda chamada do frontend (origem/porta diferente da API) mesmo a API respondendo 200 normalmente — só aparece testando com um navegador de verdade, não com `curl`/`httpx` (foi como o bug foi encontrado: Playwright headless capturando o erro de CORS no console).
- **Os tipos TypeScript de `src/lib/api.ts` espelham manualmente os schemas Pydantic de `api/schemas.py`.** Não há geração automática de código (ex.: `openapi-typescript`) — decisão pragmática dada a janela do desafio. **Limitação conhecida:** se a API mudar um schema, o frontend não vai quebrar em tempo de build, só em runtime (ou pior, silenciosamente) — ponto de atenção para uma próxima iteração.
- **A previsão "continua" visualmente a partir do último ponto do histórico real** no gráfico (`MunicipioDetalhe.tsx`, `montarPontosGrafico`): o último valor real é duplicado como primeiro ponto das séries "previsto"/"baseline", para a linha tracejada de previsão emendar visualmente na linha sólida do histórico, em vez de deixar um buraco no meio do gráfico.
- **A importância de features exibida no detalhe do município é GLOBAL, não específica daquele município** — mesma limitação já documentada na API (Dia 5), repetida aqui explicitamente na UI (nota metodológica abaixo dos cards de previsão) para não sugerir uma explicação por-instância que os dados não sustentam.
- **A página de Priorização substitui a antiga página de Análises** (ver `docs/DEVLOG.md`, pivot "Priorização") -- o usuário avaliou que Análises descrevia o dataset nacional, mas não ajudava a decidir onde agir para mitigar quedas de energia. Priorização é pensada para o gestor de manutenção da distribuidora, com ranking por **impacto esperado** (não só taxa de risco isolada) e **ação recomendada** por município a partir do mix de causas -- ver `ml/priorizacao.py` e `api/README.md`.
- **Priorização/Tendências/Geografia foram 3 páginas diferentes desde o início dessa funcionalidade, não uma reorganização de conteúdo que existia em outro lugar** -- na prática, porém, elas foram implementadas como seções sucessivas dentro de uma única página (`Priorizacao.tsx`) ao longo de várias extensões do Dia 6, e só depois separadas em 3 rotas quando o usuário apontou que a página tinha ficado sobrecarregada ("duas páginas muito pouco... deixe mais bem organizado", ver `docs/DEVLOG.md`, "Dia 6 (extensão 3)"). Cada página responde a uma pergunta distinta do gestor: **Priorização** = onde agir agora (impacto esperado + ação recomendada); **Tendências** = para onde o risco está indo (piorando/melhorando 3 vs. 3 meses + calendário sazonal de preparação); **Geografia** = onde o problema mais acontece de verdade, olhando os últimos 12 meses (mapa de clusters + mapeamento de hotspots + MTTR por região). As três se cruzam com links explícitos entre si (e para o detalhe de município) em vez de duplicar contexto.
- **Hotspots são retrospectivos (o que já aconteceu) e usam métricas normalizadas por consumidor**, diferente do ranking por impacto (prospectivo, sobre volume absoluto) -- os dois se complementam em vez de mostrar a mesma lista de grandes cidades. Granularidade é por município (não subestação/alimentador -- limitação do dado público da ANEEL); a comparação de MTTR usa região/UF em vez de urbano/rural (classificação que não existe nos dados atuais).
- **Badge de confiança da recomendação usa uma paleta separada da de nível de risco** (`--cor-risco-baixo`/`--cor-risco-medio`/cinza) -- "alta confiança na recomendação" é uma coisa boa (verde), não deveria ser confundida visualmente com "alto risco" (vermelho, usado no ranking).
- **O mapa de clusters (`MapaClusters.tsx`) reaproveita a mesma paleta de 4 níveis já usada em risco/confiança** (`--cor-risco-alto/medio-alto/medio/baixo`, mapeados para crítico/alto/moderado/baixo) em vez de inventar uma paleta nova só para o mapa -- mesma linguagem visual em toda a página.
- **A API já entrega os municípios com lat/lon e severidade prontos (`GET /mapa`)** -- o frontend desenha os marcadores direto (Leaflet `CircleMarker`), sem precisar parsear o arquivo KML no navegador; o KML de verdade (`GET /mapa/kml`) fica disponível como um link de download separado, para quem quiser abrir num visualizador GIS externo (Google Earth/Maps, QGIS). Evita adicionar uma dependência extra de parsing de XML/KML no cliente só para redesenhar o que a API já calculou.
- **`scrollWheelZoom` do mapa é desativado** -- a página tem outros gráficos e tabelas abaixo do mapa; sem isso, rolar a página com o mouse sobre o mapa daria zoom nele em vez de continuar a rolagem da página (comportamento padrão do Leaflet, mas ruim numa página com scroll longo).
- **Tema escuro é uma paleta pensada para fundo escuro, não uma inversão automática da paleta clara** (tokens CSS em `:root`, `src/index.css`) -- cores de risco mantêm o mesmo mapeamento semântico (vermelho=alto .. verde=baixo), só mais claras/saturadas para contraste sobre `--cor-superficie`. Tiles do mapa trocados de OpenStreetMap padrão (claro) para **CARTO Dark Matter** pelo mesmo motivo: tiles claros destoariam visivelmente do resto da página.
- **As barras dos gráficos (`Tendencias.tsx`, `Geografia.tsx`) têm `isAnimationActive={false}`** -- decisão tomada depois de um bug de validação real (ver `docs/DEVLOG.md`, "Dia 6 (extensão 3)"): capturar a página inteira com Playwright redimensiona a viewport antes do screenshot, o que faz o `ResponsiveContainer` do Recharts re-renderizar o gráfico e replay a animação de entrada das barras -- se o screenshot cai no meio da animação, a barra aparece com largura ~0 (vazia) mesmo com o DOM final correto pouco depois. Desativar a animação elimina esse artefato de validação e também uma classe de instabilidade visual real (qualquer resize da janela do usuário logo após carregar teria o mesmo efeito), sem perda funcional -- a animação era só decorativa.

## Validação

Build de produção (`npm run build`) e lint (`npx oxlint`) passam limpos. Validação de ponta a ponta feita com um browser real (Playwright/Chromium headless) contra a API real (`uvicorn`) e um Postgres real, carregando o ranking, alternando para o modo histórico, navegando até o detalhe de um município e confirmando o gráfico Recharts renderizado — sem erros de console, `pageerror` ou requisição falha. A página de Priorização foi validada da mesma forma (ranking por impacto, tendência e calendário sazonal carregados contra dado real, navegação para o detalhe de um município a partir dela).

O mapa de clusters foi validado à parte: 5.509 municípios reais renderizados como `CircleMarker` do Leaflet (confirmado contando os elementos SVG na página), popup com dados corretos ao clicar num município, link de download do KML apontando para `/mapa/kml`, e a legenda batendo com a contagem real por cluster (crítico 242 / alto 876 / moderado 1.879 / baixo 2.512). **Limitação conhecida deste ambiente de desenvolvimento** (não do código): a política de rede do sandbox usado para construir isso bloqueia `basemaps.cartocdn.com` (tiles do mapa) e `fonts.googleapis.com`/`fonts.gstatic.com` (fonte Inter), então os screenshots de validação feitos aqui mostram o mapa sem a camada de base (só os marcadores coloridos, que por si só já desenham o contorno do Brasil) e a fonte de fallback do sistema em vez de Inter — no navegador real do usuário, sem esse bloqueio de rede, tiles e fonte carregam normalmente. Ver "Dia 6" e "Dia 6 (pivot)" em [`../docs/DEVLOG.md`](../docs/DEVLOG.md) para o relato completo, incluindo o bug de CORS encontrado e corrigido pela validação do Dia 6, "Dia 6 (extensão, mapa)" para a validação do mapa, e "Dia 6 (extensão 3)" para a reorganização em páginas, o tema escuro e os dois bugs visuais pegos e corrigidos na validação (fundo do mapa e animação das barras).

Não há testes automatizados de frontend (unitários ou E2E) no repositório — dado o prazo do desafio, a validação manual descrita acima foi priorizada sobre escrever uma suíte de testes. Fica como ponto em aberto para uma próxima iteração (ex.: Vitest + Testing Library para os componentes, Playwright commitado como teste de CI para o fluxo E2E).
