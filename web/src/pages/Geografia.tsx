import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { MapaClusters } from "../components/MapaClusters";
import { ApiError, buscarMapa, buscarPriorizacao, type MapaResponse, type PriorizacaoResponse } from "../lib/api";
import { formatarFec } from "../lib/risco";

function formatarNumero(valor: number, casas = 0): string {
  return valor.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

export function Geografia() {
  const [dados, setDados] = useState<PriorizacaoResponse | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  const [mapa, setMapa] = useState<MapaResponse | null>(null);
  const [erroMapa, setErroMapa] = useState<string | null>(null);

  useEffect(() => {
    buscarPriorizacao()
      .then(setDados)
      .catch((e) => setErro(e instanceof ApiError ? e.message : "Não foi possível carregar o desempenho geográfico."))
      .finally(() => setCarregando(false));
  }, []);

  useEffect(() => {
    buscarMapa()
      .then(setMapa)
      .catch((e) => setErroMapa(e instanceof ApiError ? e.message : "Não foi possível carregar o mapa."));
  }, []);

  if (carregando) return <div className="conteudo estado-carregando">Carregando...</div>;
  if (erro) return <div className="conteudo estado-erro">{erro}</div>;
  if (!dados) return null;

  const geo = dados.desempenho_geografico;

  return (
    <div className="conteudo">
      <div className="cartao cartao-intro">
        <h2 style={{ marginTop: 0 }}>Desempenho geográfico e qualidade regional</h2>
        <p style={{ color: "var(--cor-texto-suave)", marginBottom: 0 }}>
          Onde o problema mais acontece de verdade -- retrospectivo, olhando os últimos {geo.janela_meses} meses,
          ao contrário da <Link to="/priorizacao">Priorização</Link> (que olha para a previsão do mês seguinte).
        </p>
      </div>

      <div className="cartao">
        <h3 style={{ marginTop: 0 }}>Mapa de clusters de qualidade de serviço</h3>
        <p style={{ color: "var(--cor-texto-suave)", fontSize: 14, marginTop: 0, marginBottom: 16 }}>
          A mesma clusterização do mapeamento de hotspots abaixo, colocada no espaço -- o KML por trás do mapa
          também está disponível para download.
        </p>
        {erroMapa && <p className="estado-erro">{erroMapa}</p>}
        {!erroMapa && !mapa && <div className="estado-carregando">Carregando mapa...</div>}
        {mapa && <MapaClusters dados={mapa} />}
      </div>

      <div className="cartao">
        <h3 style={{ marginTop: 0 }}>Mapeamento de hotspots</h3>
        <p style={{ color: "var(--cor-texto-suave)", fontSize: 14, marginTop: 0, marginBottom: 16 }}>
          Pior frequência <strong>e</strong> duração <strong>por consumidor</strong> -- não volume bruto, que já
          aparece no <Link to="/priorizacao">ranking por impacto</Link>.
        </p>
        <table>
          <thead>
            <tr>
              <th>Município</th>
              <th>UF</th>
              <th>Frequência média (por 100 consumidores)</th>
              <th>Duração média (dec_aprox_horas)</th>
              <th>MTTR (h/evento)</th>
              <th>Índice hotspot</th>
            </tr>
          </thead>
          <tbody>
            {geo.hotspots.map((item) => (
              <tr key={item.codigo_ibge}>
                <td>
                  <Link to={`/municipios/${item.codigo_ibge}`}>{item.nome}</Link>
                </td>
                <td>{item.uf}</td>
                <td>{formatarFec(item.fec_aprox_medio)}</td>
                <td>{formatarNumero(item.dec_aprox_horas_medio, 2)}h</td>
                <td>{item.mttr_horas !== null ? `${formatarNumero(item.mttr_horas, 1)}h` : "—"}</td>
                <td>
                  <div className="barra-importancia" style={{ width: 100 }}>
                    <div style={{ width: `${item.indice_hotspot}%`, background: "var(--cor-risco-alto)" }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="cartao">
        <h3 style={{ marginTop: 0 }}>Tempo médio de reparo (MTTR) por região</h3>
        <p style={{ color: "var(--cor-texto-suave)", fontSize: 14, marginTop: 0, marginBottom: 16 }}>
          Horas por evento até o restabelecimento -- comparado por região/UF, na ausência de uma classificação
          urbano/rural oficial.
        </p>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={geo.mttr_por_regiao} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--cor-grade-grafico)" />
            <XAxis type="number" tick={{ fontSize: 11, fill: "var(--cor-texto-suave)" }} unit="h" />
            <YAxis type="category" dataKey="regiao" tick={{ fontSize: 12, fill: "var(--cor-texto-suave)" }} width={90} />
            <Tooltip
              contentStyle={{ background: "var(--cor-superficie-alta)", border: "1px solid var(--cor-borda)", borderRadius: 8 }}
              labelStyle={{ color: "var(--cor-texto)" }}
              itemStyle={{ color: "var(--cor-texto)" }}
              formatter={(valor) => (typeof valor === "number" ? `${valor.toFixed(1)}h` : valor)}
            />
            <Bar
              dataKey="mttr_horas"
              name="MTTR (horas/evento)"
              fill="var(--cor-primaria)"
              radius={[0, 4, 4, 0]}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Nota única para a página inteira (hotspots + MTTR) -- em vez de uma
          nota por gráfico, ver docs/DEVLOG.md, "reorganização em páginas +
          tema escuro" (pedido do usuário para reduzir o tanto de texto). */}
      <p className="nota-metodologica">{geo.nota_metodologica}</p>
    </div>
  );
}
