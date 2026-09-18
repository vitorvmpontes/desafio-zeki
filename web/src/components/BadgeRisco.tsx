import { ROTULO_RISCO, classificarRisco } from "../lib/risco";

export function BadgeRisco({ posicao, total }: { posicao: number; total: number }) {
  const nivel = classificarRisco(posicao, total);
  return <span className={`badge badge-${nivel}`}>{ROTULO_RISCO[nivel]}</span>;
}
