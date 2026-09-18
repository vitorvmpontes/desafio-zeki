import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ApiError, buscarHistorico, buscarPrevisao, type HistoricoResponse, type PrevisaoResponse } from "../lib/api";
import { formatarFec } from "../lib/risco";

interface PontoGrafico {
  rotulo: string;
  real?: number;
  previsto?: number;
  baseline?: number;
}

const NOMES_CAUSA: Record<string, string> = {
  generica_sem_detalhe: "Genérica (sem detalhe)",
  ambiental: "Ambiental",
  outras_causas_detalhadas: "Outras causas detalhadas",
};

const NOMES_FEATURE: Record<string, string> = {
  lag_1: "fec_aprox do mês mais recente",
  lag_2: "fec_aprox de 2 meses atrás",
  lag_3: "fec_aprox de 3 meses atrás",
  media_movel_3: "média móvel (3 meses)",
  media_movel_expandida: "média histórica do município",
  mes_sin: "sazonalidade (seno do mês)",
  mes_cos: "sazonalidade (cosseno do mês)",
  log_consumidores: "log(consumidores ativos)",
  log_n_eventos_lag_1: "log(nº eventos válidos, mês mais recente)",
  prop_causa_generica_lag_1: "proporção causa genérica",
  prop_causa_ambiental_lag_1: "proporção causa ambiental",
  n_distribuidoras_lag_1: "nº de distribuidoras",
  regiao: "região",
  uf_sigla: "UF",
};

// O grafico usa a mesma escala x100 ("por 100 consumidores") do restante do
// site (ver web/src/lib/risco.ts, formatarFec) -- aplicada aqui direto nos
// pontos (nao so na formatacao) para o eixo Y tambem ficar no valor
// intuitivo, nao so o tooltip.
function montarPontosGrafico(historico: HistoricoResponse, previsao: PrevisaoResponse): PontoGrafico[] {
  const pontos: PontoGrafico[] = historico.historico.map((p) => ({
    rotulo: `${p.ano}-${String(p.mes).padStart(2, "0")}`,
    real: p.fec_aprox !== null && p.fec_aprox !== undefined ? p.fec_aprox * 100 : undefined,
  }));

  if (pontos.length > 0) {
    // conecta a linha "prevista" a partir do último ponto real, para o
    // tracejado de previsão continuar visualmente a partir de onde o
    // historico real termina.
    pontos[pontos.length - 1].previsto = pontos[pontos.length - 1].real;
    pontos[pontos.length - 1].baseline = pontos[pontos.length - 1].real;
  }

  pontos.push({
    rotulo: previsao.mes_alvo,
    previsto: previsao.previsao_modelo * 100,
    baseline: previsao.previsao_baseline !== null && previsao.previsao_baseline !== undefined
      ? previsao.previsao_baseline * 100
      : undefined,
  });

  return pontos;
}

