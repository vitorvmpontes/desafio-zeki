import { useRef, useState } from "react";
import { ApiError, perguntarChat, type ChatResponse, type ValorCelulaChat } from "../lib/api";

const PERGUNTAS_EXEMPLO = [
  "Quais os 10 municípios com maior fec_aprox em 2025?",
  "Qual a duração média de interrupção (dec_aprox_horas) por região em 2025?",
  "Quantos municípios do Nordeste tiveram mais de 5000 eventos válidos em algum mês de 2025?",
];

interface Mensagem {
  id: number;
  pergunta: string;
  estado: "carregando" | "sucesso" | "erro";
  resposta?: ChatResponse;
  erro?: string;
}

function formatarCelula(valor: ValorCelulaChat): string {
  if (valor === null || valor === undefined) return "—";
  if (typeof valor === "number") return valor.toLocaleString("pt-BR", { maximumFractionDigits: 4 });
  if (typeof valor === "boolean") return valor ? "sim" : "não";
  return valor;
}

export function Chat() {
  const [pergunta, setPergunta] = useState("");
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [enviando, setEnviando] = useState(false);
  const proximoId = useRef(0);

  async function enviar(perguntaBruta: string) {
    const texto = perguntaBruta.trim();
    if (!texto || enviando) return;

    const id = proximoId.current++;
    setMensagens((atual) => [...atual, { id, pergunta: texto, estado: "carregando" }]);
    setPergunta("");
    setEnviando(true);
    try {
      const resposta = await perguntarChat(texto);
      setMensagens((atual) => atual.map((m) => (m.id === id ? { ...m, estado: "sucesso", resposta } : m)));
    } catch (e) {
      const mensagemErro =
        e instanceof ApiError ? e.message : "Não foi possível obter uma resposta -- tente novamente.";
      setMensagens((atual) => atual.map((m) => (m.id === id ? { ...m, estado: "erro", erro: mensagemErro } : m)));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="conteudo">
      <div className="cartao cartao-intro">
        <h2 style={{ marginTop: 0 }}>Chat -- pergunte aos dados</h2>
        <p style={{ color: "var(--cor-texto-suave)", marginBottom: 0 }}>
          Cada pergunta em português é traduzida numa consulta SQL de verdade (não um conjunto fixo de
          respostas prontas) pelo Google Gemini, validada em várias camadas e executada contra um usuário
          Postgres <strong>somente leitura</strong>, restrito à tabela de município x mês -- nunca é possível
          alterar dado nenhum por aqui. Ver <code>api/chat_sql.py</code> para os detalhes da validação.
        </p>
      </div>

      <div className="cartao chat-janela">
        {mensagens.length === 0 && (
          <div className="estado-vazio" style={{ padding: "12px 4px" }}>
            <p style={{ marginTop: 0 }}>Experimente uma pergunta sobre os dados de 2024-2025:</p>
            <div className="chat-exemplos">
              {PERGUNTAS_EXEMPLO.map((exemplo) => (
                <button key={exemplo} onClick={() => enviar(exemplo)} disabled={enviando}>
                  {exemplo}
                </button>
              ))}
            </div>
          </div>
        )}

        {mensagens.length > 0 && (
          <div className="chat-historico">
            {mensagens.map((m) => (
              <div key={m.id} className="chat-troca">
                <div className="chat-bolha chat-bolha-usuario">{m.pergunta}</div>

                <div className="chat-bolha chat-bolha-resposta">
                  {m.estado === "carregando" && (
                    <span style={{ color: "var(--cor-texto-suave)" }}>Consultando os dados...</span>
                  )}

                  {m.estado === "erro" && <span style={{ color: "var(--cor-risco-alto)" }}>{m.erro}</span>}

                  {m.estado === "sucesso" && m.resposta && (
                    <>
                      {m.resposta.linhas.length === 0 ? (
                        <p style={{ margin: 0, color: "var(--cor-texto-suave)" }}>
                          A consulta não retornou nenhuma linha.
                        </p>
                      ) : (
                        <div className="chat-tabela-scroll">
                          <table>
                            <thead>
                              <tr>
                                {m.resposta.colunas.map((coluna) => (
                                  <th key={coluna}>{coluna}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {m.resposta.linhas.map((linha, i) => (
                                <tr key={i}>
                                  {m.resposta!.colunas.map((coluna) => (
                                    <td key={coluna}>{formatarCelula(linha[coluna])}</td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {m.resposta.aviso && (
                        <p className="nota-metodologica" style={{ marginTop: 12, marginBottom: 0 }}>
                          {m.resposta.aviso}
                        </p>
                      )}

                      <details className="chat-sql-gerado">
                        <summary>Ver SQL gerado</summary>
                        <pre>
                          <code>{m.resposta.sql_gerado}</code>
                        </pre>
                      </details>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <form
        className="chat-form"
        onSubmit={(e) => {
          e.preventDefault();
          enviar(pergunta);
        }}
      >
        <textarea
          value={pergunta}
          onChange={(e) => setPergunta(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              enviar(pergunta);
            }
          }}
          placeholder="Pergunte algo sobre os municípios... (Enter para enviar, Shift+Enter pra quebrar linha)"
          rows={2}
          disabled={enviando}
        />
        <button type="submit" className="ativo" disabled={enviando || !pergunta.trim()}>
          {enviando ? "Enviando..." : "Perguntar"}
        </button>
      </form>

      <p className="nota-metodologica">
        Defesa em profundidade: instrução de sistema restringindo o modelo a um único SELECT na tabela
        `municipio_mes` com LIMIT; validação estática da consulta devolvida (uma só instrução, só SELECT,
        nenhuma palavra-chave de escrita, nenhuma outra tabela, mesmo em subqueries aninhadas); execução num
        usuário Postgres dedicado e somente leitura (`continua_readonly`, ver <code>db/readonly_role.sql</code>);
        e, dentro da própria transação, <code>transaction_read_only</code> + <code>statement_timeout</code>. Se
        aparecer "Chat não configurado", é porque este ambiente não tem <code>GEMINI_API_KEY</code>/
        <code>DATABASE_URL_READONLY</code> definidas (ver README.md).
      </p>
    </div>
  );
}
