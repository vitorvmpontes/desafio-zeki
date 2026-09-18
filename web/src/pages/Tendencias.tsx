import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ApiError, buscarPriorizacao, type PriorizacaoResponse, type TendenciaItem } from "../lib/api";

const NOMES_MES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];

function formatarNumero(valor: number, casas = 0): string {
  return valor.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

function montarSazonalidadeMedia(pontos: PriorizacaoResponse["calendario_sazonal"]["pontos"]) {
  const somaPorMes = new Map<number, { soma: number; n: number }>();
  for (const p of pontos) {
    const atual = somaPorMes.get(p.mes) ?? { soma: 0, n: 0 };
    atual.soma += p.n_eventos_total;
    atual.n += 1;
    somaPorMes.set(p.mes, atual);
  }
  return Array.from({ length: 12 }, (_, i) => i + 1)
    .filter((mes) => somaPorMes.has(mes))
    .map((mes) => ({ mes, rotulo: NOMES_MES[mes - 1], media: somaPorMes.get(mes)!.soma / somaPorMes.get(mes)!.n }));
}

function TabelaTendencia({ itens, titulo, corSinal }: { itens: TendenciaItem[]; titulo: string; corSinal: "positiva" | "negativa" }) {
  return (
    <div className="cartao">
      <h3 style={{ marginTop: 0 }}>{titulo}</h3>
      {itens.length === 0 ? (
        <p className="estado-vazio" style={{ padding: 12 }}>
          Nenhum município com histórico suficiente (6 meses consecutivos) nesta categoria.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Município</th>
              <th>UF</th>
              <th>Variação</th>
            </tr>
          </thead>
          <tbody>
            {itens.map((item) => (
              <tr key={item.codigo_ibge}>
                <td>
                  <Link to={`/municipios/${item.codigo_ibge}`}>{item.nome}</Link>
                </td>
                <td>{item.uf}</td>
                <td className={corSinal === "positiva" ? "variacao-positiva" : "variacao-negativa"}>
                  {item.variacao_pct > 0 ? "+" : ""}
                  {formatarNumero(item.variacao_pct, 1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function Tendencias() {
  const [dados, setDados] = useState<PriorizacaoResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    buscarPriorizacao()
      .then(setDados)
      .catch((e) => setErro(e instanceof ApiError ? e.message : "Não foi possível carregar as tendências."))
      .finally(() => setCarregando(false));
  }, []);

  if (carregando) return <div className="conteudo estado-carregando">Carregando...</div>;
  if (erro) return <div className="conteudo estado-erro">{erro}</div>;
  if (!dados) return null;

  const sazonalidadeMedia = montarSazonalidadeMedia(dados.calendario_sazonal.pontos);

  return (
    <div className="conteudo">
      <div className="cartao cartao-intro">
        <h2 style={{ marginTop: 0 }}>Tendências e sazonalidade</h2>
        <p style={{ color: "var(--cor-texto-suave)", marginBottom: 0 }}>
          Como o risco está evoluindo -- quais municípios estão piorando ou melhorando nos últimos meses, e
          quando historicamente o problema mais se agrava no calendário. Para a lista de ação imediata, veja{" "}
          <Link to="/priorizacao">Priorização</Link>.
        </p>
      </div>

      <div className="grade-cartoes">
        <TabelaTendencia itens={dados.tendencia_piorando} titulo="Piorando (últimos 3 vs. 3 meses anteriores)" corSinal="positiva" />
        <TabelaTendencia itens={dados.tendencia_melhorando} titulo="Melhorando (últimos 3 vs. 3 meses anteriores)" corSinal="negativa" />
      </div>

      <div className="cartao">
        <h3 style={{ marginTop: 0 }}>Calendário sazonal de preparação</h3>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={sazonalidadeMedia} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--cor-grade-grafico)" />
            <XAxis dataKey="rotulo" tick={{ fontSize: 11, fill: "var(--cor-texto-suave)" }} />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--cor-texto-suave)" }}
              width={60}
              tickFormatter={(v) => `${(v / 1000).toFixed(0)} mil`}
            />
            <Tooltip
              contentStyle={{ background: "var(--cor-superficie-alta)", border: "1px solid var(--cor-borda)", borderRadius: 8 }}
              labelStyle={{ color: "var(--cor-texto)" }}
              itemStyle={{ color: "var(--cor-texto)" }}
              formatter={(valor) => (typeof valor === "number" ? formatarNumero(valor) : valor)}
            />
            <Bar dataKey="media" name="Média de eventos (2024-2025)" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {sazonalidadeMedia.map((ponto) => (
                <Cell
                  key={ponto.mes}
                  fill={dados.calendario_sazonal.meses_criticos.includes(ponto.mes) ? "var(--cor-risco-medio-alto)" : "var(--cor-primaria)"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="nota-metodologica" style={{ marginTop: 12 }}>
          {dados.calendario_sazonal.recomendacao}
        </p>
      </div>
    </div>
  );
}
