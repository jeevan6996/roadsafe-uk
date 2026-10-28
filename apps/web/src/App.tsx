import {
  BarChart3,
  CircleAlert,
  ClipboardList,
  GitCompareArrows,
  Info,
  Map as MapIcon,
  Search,
  Download,
  RotateCw,
  X,
} from "lucide-react";
import type {
  GeoJSONSource,
  Map as MapLibreMap,
  StyleSpecification,
} from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { buildEvidenceExport, mergeRetrospectiveEvidence } from "./evidence";
import { useRoadCollisions, type Collision } from "./roadCollisions";

type Summary = {
  collisions: number;
  killed_or_seriously_injured: number;
  casualties: number;
  fatal: number;
  serious: number;
  slight: number;
};

export type SegmentProperties = {
  segment_key: string;
  segment_id: string;
  count_point_id: number;
  road_number: string;
  source_year: number;
  local_authority_name?: string;
  all_motor_vehicles: number;
  estimation_method: "Counted" | "Estimated";
  estimation_method_detailed: string;
  link_length_km: number;
  collision_count: number;
  ksi_count: number;
  collision_rate_per_100m_vehicle_km: number;
  prior_expected_ksi?: number;
  expected_ksi?: number;
  expected_ksi_std?: number;
  excess_ksi?: number;
};

export type SegmentFeature = GeoJSON.Feature<GeoJSON.LineString, SegmentProperties>;
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

export type EmpiricalBayesResponse = {
  available: boolean;
  year?: number;
  records?: Array<{
    segment_key: string;
    year: number;
    ksi_count: number;
    prior_expected_ksi: number;
    expected_ksi: number;
    expected_ksi_std: number;
    excess_ksi: number;
  }>;
  reason?: string;
};

export type Metadata = {
  dataset: string;
  source: string;
  source_year: number;
  status: string;
  scope: string;
  licence: string;
  caveat: string;
  collision_sha256: string;
  network_sha256: string;
  empirical_bayes_sha256: string | null;
};

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
const NO_COLLISIONS: Collision[] = [];

type Scoped<T> = { data: T; snapshot: string | null };

