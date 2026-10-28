import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";

const mapEvents = vi.hoisted(() => new Map<string, () => void>());
const sources = vi.hoisted(() => new Map<string, { setData: ReturnType<typeof vi.fn> }>());
const layers = vi.hoisted(() => new Set<string>());
const setLayoutProperty = vi.hoisted(() => vi.fn());
const setWorkerUrl = vi.hoisted(() => vi.fn());
const setPaintProperty = vi.hoisted(() => vi.fn());
const setFilter = vi.hoisted(() => vi.fn());
const layerClicks = vi.hoisted(() => new Map<string, (event: unknown) => void>());
const sourceData = vi.hoisted(() => new Map<string, GeoJSON.FeatureCollection>());
const snapshotHeaders = (token = "fixture-primary") => new Headers({ "X-RoadSafe-Snapshot": token });

vi.mock("maplibre-gl", () => {
  class MockMap {
    addControl = vi.fn();
    on = vi.fn((event: string, callback: unknown, handler?: (event: unknown) => void) => {
      if (typeof callback === "function") mapEvents.set(event, callback as () => void);
      if (event === "click" && typeof callback === "string" && handler) layerClicks.set(callback, handler);
    });
    remove = vi.fn();
    isStyleLoaded = vi.fn(() => false);
    once = vi.fn();
    getSource = vi.fn((name: string) => sources.get(name));
    addSource = vi.fn((name: string, source: { data: GeoJSON.FeatureCollection }) => {
      sourceData.set(name, source.data);
      sources.set(name, { setData: vi.fn((data: GeoJSON.FeatureCollection) => sourceData.set(name, data)) });
    });
    addLayer = vi.fn((layer: { id: string }) => layers.add(layer.id));
    getLayer = vi.fn((name: string) => layers.has(name));
    setLayoutProperty = setLayoutProperty;
    setPaintProperty = setPaintProperty;
    setFilter = setFilter;
    moveLayer = vi.fn();
    queryRenderedFeatures = vi.fn(() => []);
    off = vi.fn();
    fitBounds = vi.fn();
  }

  class MockControl {}

  return {
    setWorkerUrl,
    Map: MockMap,
    NavigationControl: MockControl,
    AttributionControl: MockControl,
    default: {
      Map: MockMap,
      NavigationControl: MockControl,
      AttributionControl: MockControl,
    },
  };
});

beforeEach(() => {
  mapEvents.clear();
  sources.clear();
  layers.clear();
  setLayoutProperty.mockClear();
  setWorkerUrl.mockClear();
  setPaintProperty.mockClear();
  setFilter.mockClear();
  layerClicks.clear();
  sourceData.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        headers: snapshotHeaders(),
        json: () =>
          Promise.resolve(
            url.endsWith("network-summary")
              ? {
                  segments: 6,
                  segments_with_exposure: 6,
                  counted_exposure: 1,
                  estimated_exposure: 5,
                  matched_collisions: 2,
                  matched_ksi: 1,
                  scope: "DfT major-road links only",
                  caveat: "AADF link estimates are descriptive exposure, not expected collision risk.",
                }
              : url.endsWith("summary")
                ? { collisions: 12, killed_or_seriously_injured: 3, casualties: 17, fatal: 0, serious: 3, slight: 9 }
                : url.endsWith("segments")
                  ? { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "LineString", coordinates: [[-1.8, 53.8], [-1.7, 53.8]] }, properties: {
                    segment_key: "road-1", segment_id: "2024-road-1", count_point_id: 1,
                    road_number: "A1", source_year: 2024, all_motor_vehicles: 1000,
                    estimation_method: "Counted", estimation_method_detailed: "Manual count",
                    link_length_km: 1, collision_count: 3, ksi_count: 2,
                    collision_rate_per_100m_vehicle_km: 10,
                  } }] }
                  : url.endsWith("metadata")
                    ? { scope: "Traceable West Yorkshire fixture", status: "final validated data", licence: "OGL v3.0", source: "https://www.gov.uk/", collision_sha256: "collision-hash", network_sha256: "network-hash" }
                  : [],
          ),
      }),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("map busy state follows loading and idle events", async () => {
  render(<App />);
  const map = screen.getByRole("region", { name: "Collision map" });
  expect(map).toHaveAttribute("aria-busy", "true");
  await waitFor(() => expect(mapEvents.has("idle")).toBe(true));
  act(() => mapEvents.get("idle")?.());
  expect(map).toHaveAttribute("aria-busy", "false");
  act(() => mapEvents.get("movestart")?.());
  expect(map).toHaveAttribute("aria-busy", "true");
  act(() => mapEvents.get("idle")?.());
  act(() => mapEvents.get("dataloading")?.());
  expect(map).toHaveAttribute("aria-busy", "true");
});