function formatarValorGrafico(valor: number): string {
  return valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function MunicipioDetalhe() {
  const { codigoIbge } = useParams<{ codigoIbge: string }>();
  const [historico, setHistorico] = useState<HistoricoResponse | null>(null);
  const [previsao, setPrevisao] = useState<PrevisaoResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!codigoIbge) return;
    setCarregando(true);
    setErro(null);
    Promise.all([buscarHistorico(codigoIbge), buscarPrevisao(codigoIbge)])
      .then(([h, p]) => {
        setHistorico(h);
        setPrevisao(p);
      })
      .catch((e) => setErro(e instanceof ApiError ? e.message : "Não foi possível carregar este município."))
      .finally(() => setCarregando(false));
  }, [codigoIbge]);

  if (carregando) return <div className="conteudo estado-carregando">Carregando...</div>;
  if (erro) return <div className="conteudo estado-erro">{erro}</div>;
  if (!historico || !previsao) return null;

  const pontosGrafico = montarPontosGrafico(historico, previsao);

  return (
    <div className="conteudo">
      <p>
        <Link to="/">&larr; Voltar para o ranking</Link>
      </p>

      <div className="cartao">
        <h2 style={{ margin: "0 0 4px" }}>{historico.nome}</h2>
        <p className="metrica-rotulo" style={{ margin: 0 }}>
          {historico.uf} · {historico.regiao} · código IBGE {historico.codigo_ibge}
        </p>
      </div>

      <div className="cartao">
        <h3 style={{ marginTop: 0 }}>Histórico real vs. previsão ({previsao.mes_alvo})</h3>
        <p style={{ color: "var(--cor-texto-suave)", fontSize: 14, marginTop: 0, marginBottom: 16 }}>
          Valores em interrupções por 100 consumidores atendidos.
        </p>
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={pontosGrafico} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--cor-grade-grafico)" />
            <XAxis dataKey="rotulo" tick={{ fontSize: 11, fill: "var(--cor-texto-suave)" }} interval={2} />
            <YAxis tick={{ fontSize: 11, fill: "var(--cor-texto-suave)" }} width={60} />
            <Tooltip
              contentStyle={{ background: "var(--cor-superficie-alta)", border: "1px solid var(--cor-borda)", borderRadius: 8 }}
              labelStyle={{ color: "var(--cor-texto)" }}
              itemStyle={{ color: "var(--cor-texto)" }}
              formatter={(valor) => (typeof valor === "number" ? formatarValorGrafico(valor) : valor)}
            />
            <Legend wrapperStyle={{ color: "var(--cor-texto-suave)", fontSize: 13 }} />
            <Line type="monotone" dataKey="real" name="Real (por 100 consumidores)" stroke="var(--cor-primaria)" strokeWidth={2} dot={false} />
            <Line
              type="monotone"
              dataKey="previsto"
              name="Previsão (por 100 consumidores)"
              stroke="var(--cor-risco-alto)"
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={{ r: 3 }}
            />
            <Line
              type="monotone"
              dataKey="baseline"
              name="Baseline (por 100 consumidores)"
              stroke="var(--cor-texto-suave)"
              strokeWidth={1.5}
              strokeDasharray="2 3"
              dot={{ r: 3 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="cartao">
        <h3 style={{ marginTop: 0 }}>Previsão para {previsao.mes_alvo}</h3>
        <div className="grade-cartoes">
          <div>
            <div className="metrica-rotulo">Modelo (gradient boosting)</div>
            <div className="metrica-valor destaque">{formatarFec(previsao.previsao_modelo)}</div>
          </div>
          <div>
            <div className="metrica-rotulo">Baseline (persistência t-1 + t-12)</div>
            <div className="metrica-valor">{formatarFec(previsao.previsao_baseline)}</div>
          </div>
          <div>
            <div className="metrica-rotulo">Persistência mês anterior (t-1)</div>
            <div className="metrica-valor">{formatarFec(previsao.baseline_persistencia_t1)}</div>
          </div>
          <div>
            <div className="metrica-rotulo">Persistência sazonal (t-12)</div>
            <div className="metrica-valor">{formatarFec(previsao.baseline_persistencia_t12)}</div>
          </div>
        </div>
        <p className="nota-metodologica" style={{ marginTop: 16 }}>{previsao.nota_metodologica}</p>
      </div>

      <div className="grade-cartoes">
        <div className="cartao">
          <h3 style={{ marginTop: 0 }}>Causas dominantes (últimos 12 meses)</h3>
          {Object.keys(previsao.causas_dominantes_ultimos_12_meses).length === 0 ? (
            <p className="metrica-rotulo">Sem eventos suficientes para calcular.</p>
          ) : (
            <table className="tabela-features">
              <tbody>
                {Object.entries(previsao.causas_dominantes_ultimos_12_meses).map(([causa, proporcao]) => (
                  <tr key={causa}>
                    <td>{NOMES_CAUSA[causa] ?? causa}</td>
                    <td>{(proporcao * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="cartao">
          <h3 style={{ marginTop: 0 }}>Valores usados na previsão</h3>
          <table className="tabela-features">
            <tbody>
              {Object.entries(previsao.features_utilizadas).map(([feature, valor]) => (
                <tr key={feature}>
                  <td>{NOMES_FEATURE[feature] ?? feature}</td>
                  <td>{typeof valor === "number" ? valor.toFixed(4) : valor ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="cartao">
        <h3 style={{ marginTop: 0 }}>O que mais pesa nas previsões do modelo</h3>
        <p className="metrica-rotulo" style={{ marginTop: -8 }}>
          Importância GLOBAL (não específica deste município) — ver nota acima.
        </p>
        <table className="tabela-features">
          <tbody>
            {previsao.importancia_features_modelo
              .filter((f) => f.importancia_relativa > 0)
              .map((f) => (
                <tr key={f.feature}>
                  <td style={{ width: 220 }}>{NOMES_FEATURE[f.feature] ?? f.feature}</td>
                  <td>
                    <div className="barra-importancia">
                      <div style={{ width: `${f.importancia_relativa * 100}%` }} />
                    </div>
                  </td>
                  <td style={{ width: 60, textAlign: "right" }}>{(f.importancia_relativa * 100).toFixed(1)}%</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
