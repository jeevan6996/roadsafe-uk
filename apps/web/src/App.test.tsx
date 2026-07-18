import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
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
        json: () =>
          Promise.resolve(
            url.endsWith("summary")
              ? { collisions: 12, killed_or_seriously_injured: 3, casualties: 17, fatal: 0, serious: 3, slight: 9 }
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
});