test("renders the evidence workspace and responsible-use caveat", async () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "RoadSafe UK" })).toBeInTheDocument();
  expect(await screen.findByText("Police-reported personal-injury collisions. Observed concentration is not exposure-adjusted risk.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retrospective" })).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Exposure" }));
  expect(screen.getByRole("heading", { name: "Major-road network" })).toBeInTheDocument();
  expect(screen.getByText("AADF link estimates are descriptive exposure, not expected collision risk.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Screening" }));
  expect(screen.getByText(/Segments are coloured by observed collisions/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retrospective" })).toBeDisabled();
});

test("exposes the selected evidence mode to assistive technology", async () => {
  render(<App />);
  await screen.findByText("Fixture evidence");
  const observed = screen.getByRole("button", { name: "Observed" });
  const exposure = screen.getByRole("button", { name: "Exposure" });
  const screening = screen.getByRole("button", { name: "Screening" });
  expect(observed).toHaveAttribute("aria-pressed", "true");
  expect(exposure).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(exposure);
  expect(observed).toHaveAttribute("aria-pressed", "false");
  expect(exposure).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screening);
  expect(exposure).toHaveAttribute("aria-pressed", "false");
  expect(screening).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(observed);
  expect(observed).toHaveAttribute("aria-pressed", "true");
  expect(exposure).toHaveAttribute("aria-pressed", "false");
  expect(screening).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("button", { name: "Retrospective" })).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("button", { name: "Retrospective" })).toBeDisabled();
});

test("exposes the selected severity filter to assistive technology", async () => {
  render(<App />);
  const all = screen.getByRole("button", { name: "All" });
  const fatal = screen.getByRole("button", { name: "Fatal" });
  expect(all).toHaveAttribute("aria-pressed", "true");
  expect(fatal).toHaveAttribute("aria-pressed", "false");
  for (const selected of ["Fatal", "Serious", "Slight", "All"]) {
    fireEvent.click(screen.getByRole("button", { name: selected }));
    for (const name of ["All", "Fatal", "Serious", "Slight"]) {
      expect(screen.getByRole("button", { name })).toHaveAttribute("aria-pressed", String(name === selected));
    }
  }
});

test("style readiness adds evidence before basemap idle and respects an early mode change", async () => {
  render(<App />);
  await screen.findByText("Fixture evidence");
  await waitFor(() => expect(mapEvents.has("style.load")).toBe(true));
  expect(setWorkerUrl).toHaveBeenCalledWith(expect.any(String));
  fireEvent.click(screen.getByRole("button", { name: "Exposure" }));
  expect(sources.size).toBe(0);
  act(() => mapEvents.get("style.load")?.());
  await waitFor(() => expect(sources.has("collisions")).toBe(true));
  expect(layers.has("segment-exposure")).toBe(true);
  expect(setLayoutProperty).toHaveBeenCalledWith("collisions", "visibility", "none");
  expect(setLayoutProperty).toHaveBeenCalledWith("segment-exposure", "visibility", "visible");
  expect(screen.getByRole("region", { name: "Collision map" })).toHaveAttribute("aria-busy", "true");
});