async function getJson<T>(url: string): Promise<Scoped<T>> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return { data: await response.json() as T, snapshot: response.headers.get("X-RoadSafe-Snapshot") };
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
  const [selectedSegmentKey, setSelectedSegmentKey] = useState<string | null>(null);
  function selectRoad(key: string | null) {
    setSelectedSegmentKey(key);
    setSelected(null);
    setExportStatus("");
  }
  const setSelectedSegment = (feature: SegmentFeature | null) => selectRoad(feature?.properties.segment_key ?? null);
  const [mode, setMode] = useState<"observed" | "exposure" | "screening" | "expected">("observed");
  const [severity, setSeverity] = useState<"all" | "1" | "2" | "3">("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<Metadata | null>(null);
  const [exportStatus, setExportStatus] = useState("");
  const [mapReady, setMapReady] = useState(false);
  const [mapIdle, setMapIdle] = useState(false);
  const [empiricalBayes, setEmpiricalBayes] = useState<EmpiricalBayesResponse>({ available: false });

  useEffect(() => {
    Promise.all([
      getJson<Collision[]>(`${API}/collisions?limit=5000`),
      getJson<Summary>(`${API}/summary`),
      getJson<SegmentCollection>(`${API}/segments`),
      getJson<NetworkSummary>(`${API}/network-summary`),
      getJson<Metadata>(`${API}/metadata`).catch(() => null),
      getJson<EmpiricalBayesResponse>(`${API}/empirical-bayes?year=2024`).catch(() => null),
    ])
      .then(([collisionResponse, summaryResponse, segmentResponse, networkResponse, metadataResponse, modelResponse]) => {
        const snapshot = segmentResponse.snapshot;
        if (!snapshot?.trim() || [collisionResponse, summaryResponse, networkResponse].some((response) => response.snapshot !== snapshot)) {
          setError("Evidence snapshot mismatch. Reload to load a consistent dataset.");
          return;
        }
        const segmentsData = segmentResponse.data;
        const keys = segmentsData.features.map((feature) => feature.properties.segment_key);
        if (keys.some((key) => typeof key !== "string" || !key.trim()) || new Set(keys).size !== keys.length) {
          setError("Road evidence has missing or duplicate segment keys. Rebuild network data.");
          return;
        }
        setCollisions(collisionResponse.data);
        setSummary(summaryResponse.data);
        setSegmentData(segmentsData);
        setNetworkSummary(networkResponse.data);
        setMetadata(metadataResponse?.snapshot === snapshot ? metadataResponse.data : null);
        setEmpiricalBayes(modelResponse?.snapshot === snapshot ? modelResponse.data : { available: false });
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
      features: segmentData.features
        .map((feature) => mergeRetrospectiveEvidence(feature, empiricalBayes))
        .filter((feature) => {
          const term = mode === "observed" ? "" : query.trim().toLowerCase();
          return (
            !term ||
            feature.properties.road_number.toLowerCase().includes(term) ||
            feature.properties.segment_id.toLowerCase().includes(term)
          );
        }),
    }),
    [empiricalBayes, query, segmentData, mode],
  );

  const selectedSegment = visibleSegments.features.find(
    (feature) => feature.properties.segment_key === selectedSegmentKey,
  ) ?? null;
  const focusKey = selectedSegment?.properties.segment_key ?? null;
  const roadCollisions = useRoadCollisions(API, focusKey, selectedSegment?.properties.source_year, metadata?.collision_sha256, metadata?.network_sha256);
  const focusedCollisions = useMemo(() =>
    roadCollisions.data?.available ? roadCollisions.data.collisions.filter((collision) =>
      (severity === "all" || collision.severity === Number(severity)) &&
      (mode !== "observed" || collision.collision_id.toLowerCase().includes(query.trim().toLowerCase())),
    ) : [], [roadCollisions.data, severity, mode, query]);
  const mapCollisions = selectedSegment ? focusedCollisions : mode === "observed" ? visible : NO_COLLISIONS;
  const activeCollision = selected && mapCollisions.some((collision) => collision.collision_id === selected.collision_id) ? selected : null;

  useEffect(() => {
    if (selectedSegmentKey && !selectedSegment) selectRoad(null);
  }, [selectedSegmentKey, selectedSegment]);

  useEffect(() => {
    if (selected && !activeCollision) setSelected(null);
  }, [selected, activeCollision]);

  function exportEvidence() {
    if (!selectedSegment || !metadata) return;
    try {
      const payload = buildEvidenceExport(selectedSegment, metadata);
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `roadsafe-${selectedSegment.properties.count_point_id}-${selectedSegment.properties.source_year}.json`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setExportStatus("Evidence exported");
    } catch {
      setExportStatus("Export failed. Please try again.");
    }
  }

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;
    let disposed = false;

    void import("maplibre-gl").then((maplibregl) => {
      if (disposed || !mapContainer.current) return;
      // Vite relocates the engine, so its sibling worker needs an explicit bundled URL.
      maplibregl.setWorkerUrl(mapWorkerUrl);
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
      map.on("movestart", () => setMapIdle(false));
      map.on("dataloading", () => setMapIdle(false));
      map.on("idle", () => setMapIdle(true));
      map.on("style.load", () => setMapReady(true));
      mapRef.current = map;
    });

    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const update = () => {
      const geojson: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features: mapCollisions.map((collision) => ({
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
    update();
  }, [mapCollisions, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const update = () => {
      const source = map.getSource("segments") as GeoJSONSource | undefined;
      if (source) {
        source.setData(visibleSegments);
        return;
      }
      map.addSource("segments", { type: "geojson", data: visibleSegments });
      for (const [id, color, low, high] of [
        ["segment-focus-outline", "#17211c", 9, 16],
        ["segment-focus-inner", "#ffffff", 6, 12],
      ] as const) {
        map.addLayer({
          id, type: "line", source: "segments", filter: ["==", ["get", "segment_key"], ""],
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": color, "line-width": ["interpolate", ["linear"], ["zoom"], 8, low, 14, high] },
        });
      }
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
      map.addLayer({
        id: "segment-screening",
        type: "line",
        source: "segments",
        layout: { visibility: "none", "line-cap": "round" },
        paint: {
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 2.5, 14, 8],
          "line-color": [
            "interpolate",
            ["linear"],
            ["get", "collision_rate_per_100m_vehicle_km"],
            0,
            "#087f6b",
            5,
            "#d97706",
            20,
            "#a92727",
          ],
          "line-opacity": 0.92,
        },
      });
      map.addLayer({
        id: "segment-expected",
        filter: ["has", "excess_ksi"],
        type: "line",
        source: "segments",
        layout: { visibility: "none", "line-cap": "round" },
        paint: {
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 2.5, 14, 8],
          "line-color": [
            "interpolate",
            ["linear"],
            ["get", "excess_ksi"],
            0,
            "#087f6b",
            1,
            "#d97706",
            4,
            "#a92727",
          ],
          "line-opacity": 0.92,
        },
      });
      map.on("click", "segment-exposure", (event) => {
        const feature = event.features?.[0] as SegmentFeature | undefined;
        if (feature && !map.queryRenderedFeatures(event.point, { layers: ["collisions"] }).length) setSelectedSegment(feature);
      });
      map.on("click", "segment-screening", (event) => {
        const feature = event.features?.[0] as SegmentFeature | undefined;
        if (feature && !map.queryRenderedFeatures(event.point, { layers: ["collisions"] }).length) setSelectedSegment(feature);
      });
      map.on("click", "segment-expected", (event) => {
        const feature = event.features?.[0] as SegmentFeature | undefined;
        if (feature && !map.queryRenderedFeatures(event.point, { layers: ["collisions"] }).length) setSelectedSegment(feature);
      });
      map.on("mouseenter", "segment-exposure", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "segment-exposure", () => {
        map.getCanvas().style.cursor = "";
      });
      map.on("mouseenter", "segment-screening", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "segment-screening", () => {
        map.getCanvas().style.cursor = "";
      });
      map.on("mouseenter", "segment-expected", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "segment-expected", () => {
        map.getCanvas().style.cursor = "";
      });
    };
    update();
  }, [mapReady, visibleSegments]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const update = () => {
    const observedVisibility = mode === "observed" || selectedSegment ? "visible" : "none";
    const exposureVisibility = mode === "exposure" ? "visible" : "none";
    const screeningVisibility = mode === "screening" ? "visible" : "none";
    const expectedVisibility = mode === "expected" ? "visible" : "none";
    if (map.getLayer("collisions")) {
      map.setLayoutProperty("collisions", "visibility", observedVisibility);
      map.setLayoutProperty("collision-halo", "visibility", observedVisibility);
    }
    if (map.getLayer("segment-exposure")) {
      map.setLayoutProperty("segment-exposure", "visibility", exposureVisibility);
    }
    if (map.getLayer("segment-screening")) {
      map.setLayoutProperty("segment-screening", "visibility", screeningVisibility);
    }
    if (map.getLayer("segment-expected")) {
      map.setLayoutProperty("segment-expected", "visibility", expectedVisibility);
    }
    for (const id of ["segment-focus-outline", "segment-focus-inner"]) {
      if (map.getLayer(id)) {
        map.setFilter(id, ["==", ["get", "segment_key"], focusKey ?? ""]);
      }
    }
    for (const [id, opacity] of [["segment-exposure", 0.9], ["segment-screening", 0.92], ["segment-expected", 0.92]] as const) {
      if (map.getLayer(id)) map.setPaintProperty(id, "line-opacity", focusKey
        ? ["case", ["==", ["get", "segment_key"], focusKey], opacity, 0.2] : opacity);
    }
    // Road layers are created after points; keep collision hit targets above them.
    if (map.getLayer("collision-halo")) map.moveLayer("collision-halo");
    if (map.getLayer("collisions")) map.moveLayer("collisions");
    };
    update();
  }, [mode, mapReady, visible, visibleSegments, focusKey, selectedSegment]);

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
          <h1>RoadSafe UK</h1>
          <span>{metadata?.scope ?? "West Yorkshire · source metadata unavailable"}</span>
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
          aria-pressed={mode === "observed"}
          onClick={() => {
            setMode("observed");
            setQuery("");
          }}
        >Observed</button>
        <button
          className={`mode ${mode === "exposure" ? "active" : ""}`}
          aria-pressed={mode === "exposure"}
          onClick={() => {
            setMode("exposure");
            setSelected(null);
            setQuery("");
          }}
        >Exposure</button>
        <button
          className={`mode ${mode === "screening" ? "active" : ""}`}
          aria-pressed={mode === "screening"}
          onClick={() => {
            setMode("screening");
            setSelected(null);
            setQuery("");
          }}
        >Screening</button>
        <button
          className={`mode ${mode === "expected" ? "active" : ""}`}
          aria-pressed={mode === "expected"}
          disabled={!empiricalBayes.available}
          title={empiricalBayes.available ? "Empirical Bayes screening" : "Expected-frequency model unavailable"}
          onClick={() => {
            setMode("expected");
            setSelected(null);
            setQuery("");
          }}
        >Retrospective</button>
        <button className="mode" disabled>Agreement</button>
      </section>

      <section className="map-region" aria-label="Collision map" aria-busy={!mapIdle}>
        <div ref={mapContainer} className="map" />
        {mode === "observed" && !selectedSegment && <div className="severity-control">
          <span>Severity</span>
          {(["all", "1", "2", "3"] as const).map((value) => (
            <button
              className={severity === value ? "selected" : ""}
              aria-pressed={severity === value}
              key={value}
              onClick={() => setSeverity(value)}
            >
              {value === "all" ? "All" : value === "1" ? "Fatal" : value === "2" ? "Serious" : "Slight"}
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
        {mode === "screening" && (
          <div className="exposure-legend" aria-label="Observed collision rate legend">
            <span>Observed rate</span>
            <i className="flow-low" />Low
            <i className="flow-medium" />Elevated
            <i className="flow-high" />High
          </div>
        )}
        {mode === "expected" && (
          <div className="exposure-legend" aria-label="Excess frequency legend">
            <span>Excess frequency</span>
            <i className="flow-low" />Low
            <i className="flow-medium" />Elevated
            <i className="flow-high" />High
          </div>
        )}
        {error && <div className="error-banner">{error}</div>}
      </section>

      <aside className="evidence-panel">
        {(mode !== "observed" || selectedSegment) && <div className="investigation-tools">
          <label htmlFor="road-segment">Road segment</label>
          <select id="road-segment" value={selectedSegment?.properties.segment_key ?? ""}
            onChange={(event) => {
              selectRoad(event.target.value || null);
              const feature = visibleSegments.features.find((item) => item.properties.segment_key === event.target.value);
              if (feature) {
                const coordinates = feature.geometry.coordinates;
                const xs = coordinates.map((point) => point[0]);
                const ys = coordinates.map((point) => point[1]);
                mapRef.current?.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], { padding: 70, maxZoom: 14 });
              }
            }}>
            <option value="">{visibleSegments.features.length ? "Network overview" : "No matching segments"}</option>
            {visibleSegments.features.map((feature) => <option key={feature.properties.segment_key} value={feature.properties.segment_key}>
              {feature.properties.road_number} · {feature.properties.count_point_id}
            </option>)}
          </select>
          <div className="investigation-actions">
            <button className="export-button" disabled={!selectedSegment || !metadata} onClick={exportEvidence}><Download size={16} />Export evidence</button>
            <button className="icon-button" title="Clear selection" aria-label="Clear selection" disabled={!selectedSegment} onClick={() => { setSelectedSegment(null); setExportStatus(""); }}><X /></button>
          </div>
          <span className="export-status" role="status">{exportStatus}</span>
        </div>}
        {selectedSegment && <section className="road-collisions" aria-label="Matched road collisions">
          <h3>Matched collision locations</h3>
          <div className="road-severity" aria-label="Collision severity">
            {(["all", "1", "2", "3"] as const).map((value) => (
              <button key={value} aria-pressed={severity === value} onClick={() => setSeverity(value)}>
                {value === "all" ? "All" : value === "1" ? "Fatal" : value === "2" ? "Serious" : "Slight"}
              </button>
            ))}
          </div>
          <p className="matching-state" aria-live="polite">
            {roadCollisions.status === "loading" ? "Loading matched collisions…"
              : roadCollisions.status === "error" ? "Could not load matched collisions."
              : !roadCollisions.data?.available ? `Matched collision locations unavailable${roadCollisions.data?.reason ? `: ${roadCollisions.data.reason}` : "."}`
              : `${focusedCollisions.length} of ${roadCollisions.data.collisions.length} matched collisions`}
          </p>
          {(roadCollisions.status === "error" || (roadCollisions.status === "ready" && !roadCollisions.data?.available)) &&
            <button className="retry-button" onClick={roadCollisions.retry}><RotateCw size={16} />Retry matched collisions</button>}
          {roadCollisions.data?.available && <ul className="collision-list" aria-label="Matched collisions">
            {focusedCollisions.map((collision) => <li key={collision.collision_id}>
              <button aria-pressed={activeCollision?.collision_id === collision.collision_id} onClick={() => setSelected(collision)}>
                <i className={`dot ${collision.severity === 1 ? "fatal" : collision.severity === 2 ? "serious" : "slight"}`} />
                <span>{collision.collision_id}</span><span>{collision.severity_label}</span>
              </button>
            </li>)}
          </ul>}
          {activeCollision && <section aria-label="Collision details">
            <div className="collision-heading"><h3>{activeCollision.collision_id}</h3>
              <button className="icon-button" title="Close collision details" aria-label="Close collision details" onClick={() => setSelected(null)}><X /></button>
            </div>
            <CollisionDetails collision={activeCollision} />
          </section>}
        </section>}
        <div className="panel-heading">
          <div>
            <span className="eyebrow">
              {mode === "observed" ? "Observed evidence" : mode === "exposure" ? "Traffic exposure" : "Exposure-adjusted screening"}
            </span>
            <h2>{selectedSegment?.properties.road_number ?? (mode === "observed" ? (activeCollision ? activeCollision.collision_id : "Pilot area") : "Major-road network")}</h2>
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
                <div><dt>Matched KSI collisions</dt><dd>{selectedSegment.properties.ksi_count}</dd></div>
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
        ) : mode === "screening" ? (
          selectedSegment ? (
            <div className="selected-evidence">
              <div className="method-label method-estimated">Observed screening</div>
              <dl className="detail-list">
                <div><dt>Collision rate</dt><dd>{selectedSegment.properties.collision_rate_per_100m_vehicle_km.toFixed(2)} / 100m vehicle-km</dd></div>
                <div><dt>Observed collisions</dt><dd>{selectedSegment.properties.collision_count}</dd></div>
                <div><dt>Observed KSI collisions</dt><dd>{selectedSegment.properties.ksi_count}</dd></div>
                <div><dt>Exposure</dt><dd>{selectedSegment.properties.all_motor_vehicles.toLocaleString()} vehicles/day</dd></div>
                <div><dt>Road</dt><dd>{selectedSegment.properties.road_number}</dd></div>
              </dl>
              <div className="notice"><Info size={17} /><p>Descriptive observed rate normalised by traffic exposure. This is a screening signal, not an expected-frequency or causal-risk estimate.</p></div>
            </div>
          ) : (
            <>
              <div className="metric-row">
                <div><span>Links</span><strong>{networkSummary?.segments ?? "—"}</strong></div>
                <div><span>Matched KSI</span><strong>{networkSummary?.matched_ksi ?? "—"}</strong></div>
                <div><span>Exposure basis</span><strong>AADF</strong></div>
              </div>
              <div className="notice"><Info size={17} /><p>Segments are coloured by observed collisions per 100 million vehicle-kilometres. Low counts and estimated exposure require cautious interpretation.</p></div>
            </>
          )
        ) : mode === "expected" ? (
          selectedSegment ? (
            <div className="selected-evidence">
              <div className="method-label method-counted">Empirical Bayes</div>
              <dl className="detail-list">
                <div><dt>Expected KSI</dt><dd>{selectedSegment.properties.expected_ksi?.toFixed(2) ?? "—"}</dd></div>
                <div><dt>Standard deviation proxy</dt><dd>{selectedSegment.properties.expected_ksi_std?.toFixed(2) ?? "—"}</dd></div>
                <div><dt>Observed KSI collisions</dt><dd>{selectedSegment.properties.ksi_count}</dd></div>
                <div><dt>Excess KSI</dt><dd>{selectedSegment.properties.excess_ksi?.toFixed(2) ?? "—"}</dd></div>
                <div><dt>Road</dt><dd>{selectedSegment.properties.road_number}</dd></div>
              </dl>
              <div className="notice"><Info size={17} /><p>{selectedSegment.properties.expected_ksi === undefined ? "No matching retrospective evidence for this segment and year." : "Retrospective Empirical Bayes screening uses the observed period count. It is not a future prediction or causal intervention estimate."}</p></div>
            </div>
          ) : (
            <>
              <div className="metric-row">
                <div><span>Links</span><strong>{visibleSegments.features.length}</strong></div>
                <div><span>Model</span><strong>EB</strong></div>
                <div><span>Period</span><strong>2024</strong></div>
              </div>
              <div className="notice"><Info size={17} /><p>Lines show positive excess frequency after shrinking observed KSI counts toward a training-period prior. Review uncertainty and data quality before interpretation.</p></div>
            </>
          )
        ) : selectedSegment ? null : activeCollision ? (
          <CollisionDetails collision={activeCollision} />
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
                <div className="bar fatal" style={{ width: `${((summary?.fatal ?? 0) / (summary?.collisions || 1)) * 100}%` }} />
                <div className="bar serious" style={{ width: `${((summary?.serious ?? 0) / (summary?.collisions || 1)) * 100}%` }} />
                <div className="bar slight" style={{ width: `${((summary?.slight ?? 0) / (summary?.collisions || 1)) * 100}%` }} />
              </div>
              <div className="legend"><span><i className="dot fatal" />Fatal {summary?.fatal ?? 0}</span><span><i className="dot serious" />Serious {summary?.serious ?? 0}</span><span><i className="dot slight" />Slight {summary?.slight ?? 0}</span></div>
            </div>
            <div className="notice">
              <Info size={17} />
              <p>Police-reported personal-injury collisions. Observed concentration is not exposure-adjusted risk.</p>
            </div>
          </>
        )}
        <details className="source-details">
          <summary>Source and scope</summary>
          <p>{metadata?.scope ?? "Source metadata unavailable"}</p>
          {metadata && <><a href={metadata.source} target="_blank" rel="noreferrer">Department for Transport source</a><p>{metadata.licence}</p></>}
          <p>Major-road matches within 50 metres. Ambiguous matches excluded.</p>
        </details>
      </aside>

      <footer className="statusbar">
        <span><i className="status-dot" />{metadata?.scope.includes("fixture") ? "Fixture evidence" : metadata?.status ?? "Source unverified"}</span>
        <span>{mode === "observed" ? `${mapCollisions.length} visible / ${summary?.collisions ?? "?"} collisions` : `${visibleSegments.features.length} major-road links`}</span>
        <span className="status-right">OGL v3.0 · DfT STATS19 + Road Traffic Statistics</span>
      </footer>
    </main>
  );
}

function CollisionDetails({ collision }: { collision: Collision }) {
  return <div className="selected-evidence">
    <div className={`severity-label severity-${collision.severity}`}>{collision.severity_label}</div>
    <dl className="detail-list">
      <div><dt>Date</dt><dd>{collision.date} · {collision.time}</dd></div>
      <div><dt>Casualties</dt><dd>{collision.casualties}</dd></div>
      <div><dt>Vehicles</dt><dd>{collision.vehicles}</dd></div>
      <div><dt>Speed limit</dt><dd>{collision.speed_limit} mph</dd></div>
      <div><dt>Authority</dt><dd>{collision.local_authority_code}</dd></div>
    </dl>
  </div>;
}

export default App;
