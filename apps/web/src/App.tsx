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

type SegmentProperties = {
  segment_id: string;
  count_point_id: number;
  road_number: string;
  source_year: number;
  all_motor_vehicles: number;
  estimation_method: "Counted" | "Estimated";
  estimation_method_detailed: string;
  link_length_km: number;
  collision_count: number;
  ksi_count: number;
  collision_rate_per_100m_vehicle_km: number;
};

type SegmentFeature = GeoJSON.Feature<GeoJSON.LineString, SegmentProperties>;
type SegmentCollection = GeoJSON.FeatureCollection<GeoJSON.LineString, SegmentProperties>;

type NetworkSummary = {
  segments: number;
  segments_with_exposure: number;
  counted_exposure: number;
  estimated_exposure: number;
  matched_collisions: number;
  matched_ksi: number;
  scope: string;
  caveat: string;
};

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

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
  const [segmentData, setSegmentData] = useState<SegmentCollection>({
    type: "FeatureCollection",
    features: [],
  });
  const [networkSummary, setNetworkSummary] = useState<NetworkSummary | null>(null);
  const [selected, setSelected] = useState<Collision | null>(null);
  const [selectedSegment, setSelectedSegment] = useState<SegmentFeature | null>(null);
  const [mode, setMode] = useState<"observed" | "exposure">("observed");
  const [severity, setSeverity] = useState<"all" | "2" | "3">("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    Promise.all([
      getJson<Collision[]>(`${API}/collisions`),
      getJson<Summary>(`${API}/summary`),
      getJson<SegmentCollection>(`${API}/segments`),
      getJson<NetworkSummary>(`${API}/network-summary`),
    ])
      .then(([collisionData, summaryData, segmentsData, networkSummaryData]) => {
        setCollisions(collisionData);
        setSummary(summaryData);
        setSegmentData(segmentsData);
        setNetworkSummary(networkSummaryData);
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

  const visibleSegments = useMemo<SegmentCollection>(
    () => ({
      type: "FeatureCollection",
      features: segmentData.features.filter((feature) => {
        const term = query.trim().toLowerCase();
        return (
          !term ||
          feature.properties.road_number.toLowerCase().includes(term) ||
          feature.properties.segment_id.toLowerCase().includes(term)
        );
      }),
    }),
    [query, segmentData],
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
        const collision = event.features?.[0]?.properties as Collision | undefined;
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
  }, [visible, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const update = () => {
      const source = map.getSource("segments") as GeoJSONSource | undefined;
      if (source) {
        source.setData(visibleSegments);
        return;
      }
      map.addSource("segments", { type: "geojson", data: visibleSegments });
      map.addLayer({
        id: "segment-exposure",
        type: "line",
        source: "segments",
        layout: { visibility: "none", "line-cap": "round" },
        paint: {
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 2.5, 14, 8],
          "line-color": [
            "interpolate",
            ["linear"],
            ["get", "all_motor_vehicles"],
            0,
            "#7b8782",
            10000,
            "#087f6b",
            30000,
            "#d97706",
            65000,
            "#a92727",
          ],
          "line-opacity": 0.9,
        },
      });
      map.on("click", "segment-exposure", (event) => {
        const feature = event.features?.[0] as SegmentFeature | undefined;
        if (feature) setSelectedSegment(feature);
      });
      map.on("mouseenter", "segment-exposure", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "segment-exposure", () => {
        map.getCanvas().style.cursor = "";
      });
    };
    if (map.isStyleLoaded()) update();
    else map.once("load", update);
  }, [mapReady, visibleSegments]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const observedVisibility = mode === "observed" ? "visible" : "none";
    const exposureVisibility = mode === "exposure" ? "visible" : "none";
    if (map.getLayer("collisions")) {
      map.setLayoutProperty("collisions", "visibility", observedVisibility);
      map.setLayoutProperty("collision-halo", "visibility", observedVisibility);
    }
    if (map.getLayer("segment-exposure")) {
      map.setLayoutProperty("segment-exposure", "visibility", exposureVisibility);
    }
  }, [mode, mapReady, segmentData]);

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
            aria-label={mode === "observed" ? "Search collision ID" : "Search road or segment"}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={mode === "observed" ? "Search collision ID" : "Search road or segment"}
            value={query}
          />
        </label>
      </header>

      <section className="modebar" aria-label="Evidence mode">
        <button
          className={`mode ${mode === "observed" ? "active" : ""}`}
          onClick={() => {
            setMode("observed");
            setSelectedSegment(null);
            setQuery("");
          }}
        >Observed</button>
        <button
          className={`mode ${mode === "exposure" ? "active" : ""}`}
          onClick={() => {
            setMode("exposure");
            setSelected(null);
            setQuery("");
          }}
        >Exposure</button>
        <button className="mode" disabled>Expected</button>
        <button className="mode" disabled>Agreement</button>
      </section>

      <section className="map-region" aria-label="Collision map">
        <div ref={mapContainer} className="map" />
        {mode === "observed" && <div className="severity-control">
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
        </div>}
        {mode === "exposure" && (
          <div className="exposure-legend" aria-label="Daily motor vehicle flow legend">
            <span>Daily motor vehicles</span>
            <i className="flow-low" />Low
            <i className="flow-medium" />Medium
            <i className="flow-high" />High
          </div>
        )}
        {error && <div className="error-banner">{error}</div>}
      </section>

      <aside className="evidence-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">{mode === "observed" ? "Observed evidence" : "Traffic exposure"}</span>
            <h2>{mode === "observed" ? (selected ? selected.collision_id : "Pilot area") : (selectedSegment?.properties.road_number ?? "Major-road network")}</h2>
          </div>
          <Info size={18} />
        </div>

        {mode === "exposure" ? (
          selectedSegment ? (
            <div className="selected-evidence">
              <div className={`method-label method-${selectedSegment.properties.estimation_method.toLowerCase()}`}>
                {selectedSegment.properties.estimation_method}
              </div>
              <dl className="detail-list">
                <div><dt>Daily motor vehicles</dt><dd>{selectedSegment.properties.all_motor_vehicles.toLocaleString()}</dd></div>
                <div><dt>Count point</dt><dd>{selectedSegment.properties.count_point_id}</dd></div>
                <div><dt>Link length</dt><dd>{selectedSegment.properties.link_length_km} km</dd></div>
                <div><dt>Matched collisions</dt><dd>{selectedSegment.properties.collision_count}</dd></div>
                <div><dt>Matched KSI</dt><dd>{selectedSegment.properties.ksi_count}</dd></div>
                <div><dt>Method</dt><dd>{selectedSegment.properties.estimation_method_detailed}</dd></div>
              </dl>
              <div className="notice"><Info size={17} /><p>Descriptive 2024 exposure for this DfT major-road link. It is not an expected collision estimate.</p></div>
            </div>
          ) : (
            <>
              <div className="metric-row">
                <div><span>Links</span><strong>{networkSummary?.segments ?? "—"}</strong></div>
                <div><span>Counted</span><strong>{networkSummary?.counted_exposure ?? "—"}</strong></div>
                <div><span>Estimated</span><strong>{networkSummary?.estimated_exposure ?? "—"}</strong></div>
              </div>
              <div className="distribution">
                <div className="distribution-heading"><span>Matched evidence</span><span>Accepted</span></div>
                <dl className="detail-list compact">
                  <div><dt>Collisions</dt><dd>{networkSummary?.matched_collisions ?? "—"}</dd></div>
                  <div><dt>KSI collisions</dt><dd>{networkSummary?.matched_ksi ?? "—"}</dd></div>
                  <div><dt>Scope</dt><dd>{networkSummary?.scope ?? "—"}</dd></div>
                </dl>
              </div>
              <div className="notice"><Info size={17} /><p>{networkSummary?.caveat ?? "Loading exposure limitations."}</p></div>
            </>
          )
        ) : selected ? (
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
        <span>{mode === "observed" ? `${visible.length} visible collisions` : `${visibleSegments.features.length} major-road links`}</span>
        <span className="status-right">OGL v3.0 · DfT STATS19 + Road Traffic Statistics</span>
      </footer>
    </main>
  );
}

export default App;