test("selects a canonical segment, exports evidence and clears selection", async () => {
  const createObjectURL = vi.fn(() => "blob:evidence");
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<App />);
  await screen.findByText("Fixture evidence");
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("collisions?limit=5000"));
  fireEvent.click(screen.getByRole("button", { name: "Exposure" }));
  const exportButton = screen.getByRole("button", { name: "Export evidence" });
  expect(exportButton).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Road segment"), { target: { value: "road-1" } });
  expect(screen.getByRole("heading", { name: "A1" })).toBeInTheDocument();
  expect(exportButton).toBeEnabled();
  fireEvent.click(exportButton);
  expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
  expect(click).toHaveBeenCalledOnce();
  expect(screen.getByRole("status")).toHaveTextContent("Evidence exported");
  fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
  expect(exportButton).toBeDisabled();
  expect(screen.getByRole("heading", { name: "Major-road network" })).toBeInTheDocument();
});

test("search cannot export a segment that is no longer visible", async () => {
  render(<App />);
  await screen.findByText("Fixture evidence");
  fireEvent.click(screen.getByRole("button", { name: "Screening" }));
  fireEvent.change(screen.getByLabelText("Road segment"), { target: { value: "road-1" } });
  fireEvent.change(screen.getByRole("textbox", { name: "Search road or segment" }), { target: { value: "nonexistent" } });
  expect(screen.getByRole("button", { name: "Export evidence" })).toBeDisabled();
  expect(screen.getByRole("option", { name: "No matching segments" })).toBeInTheDocument();
});

test("reports a download failure without reporting success", async () => {
  vi.stubGlobal("URL", { createObjectURL: vi.fn(() => { throw new Error("Unavailable"); }) });
  render(<App />);
  await screen.findByText("Fixture evidence");
  fireEvent.click(screen.getByRole("button", { name: "Exposure" }));
  fireEvent.change(screen.getByLabelText("Road segment"), { target: { value: "road-1" } });
  fireEvent.click(screen.getByRole("button", { name: "Export evidence" }));
  expect(screen.getByRole("status")).toHaveTextContent("Export failed");
});

test("rejects a legacy network artifact without stable segment keys", async () => {
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("segments")
    ? Promise.resolve({ ok: true, headers: snapshotHeaders(), json: async () => ({ type: "FeatureCollection", features: [{ properties: { count_point_id: 1 } }] }) })
    : originalFetch(url)));
  render(<App />);
  expect(await screen.findByText("Road evidence has missing or duplicate segment keys. Rebuild network data.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Exposure" }));
  expect(screen.getByRole("button", { name: "Export evidence" })).toBeDisabled();
});

const roadCollision = {
  collision_id: "matched-only", longitude: -1.75, latitude: 53.8, severity: 2,
  severity_label: "Serious", date: "2024-02-03", time: "12:30", casualties: 3,
  vehicles: 2, speed_limit: 30, local_authority_code: "E08000032",
};
const matchedResponse = (key = "road-1") => ({
  segment_key: key, source_year: 2024, available: true, reason: null,
  collisions: [roadCollision], collision_sha256: "collision-hash", network_sha256: "network-hash",
  matching: { method: "nearest-unambiguous", max_distance_m: 30, ambiguity_margin_m: 5 },
});

async function startRoadFocus() {
  render(<App />);
  await screen.findByText("Fixture evidence");
  await waitFor(() => expect(mapEvents.has("style.load")).toBe(true));
  act(() => mapEvents.get("style.load")?.());
  fireEvent.click(screen.getByRole("button", { name: "Exposure" }));
  fireEvent.change(screen.getByLabelText("Road segment"), { target: { value: "road-1" } });
}

test("focus outlines the selected road, dims context and restores opacity on clear", async () => {
  await startRoadFocus();
  expect(layers.has("segment-focus-outline")).toBe(true);
  expect(setFilter).toHaveBeenCalledWith("segment-focus-outline", ["==", ["get", "segment_key"], "road-1"]);
  expect(setPaintProperty).toHaveBeenCalledWith("segment-exposure", "line-opacity", ["case", ["==", ["get", "segment_key"], "road-1"], 0.9, 0.2]);
  fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
  expect(setPaintProperty).toHaveBeenLastCalledWith("segment-expected", "line-opacity", 0.92);
});

