import { BrowserRouter, Link, NavLink, Route, Routes } from "react-router-dom";
import { Ranking } from "./pages/Ranking";
import { MunicipioDetalhe } from "./pages/MunicipioDetalhe";
import { Priorizacao } from "./pages/Priorizacao";
import { Tendencias } from "./pages/Tendencias";
import { Geografia } from "./pages/Geografia";

function App() {
  return (
    <BrowserRouter>
      <header className="cabecalho">
        <Link to="/" className="marca">
          <span className="marca-icone" aria-hidden="true">
            ⚡
          </span>
          <h1>Continua</h1>
        </Link>
        <span className="subtitulo">risco de interrupção de energia por município — dados ANEEL</span>
        <nav className="nav-principal">
          <NavLink to="/" end className={({ isActive }) => (isActive ? "ativo" : undefined)}>
            Ranking
          </NavLink>
          <NavLink to="/priorizacao" className={({ isActive }) => (isActive ? "ativo" : undefined)}>
            Priorização
          </NavLink>
          <NavLink to="/tendencias" className={({ isActive }) => (isActive ? "ativo" : undefined)}>
            Tendências
          </NavLink>
          <NavLink to="/geografia" className={({ isActive }) => (isActive ? "ativo" : undefined)}>
            Geografia
          </NavLink>
        </nav>
      </header>

      <Routes>
        <Route path="/" element={<Ranking />} />
        <Route path="/municipios/:codigoIbge" element={<MunicipioDetalhe />} />
        <Route path="/priorizacao" element={<Priorizacao />} />
        <Route path="/tendencias" element={<Tendencias />} />
        <Route path="/geografia" element={<Geografia />} />
      </Routes>

      <footer className="rodape">
        Continua — desafio técnico Zeki. Dados: ANEEL (Portal de Dados Abertos).
      </footer>
    </BrowserRouter>
  );
}

export default App;
