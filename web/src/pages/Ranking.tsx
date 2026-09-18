import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, buscarRankingHistorico, buscarRankingPrevisto, type RankingResponse } from "../lib/api";
import { BadgeRisco } from "../components/BadgeRisco";
import { formatarFec } from "../lib/risco";

type Modo = "previsto" | "historico";

export function Ranking() {
  const [modo, setModo] = useState<Modo>("previsto");
  const [ano, setAno] = useState(2025);
  const [mes, setMes] = useState(12);
  const [limite, setLimite] = useState(50);
  const [busca, setBusca] = useState("");

  const [dados, setDados] = useState<RankingResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setCarregando(true);
    setErro(null);
    const promessa = modo === "previsto" ? buscarRankingPrevisto(limite) : buscarRankingHistorico(ano, mes, limite);
    promessa
      .then(setDados)
      .catch((e) => setErro(e instanceof ApiError ? e.message : "Não foi possível carregar o ranking."))
      .finally(() => setCarregando(false));
  }, [modo, ano, mes, limite]);

  const itensFiltrados = useMemo(() => {
    if (!dados) return [];
    if (!busca.trim()) return dados.itens;
    const alvo = busca.trim().toLowerCase();
    return dados.itens.filter((item) => item.nome.toLowerCase().includes(alvo));
  }, [dados, busca]);

  return (
    <div className="conteudo">
      <div className="cartao">
        <div className="barra-controles">
          <button className={modo === "previsto" ? "ativo" : ""} onClick={() => setModo("previsto")}>
            Previsto (próximo mês)
          </button>
          <button className={modo === "historico" ? "ativo" : ""} onClick={() => setModo("historico")}>
            Histórico observado
          </button>

          {modo === "historico" && (
            <>
              <label>
                Ano{" "}
                <input
                  type="number"
                  value={ano}
                  min={2024}
                  max={2025}
                  onChange={(e) => setAno(Number(e.target.value))}
                  style={{ width: 80 }}
                />
              </label>
              <label>
                Mês{" "}
                <select value={mes} onChange={(e) => setMes(Number(e.target.value))}>
                  {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                    <option key={m} value={m}>
                      {String(m).padStart(2, "0")}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}

          <input
            type="text"
            placeholder="Buscar município..."
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            style={{ marginLeft: "auto", minWidth: 220 }}
          />
          <select value={limite} onChange={(e) => setLimite(Number(e.target.value))}>
            <option value={25}>Top 25</option>
            <option value={50}>Top 50</option>
            <option value={100}>Top 100</option>
            <option value={500}>Top 500</option>
          </select>
        </div>

        {dados && (
          <p className="metrica-rotulo" style={{ margin: "0 0 12px" }}>
            {dados.modo === "previsto"
              ? `Previsão do modelo para ${String(dados.mes).padStart(2, "0")}/${dados.ano} · ${dados.total_municipios.toLocaleString("pt-BR")} municípios cobertos`
              : `Risco observado em ${String(dados.mes).padStart(2, "0")}/${dados.ano} · ${dados.total_municipios.toLocaleString("pt-BR")} municípios`}
          </p>
        )}

        {carregando && <div className="estado-carregando">Carregando ranking...</div>}
        {erro && <div className="estado-erro">{erro}</div>}

        {!carregando && !erro && dados && (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Risco</th>
                <th>Município</th>
                <th>UF</th>
                <th>Região</th>
                <th>{modo === "previsto" ? "Previsão (modelo)" : "fec_aprox observado"}</th>
                {modo === "previsto" && <th>Baseline (referência)</th>}
              </tr>
            </thead>
            <tbody>
              {itensFiltrados.map((item) => (
                <tr key={item.codigo_ibge}>
                  <td>{item.posicao}</td>
                  <td>
                    <BadgeRisco posicao={item.posicao} total={dados.total_municipios} />
                  </td>
                  <td>
                    <Link to={`/municipios/${item.codigo_ibge}`}>{item.nome}</Link>
                  </td>
                  <td>{item.uf}</td>
                  <td>{item.regiao}</td>
                  <td>{formatarFec(modo === "previsto" ? item.previsao_modelo : item.fec_aprox_observado)}</td>
                  {modo === "previsto" && <td>{formatarFec(item.previsao_baseline)}</td>}
                </tr>
              ))}
              {itensFiltrados.length === 0 && (
                <tr>
                  <td colSpan={7} className="estado-vazio">
                    Nenhum município encontrado para "{busca}".
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
