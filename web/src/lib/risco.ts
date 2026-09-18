// Classificação visual de risco por posição relativa no ranking (não por
// um valor absoluto de fec_aprox, que não tem um limiar "alto/baixo"
// universal — ver ml/notebooks/01-eda.ipynb). Top 10% = alto risco (mesmo
// corte usado na métrica "precisão no top 10%" do Dia 3/4), próximos 25% =
// médio-alto, próximos 35% = médio, resto = baixo.
export type NivelRisco = "alto" | "medio-alto" | "medio" | "baixo";

export function classificarRisco(posicao: number, total: number): NivelRisco {
  const percentil = posicao / total;
  if (percentil <= 0.10) return "alto";
  if (percentil <= 0.35) return "medio-alto";
  if (percentil <= 0.70) return "medio";
  return "baixo";
}

export const ROTULO_RISCO: Record<NivelRisco, string> = {
  alto: "Alto",
  "medio-alto": "Médio-alto",
  medio: "Médio",
  baixo: "Baixo",
};

export function formatarFec(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return valor.toFixed(4);
}
