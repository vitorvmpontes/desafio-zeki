import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import type { MapaResponse } from "../lib/api";
import { urlKmlMapa } from "../lib/api";
import { formatarFec } from "../lib/risco";

// Mesma paleta de 4 niveis ja usada no resto do app para risco/confianca
// (ver web/src/index.css, --cor-risco-*) -- reaproveitada aqui para nao
// introduzir uma segunda linguagem de cor so para o mapa.
const COR_SEVERIDADE: Record<string, string> = {
  critico: "var(--cor-risco-alto)",
  alto: "var(--cor-risco-medio-alto)",
  moderado: "var(--cor-risco-medio)",
  baixo: "var(--cor-risco-baixo)",
};

const ROTULO_SEVERIDADE: Record<string, string> = {
  critico: "Crítico",
  alto: "Alto",
  moderado: "Moderado",
  baixo: "Baixo",
};

const ORDEM_SEVERIDADE = ["critico", "alto", "moderado", "baixo"];

function formatarNumero(valor: number, casas = 2): string {
  return valor.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

export function MapaClusters({ dados }: { dados: MapaResponse }) {
  return (
    <div>
      <div className="mapa-legenda">
        {ORDEM_SEVERIDADE.filter((s) => dados.resumo_por_cluster.some((c) => c.severidade === s)).map((s) => {
          const resumo = dados.resumo_por_cluster.find((c) => c.severidade === s)!;
          return (
            <span key={s} className="mapa-legenda-item">
              <span className="mapa-legenda-cor" style={{ background: COR_SEVERIDADE[s] }} />
              {ROTULO_SEVERIDADE[s]} ({formatarNumero(resumo.n_municipios, 0)})
            </span>
          );
        })}
      </div>

      <MapContainer
        center={[-14.2, -51.9]}
        zoom={4}
        minZoom={3}
        maxZoom={12}
        style={{ height: 480, width: "100%", borderRadius: 8 }}
        scrollWheelZoom={false}
      >
        {/* Tiles escuros (CARTO Dark Matter, gratuitos e sem chave de API,
            mesma filosofia de zero-custo do resto do projeto) -- combinam
            com o tema escuro do site; os tiles claros padrao do OSM
            destoariam visualmente do resto da pagina. */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={19}
        />
        {dados.municipios.map((m) => (
          <CircleMarker
            key={m.codigo_ibge}
            center={[m.latitude, m.longitude]}
            radius={m.severidade === "critico" ? 6 : 4}
            pathOptions={{
              color: COR_SEVERIDADE[m.severidade] ?? "#888",
              fillColor: COR_SEVERIDADE[m.severidade] ?? "#888",
              fillOpacity: 0.75,
              weight: 1,
            }}
          >
            <Popup>
              <strong>{m.nome}</strong> ({m.uf}) -- {m.regiao}
              <br />
              Cluster: <strong>{ROTULO_SEVERIDADE[m.severidade] ?? m.severidade}</strong>
              <br />
              Frequência média: {formatarFec(m.fec_aprox_medio)} por 100 consumidores
              <br />
              dec_aprox_horas médio: {formatarNumero(m.dec_aprox_horas_medio, 2)}h
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>

      <p className="nota-metodologica" style={{ marginTop: 12, marginBottom: 4 }}>
        {dados.nota_metodologica}
      </p>
      <p style={{ fontSize: 13, marginTop: 0 }}>
        <a href={urlKmlMapa()} download="continua_mapa_clusters.kml">
          Baixar arquivo KML ({formatarNumero(dados.n_municipios_no_mapa, 0)} municípios, para abrir no Google
          Earth/Maps ou QGIS)
        </a>
      </p>
    </div>
  );
}
