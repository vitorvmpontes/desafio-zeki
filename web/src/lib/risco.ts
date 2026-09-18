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
  // fec_aprox bruto é uma taxa por consumidor (ex.: 0,0731) -- correto, mas
  // pouco intuitivo à primeira vista para quem não conhece a métrica.
  // Exibido multiplicado por 100 ("7,31 por 100 consumidores"): mesma
  // precisão, escala que dá pra comparar de cabeça (ver docs/DEVLOG.md,
  // pedido do usuário para deixar o número do ranking mais intuitivo). O
  // valor por trás continua o fec_aprox de sempre -- só a apresentação
  // mudou, a API e a nota_metodologica de cada tela seguem descrevendo a
  // métrica original.
  return (valor * 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
