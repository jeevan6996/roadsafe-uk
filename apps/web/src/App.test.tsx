import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";

vi.mock("maplibre-gl", () => {
  class MockMap {
    addControl = vi.fn();
    remove = vi.fn();
    isStyleLoaded = vi.fn(() => false);
    once = vi.fn();
    getSource = vi.fn();
  }

  class MockControl {}

  return {
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
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
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
                  ? { type: "FeatureCollection", features: [] }
                  : [],
          ),
      }),
    ),
  );
});

test("renders the evidence workspace and responsible-use caveat", async () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "Network evidence" })).toBeInTheDocument();
  expect(await screen.findByText("Police-reported personal-injury collisions. Observed concentration is not exposure-adjusted risk.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Expected" })).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Exposure" }));
  expect(screen.getByRole("heading", { name: "Major-road network" })).toBeInTheDocument();
  expect(screen.getByText("AADF link estimates are descriptive exposure, not expected collision risk.")).toBeInTheDocument();
});
