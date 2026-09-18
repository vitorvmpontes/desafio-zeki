// Cliente da API do Continua -- tipos espelham exatamente api/schemas.py
// (Pydantic). Se um campo mudar lá, muda aqui também -- não há geração
// automática de tipos por ora (fora do escopo do Dia 6).

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface MunicipioResumo {
  codigo_ibge: string;
  nome: string;
  uf: string;
  regiao: string;
  consumidores_ativos_estimados: number | null;
}

export interface HistoricoPonto {
  ano: number;
  mes: number;
  fec_aprox: number | null;
  n_eventos_validos: number | null;
  consumidores_ativos_max: number | null;
}

export interface HistoricoResponse {
  codigo_ibge: string;
  nome: string;
  uf: string;
  regiao: string;
  historico: HistoricoPonto[];
}

export interface ImportanciaFeature {
  feature: string;
  importancia_relativa: number;
  aumento_mae_medio: number;
}

export interface PrevisaoResponse {
  codigo_ibge: string;
  nome: string;
  uf: string;
  regiao: string;
  mes_alvo: string;
  previsao_modelo: number;
  previsao_baseline: number | null;
  baseline_persistencia_t1: number | null;
  baseline_persistencia_t12: number | null;
  features_utilizadas: Record<string, number | string | null>;
  causas_dominantes_ultimos_12_meses: Record<string, number>;
  importancia_features_modelo: ImportanciaFeature[];
  nota_metodologica: string;
}

export interface RankingItem {
  posicao: number;
  codigo_ibge: string;
  nome: string;
  uf: string;
  regiao: string;
  risco: number;
  previsao_modelo: number | null;
  previsao_baseline: number | null;
  fec_aprox_observado: number | null;
}

export interface RankingResponse {
  modo: "previsto" | "historico";
  ano: number;
  mes: number;
  total_municipios: number;
  itens: RankingItem[];
}

export type ConfiancaRecomendacao = "alta" | "media" | "baixa" | "sem_dado";

export interface ItemPriorizacao {
  posicao: number;
  codigo_ibge: string;
  nome: string;
  uf: string;
  regiao: string;
  previsao_modelo: number;
  consumidores_ativos_estimados: number | null;
  impacto_esperado: number;
  acao_recomendada: string;
  confianca_recomendacao: ConfiancaRecomendacao;
  causa_dominante: string | null;
  percentual_causa_dominante: number | null;
}

export interface TendenciaItem {
  codigo_ibge: string;
  nome: string;
  uf: string;
  regiao: string;
  variacao_pct: number;
  fec_aprox_medio_recente: number;
  fec_aprox_medio_anterior: number;
}

export interface CalendarioSazonalPonto {
  ano: number;
  mes: number;
  n_eventos_total: number;
}

export interface CalendarioSazonal {
  pontos: CalendarioSazonalPonto[];
  meses_criticos: number[];
  recomendacao: string;
}

export interface HotspotItem {
  codigo_ibge: string;
  nome: string;
  uf: string;
  regiao: string;
  fec_aprox_medio: number;
  dec_aprox_horas_medio: number;
  n_eventos_validos: number;
  mttr_horas: number | null;
  indice_hotspot: number;
}

export interface MttrRegional {
  regiao: string;
  n_eventos_validos: number;
  duracao_total_horas: number;
  mttr_horas: number | null;
}

export interface DesempenhoGeografico {
  janela_meses: number;
  hotspots: HotspotItem[];
  mttr_por_regiao: MttrRegional[];
  nota_metodologica: string;
}

export interface PriorizacaoResponse {
  mes_alvo: string;
  total_municipios: number;
  ranking_impacto: ItemPriorizacao[];
  tendencia_piorando: TendenciaItem[];
  tendencia_melhorando: TendenciaItem[];
  calendario_sazonal: CalendarioSazonal;
  desempenho_geografico: DesempenhoGeografico;
  nota_metodologica: string;
}

export interface MapaMunicipio {
  codigo_ibge: string;
  nome: string;
  uf: string;
  regiao: string;
  latitude: number;
  longitude: number;
  fec_aprox_medio: number;
  dec_aprox_horas_medio: number;
  severidade: "critico" | "alto" | "moderado" | "baixo";
}

export interface MapaClusterResumo {
  severidade: string;
  n_municipios: number;
  fec_aprox_medio: number;
  dec_aprox_horas_medio: number;
}

export interface MapaResponse {
  janela_meses: number;
  n_clusters: number;
  n_municipios_no_mapa: number;
  municipios: MapaMunicipio[];
  resumo_por_cluster: MapaClusterResumo[];
  kml_url: string;
  nota_metodologica: string;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function pedir<T>(caminho: string): Promise<T> {
  const resposta = await fetch(`${API_URL}${caminho}`);
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => ({}));
    throw new ApiError(resposta.status, corpo.detail ?? `Erro ${resposta.status} ao chamar ${caminho}`);
  }
  return resposta.json() as Promise<T>;
}

export function listarMunicipios(busca?: string, limite = 300): Promise<MunicipioResumo[]> {
  const params = new URLSearchParams({ limite: String(limite) });
  if (busca) params.set("busca", busca);
  return pedir(`/municipios?${params.toString()}`);
}

export function buscarHistorico(codigoIbge: string): Promise<HistoricoResponse> {
  return pedir(`/municipios/${codigoIbge}/historico`);
}

export function buscarPrevisao(codigoIbge: string): Promise<PrevisaoResponse> {
  return pedir(`/municipios/${codigoIbge}/previsao`);
}

export function buscarRankingPrevisto(limite = 50): Promise<RankingResponse> {
  return pedir(`/ranking?limite=${limite}`);
}

export function buscarRankingHistorico(ano: number, mes: number, limite = 50): Promise<RankingResponse> {
  return pedir(`/ranking?ano=${ano}&mes=${mes}&limite=${limite}`);
}

export function buscarPriorizacao(limite = 20): Promise<PriorizacaoResponse> {
  return pedir(`/priorizacao?limite=${limite}`);
}

export function buscarMapa(): Promise<MapaResponse> {
  return pedir(`/mapa`);
}

export function urlKmlMapa(): string {
  return `${API_URL}/mapa/kml`;
}

export { ApiError };