test("server matched collisions persist across road modes and open details without losing focus", async () => {
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn((url: string, options?: RequestInit) => url.includes("/segments/road-1/collisions")
    ? Promise.resolve({ ok: true, headers: snapshotHeaders(), json: async () => matchedResponse() }) : originalFetch(url, options)));
  await startRoadFocus();
  await screen.findByRole("button", { name: /matched-only/ });
  expect(sourceData.get("collisions")?.features[0]?.properties?.collision_id).toBe("matched-only");
  expect(setLayoutProperty).toHaveBeenCalledWith("collisions", "visibility", "visible");
  fireEvent.click(screen.getByRole("button", { name: /matched-only/ }));
  expect(screen.getByRole("heading", { name: "matched-only" })).toBeInTheDocument();
  expect(screen.getByText("2024-02-03 · 12:30")).toBeInTheDocument();
  expect(screen.getByLabelText("Road segment")).toHaveValue("road-1");
  fireEvent.click(screen.getByRole("button", { name: "Fatal" }));
  expect(sourceData.get("collisions")?.features).toHaveLength(0);
  expect(screen.queryByRole("heading", { name: "matched-only" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "All" }));
  fireEvent.click(screen.getByRole("button", { name: "Screening" }));
  expect(screen.getByLabelText("Road segment")).toHaveValue("road-1");
  act(() => layerClicks.get("collisions")?.({ features: [{ properties: roadCollision }] }));
  expect(screen.getByRole("heading", { name: "matched-only" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Observed" }));
  expect(screen.getByLabelText("Road segment")).toHaveValue("road-1");
  expect(sourceData.get("collisions")?.features).toHaveLength(1);
});

test("clearing focus aborts a request and ignores a late response", async () => {
  let resolve!: (response: unknown) => void;
  let signal: AbortSignal | null | undefined;
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn((url: string, options?: RequestInit) => {
    if (!url.includes("/segments/road-1/collisions")) return originalFetch(url, options);
    signal = options?.signal;
    return new Promise((done) => { resolve = done; });
  }));
  await startRoadFocus();
  expect(screen.getByText("Loading matched collisions…")).toBeInTheDocument();
  expect(sourceData.get("collisions")?.features).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
  expect(signal?.aborted).toBe(true);
  await act(async () => resolve({ ok: true, headers: snapshotHeaders(), json: async () => matchedResponse() }));
  expect(screen.queryByRole("button", { name: /matched-only/ })).not.toBeInTheDocument();
  expect(sourceData.get("collisions")?.features).toHaveLength(0);
});

test("unavailable and failed matching never fall back to area points and allow retry", async () => {
  let fail = false;
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn((url: string, options?: RequestInit) => url.includes("/segments/road-1/collisions")
    ? fail ? Promise.reject(new Error("offline")) : Promise.resolve({ ok: true, headers: snapshotHeaders(), json: async () => ({ ...matchedResponse(), available: false, reason: "Provenance mismatch" }) })
    : originalFetch(url, options)));
  await startRoadFocus();
  expect(await screen.findByText(/Matched collision locations unavailable/)).toBeInTheDocument();
  expect(sourceData.get("collisions")?.features).toHaveLength(0);
  fail = true;
  fireEvent.click(screen.getByRole("button", { name: "Retry matched collisions" }));
  expect(await screen.findByText("Could not load matched collisions.")).toBeInTheDocument();
  expect(sourceData.get("collisions")?.features).toHaveLength(0);
  fail = false;
  fireEvent.click(screen.getByRole("button", { name: "Retry matched collisions" }));
  expect(await screen.findByText(/Matched collision locations unavailable/)).toBeInTheDocument();
});

