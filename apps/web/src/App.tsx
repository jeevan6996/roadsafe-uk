import {
  BarChart3,
  CircleAlert,
  ClipboardList,
  GitCompareArrows,
  Info,
  Map as MapIcon,
  Search,
} from "lucide-react";
import type {
  GeoJSONSource,
  Map as MapLibreMap,
  StyleSpecification,
} from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";

type Collision = {
  collision_id: string;
  longitude: number;
  latitude: number;
  severity: number;
  severity_label: string;
  date: string;
  time: string;
  speed_limit: number;
  vehicles: number;
  casualties: number;
  local_authority_code: string;
};

type Summary = {
  collisions: number;
  killed_or_seriously_injured: number;
  casualties: number;
  fatal: number;
  serious: number;
  slight: number;
};

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

const mapStyle: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

function App() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [collisions, setCollisions] = useState<Collision[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [selected, setSelected] = useState<Collision | null>(null);
  const [severity, setSeverity] = useState<"all" | "2" | "3">("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/collisions`).then((response) => response.json()),
      fetch(`${API}/summary`).then((response) => response.json()),
    ])
      .then(([collisionData, summaryData]) => {
        setCollisions(collisionData);
        setSummary(summaryData);
      })
      .catch(() => setError("Evidence API unavailable"));
  }, []);

  const visible = useMemo(
    () =>
      collisions.filter(
        (collision) =>
          (severity === "all" || collision.severity === Number(severity)) &&
          collision.collision_id.toLowerCase().includes(query.trim().toLowerCase()),
      ),
    [collisions, query, severity],
  );

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;
    let disposed = false;

    void import("maplibre-gl").then((maplibregl) => {
      if (disposed || !mapContainer.current) return;
      const map = new maplibregl.Map({
        container: mapContainer.current,
        style: mapStyle,
        center: [-1.731, 53.8],
        zoom: 11.1,
        attributionControl: false,
      });
      map.addControl(
        new maplibregl.NavigationControl({ showCompass: false }),
        "bottom-left",
      );
      map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
      mapRef.current = map;
      setMapReady(true);
    });

    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const update = () => {
      const geojson: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features: visible.map((collision) => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [collision.longitude, collision.latitude],
          },
          properties: collision,
        })),
      };
      const source = map.getSource("collisions") as GeoJSONSource | undefined;
      if (source) {
        source.setData(geojson);
        return;
      }
      map.addSource("collisions", { type: "geojson", data: geojson });
      map.addLayer({
        id: "collision-halo",
        type: "circle",
        source: "collisions",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 7, 14, 13],
          "circle-color": "#ffffff",
          "circle-opacity": 0.9,
        },
      });
      map.addLayer({
        id: "collisions",
        type: "circle",
        source: "collisions",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 4, 14, 8],
          "circle-color": ["match", ["get", "severity"], 1, "#a92727", 2, "#d97706", "#087f6b"],
          "circle-stroke-color": "#17211c",
          "circle-stroke-width": 1,
        },
      });
      map.on("click", "collisions", (event) => {
        const id = event.features?.[0]?.properties?.collision_id;
        const collision = collisions.find((item) => item.collision_id === id);
        if (collision) setSelected(collision);
      });
      map.on("mouseenter", "collisions", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "collisions", () => {
        map.getCanvas().style.cursor = "";
      });
    };
    if (map.isStyleLoaded()) update();
    else map.once("load", update);
  }, [visible, collisions, mapReady]);

  return (
    <main className="app-shell">
      <aside className="navigation" aria-label="Primary navigation">
        <div className="brand-mark" aria-label="RoadSafe UK">RS</div>
        <button className="nav-button active" title="Network"><MapIcon /></button>
        <button className="nav-button" title="Emerging risk (planned)" disabled><CircleAlert /></button>
        <button className="nav-button" title="Compare models (planned)" disabled><GitCompareArrows /></button>
        <button className="nav-button" title="Investigations (planned)" disabled><ClipboardList /></button>
        <button className="nav-button nav-bottom" title="Methods (planned)" disabled><BarChart3 /></button>
      </aside>

      <header className="topbar">
        <div>
          <h1>Network evidence</h1>
          <span>West Yorkshire · DfT 2024 observed pilot</span>
        </div>
        <label className="search-field">
          <Search size={17} />
          <input
            aria-label="Search collision ID"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search collision ID"
            value={query}
          />
        </label>
      </header>

      <section className="modebar" aria-label="Evidence mode">
        <button className="mode active">Observed</button>
        <button className="mode" disabled>Exposure</button>
        <button className="mode" disabled>Expected</button>
        <button className="mode" disabled>Agreement</button>
      </section>

      <section className="map-region" aria-label="Collision map">
        <div ref={mapContainer} className="map" />
        <div className="severity-control">
          <span>Severity</span>
          {(["all", "2", "3"] as const).map((value) => (
            <button
              className={severity === value ? "selected" : ""}
              key={value}
              onClick={() => setSeverity(value)}
            >
              {value === "all" ? "All" : value === "2" ? "Serious" : "Slight"}
            </button>
          ))}
        </div>
        {error && <div className="error-banner">{error}</div>}
      </section>

      <aside className="evidence-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Observed evidence</span>
            <h2>{selected ? selected.collision_id : "Pilot area"}</h2>
          </div>
          <Info size={18} />
        </div>

        {selected ? (
          <div className="selected-evidence">
            <div className={`severity-label severity-${selected.severity}`}>
              {selected.severity_label}
            </div>
            <dl className="detail-list">
              <div><dt>Date</dt><dd>{selected.date} · {selected.time}</dd></div>
              <div><dt>Casualties</dt><dd>{selected.casualties}</dd></div>
              <div><dt>Vehicles</dt><dd>{selected.vehicles}</dd></div>
              <div><dt>Speed limit</dt><dd>{selected.speed_limit} mph</dd></div>
              <div><dt>Authority</dt><dd>{selected.local_authority_code}</dd></div>
            </dl>
          </div>
        ) : (
          <>
            <div className="metric-row">
              <div><span>Collisions</span><strong>{summary?.collisions ?? "—"}</strong></div>
              <div><span>KSI</span><strong>{summary?.killed_or_seriously_injured ?? "—"}</strong></div>
              <div><span>Casualties</span><strong>{summary?.casualties ?? "—"}</strong></div>
            </div>
            <div className="distribution">
              <div className="distribution-heading"><span>Severity distribution</span><span>Records</span></div>
              <div className="bar-track">
                <div className="bar serious" style={{ width: `${((summary?.serious ?? 0) / (summary?.collisions || 1)) * 100}%` }} />
                <div className="bar slight" style={{ width: `${((summary?.slight ?? 0) / (summary?.collisions || 1)) * 100}%` }} />
              </div>
              <div className="legend"><span><i className="dot serious" />Serious {summary?.serious ?? 0}</span><span><i className="dot slight" />Slight {summary?.slight ?? 0}</span></div>
            </div>
            <div className="notice">
              <Info size={17} />
              <p>Police-reported personal-injury collisions. Observed concentration is not exposure-adjusted risk.</p>
            </div>
          </>
        )}
      </aside>

      <footer className="statusbar">
        <span><i className="status-dot" />Final validated data</span>
        <span>Fixture · {visible.length} visible records</span>
        <span className="status-right">OGL v3.0 · DfT STATS19</span>
      </footer>
    </main>
  );
}

export default App;
