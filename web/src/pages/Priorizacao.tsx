import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, buscarPriorizacao, type ConfiancaRecomendacao, type PadraoOperacional, type PriorizacaoResponse } from "../lib/api";
import { formatarFec } from "../lib/risco";

const ROTULO_CONFIANCA: Record<ConfiancaRecomendacao, string> = {
  alta: "Alta confiança",
  media: "Média confiança",
  baixa: "Baixa confiança",
  sem_dado: "Sem dado",
};

// Rótulo curto + classe de severidade (reaproveita as mesmas 4 cores de
// risco já usadas em BadgeRisco -- ver web/src/index.css, .badge-*) para o
// padrão frequência x duração que agora sustenta a ação recomendada (ver
// docs/DEVLOG.md, "ação recomendada baseada em causa não ajudava").
const ROTULO_PADRAO: Record<PadraoOperacional, string> = {
  critico_ambos: "Crítico (frequência + duração)",
  frequencia_dominante: "Muitos eventos curtos",
  duracao_dominante: "Poucos eventos longos",
  atencao_moderada: "Atenção moderada",
  dentro_do_padrao: "Dentro do padrão",
  sem_dado: "Sem dado",
};

const CLASSE_PADRAO: Record<PadraoOperacional, string> = {
  critico_ambos: "badge-alto",
  frequencia_dominante: "badge-medio-alto",
  duracao_dominante: "badge-medio-alto",
  atencao_moderada: "badge-medio",
  dentro_do_padrao: "badge-baixo",
  sem_dado: "badge-confianca-sem_dado",
};

function formatarNumero(valor: number, casas = 0): string {
  return valor.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

function formatarInteiro(valor: number | null): string {
  if (valor === null) return "—";
  return Math.round(valor).toLocaleString("pt-BR");
}

export function Priorizacao() {
  const [limite, setLimite] = useState(20);
  const [dados, setDados] = useState<PriorizacaoResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setCarregando(true);
    setErro(null);
    buscarPriorizacao(limite)
      .then(setDados)
      .catch((e) => setErro(e instanceof ApiError ? e.message : "Não foi possível carregar a priorização."))
      .finally(() => setCarregando(false));
  }, [limite]);

  if (carregando && !dados) return <div className="conteudo estado-carregando">Carregando...</div>;
  if (erro) return <div className="conteudo estado-erro">{erro}</div>;
  if (!dados) return null;

  return (
    <div className="conteudo">
      <div className="cartao cartao-intro">
        <h2 style={{ marginTop: 0 }}>Priorização para {dados.mes_alvo}</h2>
        <p style={{ color: "var(--cor-texto-suave)", marginBottom: 0 }}>
          Onde agir primeiro e com qual ação -- não só "qual município tem a maior taxa de risco" (ver{" "}
          <Link to="/">o ranking por taxa</Link>). Para a evolução no tempo, veja <Link to="/tendencias">Tendências</Link>;
          para a leitura espacial, <Link to="/geografia">Geografia</Link>. {formatarInteiro(dados.total_municipios)}{" "}
          municípios cobertos.
        </p>
      </div>

      <div className="cartao">
        <div className="barra-controles">
          <h3 style={{ margin: 0 }}>Priorização por impacto real</h3>
          <select value={limite} onChange={(e) => setLimite(Number(e.target.value))} style={{ marginLeft: "auto" }}>
            <option value={10}>Top 10</option>
            <option value={20}>Top 20</option>
            <option value={50}>Top 50</option>
            <option value={100}>Top 100</option>
          </select>
        </div>
        <p style={{ color: "var(--cor-texto-suave)", fontSize: 14, marginTop: 0, marginBottom: 16 }}>
          Ordenado por <strong>impacto esperado</strong> (previsão × consumidores atendidos), não só pela taxa de
          risco -- ver <Link to="/">o ranking por taxa</Link> para a outra métrica. Previsão em interrupções por 100
          consumidores.
        </p>
        {carregando && <div className="estado-carregando">Atualizando...</div>}
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Município</th>
              <th>UF</th>
              <th>Previsão (por 100 consumidores)</th>
              <th>Consumidores</th>
              <th>Impacto esperado</th>
              <th>Ação recomendada</th>
            </tr>
          </thead>
          <tbody>
            {dados.ranking_impacto.map((item) => (
              <tr key={item.codigo_ibge}>
                <td>{item.posicao}</td>
                <td>
                  <Link to={`/municipios/${item.codigo_ibge}`}>{item.nome}</Link>
                </td>
                <td>{item.uf}</td>
                <td>{formatarFec(item.previsao_modelo)}</td>
                <td>{formatarInteiro(item.consumidores_ativos_estimados)}</td>
                <td>{formatarNumero(item.impacto_esperado, 1)}</td>
                <td style={{ minWidth: 300, fontSize: 13 }}>
                  <div style={{ marginBottom: 6, display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <span className={`badge ${CLASSE_PADRAO[item.padrao_operacional]}`}>
                      {ROTULO_PADRAO[item.padrao_operacional]}
                    </span>
                    <span className={`badge badge-confianca-${item.confianca_recomendacao}`}>
                      {ROTULO_CONFIANCA[item.confianca_recomendacao]}
                    </span>
                  </div>
                  <div style={{ color: "var(--cor-texto-suave)" }}>{item.acao_recomendada}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="nota-metodologica">{dados.nota_metodologica}</p>
    </div>
  );
}