test("switching roads hides previous points and ignores an out-of-order response", async () => {
  const pending = new Map<string, (response: unknown) => void>();
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith("segments")) {
      const response = await originalFetch(url, options);
      const network = await response.json();
      const first = network.features[0];
      return { ok: true, headers: snapshotHeaders(), json: async () => ({ ...network, features: [first, { ...first, properties: { ...first.properties, segment_key: "road-2", road_number: "A2" } }] }) };
    }
    const match = url.match(/\/segments\/(road-[12])\/collisions/);
    if (match) return new Promise((done) => pending.set(match[1], done));
    return originalFetch(url, options);
  }));
  await startRoadFocus();
  fireEvent.change(screen.getByLabelText("Road segment"), { target: { value: "road-2" } });
  await act(async () => pending.get("road-1")?.({ ok: true, headers: snapshotHeaders(), json: async () => matchedResponse() }));
  expect(screen.getByText("Loading matched collisions…")).toBeInTheDocument();
  expect(sourceData.get("collisions")?.features).toHaveLength(0);
  await act(async () => pending.get("road-2")?.({ ok: true, headers: snapshotHeaders(), json: async () => matchedResponse("road-2") }));
  expect(await screen.findByRole("button", { name: /matched-only/ })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Road segment"), { target: { value: "road-1" } });
  expect(screen.queryByRole("button", { name: /matched-only/ })).not.toBeInTheDocument();
  expect(sourceData.get("collisions")?.features).toHaveLength(0);
  fireEvent.change(screen.getByRole("textbox", { name: "Search road or segment" }), { target: { value: "no matching road" } });
  fireEvent.change(screen.getByRole("textbox", { name: "Search road or segment" }), { target: { value: "" } });
  expect(screen.getByLabelText("Road segment")).toHaveValue("");
});

test("mismatched response identity fails closed and a retry can recover", async () => {
  let key = "wrong-road";
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn((url: string, options?: RequestInit) => url.includes("/segments/road-1/collisions")
    ? Promise.resolve({ ok: true, headers: snapshotHeaders(), json: async () => matchedResponse(key) }) : originalFetch(url, options)));
  await startRoadFocus();
  expect(await screen.findByText("Could not load matched collisions.")).toBeInTheDocument();
  expect(sourceData.get("collisions")?.features).toHaveLength(0);
  key = "road-1";
  fireEvent.click(screen.getByRole("button", { name: "Retry matched collisions" }));
  expect(await screen.findByRole("button", { name: /matched-only/ })).toBeInTheDocument();
});

test.each(["collision_sha256", "network_sha256", "source_year"] as const)("stale %s payload fails closed before displaying markers", async (field) => {
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn((url: string, options?: RequestInit) => url.includes("/segments/road-1/collisions")
    ? Promise.resolve({ ok: true, headers: snapshotHeaders(), json: async () => ({ ...matchedResponse(), [field]: field === "source_year" ? 2023 : "stale-fingerprint" }) })
    : originalFetch(url, options)));
  await startRoadFocus();
  expect(await screen.findByText("Could not load matched collisions.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /matched-only/ })).not.toBeInTheDocument();
  expect(sourceData.get("collisions")?.features).toHaveLength(0);
});

test.each(["collisions", "summary", "segments", "network-summary"])("mixed initial %s snapshot rejects the essential group", async (endpoint) => {
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
    const response = await originalFetch(url, options);
    return new URL(url).pathname.endsWith(`/${endpoint}`) ? { ...response, headers: snapshotHeaders("different-snapshot") } : response;
  }));
  render(<App />);
  expect(await screen.findByText("Evidence snapshot mismatch. Reload to load a consistent dataset.")).toBeInTheDocument();
  await waitFor(() => expect(mapEvents.has("style.load")).toBe(true));
  act(() => mapEvents.get("style.load")?.());
  expect(sourceData.get("collisions")?.features).toHaveLength(0);
  expect(sourceData.get("segments")?.features).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Exposure" }));
  expect(screen.getByRole("button", { name: "Export evidence" })).toBeDisabled();
});

test.each([undefined, "", "   "])("missing or empty essential snapshot %s fails closed", async (token) => {
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
    const response = await originalFetch(url, options);
    return url.endsWith("segments") ? { ...response, headers: token === undefined ? new Headers() : snapshotHeaders(token) } : response;
  }));
  render(<App />);
  expect(await screen.findByText("Evidence snapshot mismatch. Reload to load a consistent dataset.")).toBeInTheDocument();
});

test.each(["different-snapshot", undefined])("geometry A cannot export or show points using unbound metadata B (%s)", async (token) => {
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
    if (url.includes("/segments/road-1/collisions")) return { ok: true, headers: snapshotHeaders(), json: async () => matchedResponse() };
    const response = await originalFetch(url, options);
    return url.endsWith("metadata") ? { ...response, headers: token === undefined ? new Headers() : snapshotHeaders(token) } : response;
  }));
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Exposure" }));
  await screen.findByRole("option", { name: "A1 · 1" });
  fireEvent.change(screen.getByLabelText("Road segment"), { target: { value: "road-1" } });
  expect(screen.getByRole("button", { name: "Export evidence" })).toBeDisabled();
  expect(await screen.findByText("Could not load matched collisions.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /matched-only/ })).not.toBeInTheDocument();
  expect(screen.getByText("Source metadata unavailable")).toBeInTheDocument();
});

const retrospectiveResponse = {
  available: true, year: 2024, records: [{ segment_key: "road-1", year: 2024, ksi_count: 2,
    prior_expected_ksi: 1, expected_ksi: 1.5, expected_ksi_std: 1.3, excess_ksi: 0.5 }],
};

test.each(["different-snapshot", undefined])("retrospective evidence must share the primary snapshot (%s)", async (token) => {
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn((url: string, options?: RequestInit) => url.includes("/empirical-bayes")
    ? Promise.resolve({ ok: true, headers: token === undefined ? new Headers() : snapshotHeaders(token), json: async () => retrospectiveResponse }) : originalFetch(url, options)));
  await startRoadFocus();
  expect(screen.getByRole("button", { name: "Retrospective" })).toBeDisabled();
  expect(sourceData.get("segments")?.features[0]?.properties?.expected_ksi).toBeUndefined();
});

test("bound retrospective evidence merges actual expected values", async () => {
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn((url: string, options?: RequestInit) => url.includes("/empirical-bayes")
    ? Promise.resolve({ ok: true, headers: snapshotHeaders(), json: async () => retrospectiveResponse }) : originalFetch(url, options)));
  await startRoadFocus();
  fireEvent.click(screen.getByRole("button", { name: "Retrospective" }));
  expect(screen.getByText("1.50")).toBeInTheDocument();
  expect(screen.getByText("1.30")).toBeInTheDocument();
});

test("missing metadata and failed retrospective data preserve bound Observed evidence", async () => {
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn((url: string, options?: RequestInit) => {
    if (url.endsWith("metadata") || url.includes("/empirical-bayes")) return Promise.reject(new Error("optional endpoint unavailable"));
    if (url.includes("/collisions?")) return Promise.resolve({ ok: true, headers: snapshotHeaders(), json: async () => [roadCollision] });
    return originalFetch(url, options);
  }));
  render(<App />);
  expect(await screen.findByText("1 visible / 12 collisions")).toBeInTheDocument();
  expect(screen.getByText("Source metadata unavailable")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retrospective" })).toBeDisabled();
});

test("Observed footer counts road points rather than the area collision list", async () => {
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn((url: string, options?: RequestInit) => url.includes("/segments/road-1/collisions")
    ? Promise.resolve({ ok: true, headers: snapshotHeaders(), json: async () => matchedResponse() }) : originalFetch(url, options)));
  await startRoadFocus();
  await screen.findByRole("button", { name: /matched-only/ });
  fireEvent.click(screen.getByRole("button", { name: "Observed" }));
  expect(screen.getByText("1 visible / 12 collisions")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Fatal" }));
  expect(screen.getByText("0 visible / 12 collisions")).toBeInTheDocument();
});

test.each(["loading", "unavailable", "error"])("Observed footer shows no road points while matching is %s", async (status) => {
  const originalFetch = fetch;
  vi.stubGlobal("fetch", vi.fn((url: string, options?: RequestInit) => {
    if (url.includes("/segments/road-1/collisions")) {
      if (status === "loading") return new Promise(() => {});
      if (status === "error") return Promise.reject(new Error("offline"));
      return Promise.resolve({ ok: true, headers: snapshotHeaders(), json: async () => ({ ...matchedResponse(), available: false, reason: "Unavailable", collisions: [] }) });
    }
    if (url.includes("/collisions?")) return Promise.resolve({ ok: true, headers: snapshotHeaders(), json: async () => [roadCollision] });
    return originalFetch(url, options);
  }));
  await startRoadFocus();
  fireEvent.click(screen.getByRole("button", { name: "Observed" }));
  expect(screen.getByText("0 visible / 12 collisions")).toBeInTheDocument();
});
