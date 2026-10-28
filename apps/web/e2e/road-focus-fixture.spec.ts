import { expect, test, type Page } from "@playwright/test";
import type { SegmentFeature } from "../src/App";
import type { Collision, SegmentCollisions } from "../src/roadCollisions";

// Synthetic API fixtures exercise the real renderer, not the pilot's matching evidence.
const road: SegmentFeature = {
  type: "Feature", geometry: { type: "LineString", coordinates: [[-1.76, 53.8], [-1.74, 53.8]] },
  properties: {
    segment_key: "fixture-road-1", segment_id: "fixture-link-1", count_point_id: 1,
    road_number: "A1", source_year: 2024, all_motor_vehicles: 15000,
    estimation_method: "Counted", estimation_method_detailed: "Fixture count",
    link_length_km: 1.3, collision_count: 3, ksi_count: 2, collision_rate_per_100m_vehicle_km: 5,
  },
};
const points: Collision[] = [1, 2, 3].map((severity) => ({
  collision_id: `fixture-collision-${severity}`, severity,
  severity_label: severity === 1 ? "Fatal" : severity === 2 ? "Serious" : "Slight",
  longitude: -1.75 + (severity - 2) * 0.006, latitude: 53.8,
  date: "2024-02-03", time: "12:30", casualties: severity, vehicles: 2,
  speed_limit: 30, local_authority_code: "fixture-authority",
}));
const response: SegmentCollisions = {
  segment_key: road.properties.segment_key, source_year: 2024, available: true, reason: null,
  collisions: points, collision_sha256: "a".repeat(64), network_sha256: "b".repeat(64),
  matching: { method: "nearest_unambiguous_bng", max_distance_m: 50, ambiguity_margin_m: 5 },
};

async function fixtureApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith("/segments/fixture-road-1/collisions") ? response
      : path.endsWith("/segments/fixture-road-2/collisions") ? { ...response, segment_key: "fixture-road-2", available: false, reason: "Fixture evidence unavailable", collisions: [] }
      : path.endsWith("/segments") ? { type: "FeatureCollection", features: [road, {
        ...road, geometry: { type: "LineString", coordinates: [[-1.76, 53.803], [-1.74, 53.803]] },
        properties: { ...road.properties, segment_key: "fixture-road-2", segment_id: "fixture-link-2", road_number: "A2", count_point_id: 2 },
      }] }
      : path.endsWith("/metadata") ? { scope: "Synthetic road focus browser fixture", status: "fixture", licence: "OGL v3.0", source_year: 2024, collision_sha256: response.collision_sha256, network_sha256: response.network_sha256 }
      : path.endsWith("/network-summary") ? { segments: 2, counted_exposure: 2, estimated_exposure: 0, matched_collisions: 3, matched_ksi: 2 }
      : path.endsWith("/empirical-bayes") ? { available: true, year: 2024, records: [{ segment_key: "fixture-road-1", year: 2024, ksi_count: 2, prior_expected_ksi: 1, expected_ksi: 1.5, expected_ksi_std: 1.3, excess_ksi: 0.5 }] }
      : path.endsWith("/summary") ? { collisions: 3, killed_or_seriously_injured: 2, casualties: 6, fatal: 1, serious: 1, slight: 1 }
      : points;
    await route.fulfill({ json: body, headers: {
      "X-RoadSafe-Snapshot": "fixture-primary",
      "Access-Control-Expose-Headers": "X-RoadSafe-Snapshot",
    } });
  });
}

for (const width of [1440, 390, 320]) {
  test(`fixture road focus, real map point click and keyboard controls at ${width}px`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await fixtureApi(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Exposure", exact: true }).click();
    const roads = page.getByRole("combobox", { name: "Road segment" });
    await expect(roads.locator('option[value="fixture-road-1"]')).toBeAttached();
    await roads.selectOption("fixture-road-1");
    await expect(page.getByText("3 of 3 matched collisions")).toBeVisible();
    const map = page.getByRole("region", { name: "Collision map" });
    await expect(map).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
    // fitBounds places the middle collision at the canvas centre.
    const canvas = page.locator(".maplibregl-canvas");
    const bounds = await canvas.boundingBox();
    expect(bounds).not.toBeNull();
    await canvas.click({ position: { x: bounds!.width / 2, y: bounds!.height / 2 } });
    await expect(page.getByRole("heading", { name: "fixture-collision-2", exact: true })).toBeVisible();
    await expect(roads).toHaveValue("fixture-road-1");
    await page.screenshot({ path: info.outputPath(`fixture-selected-${width}.png`), fullPage: true });
    await page.getByRole("button", { name: "Close collision details" }).click();
    for (const mode of ["Screening", "Retrospective", "Observed"]) {
      await page.getByRole("button", { name: mode, exact: true }).click();
      await expect(roads).toHaveValue("fixture-road-1");
      await expect(page.getByText("3 of 3 matched collisions")).toBeVisible();
      if (mode === "Retrospective") {
        await expect(page.getByText("Expected KSI", { exact: true }).locator("..")).toHaveText("Expected KSI1.50");
        await expect(page.getByText("Standard deviation proxy", { exact: true }).locator("..")).toHaveText("Standard deviation proxy1.30");
      }
    }
    const fatal = page.getByRole("button", { name: "Fatal", exact: true });
    await fatal.focus();
    await page.keyboard.press("Enter");
    await expect(fatal).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("1 of 3 matched collisions")).toBeVisible();
    await expect(page.locator(".statusbar")).toContainText("1 visible / 3 collisions");
    const collision = page.getByRole("button", { name: /fixture-collision-1/ });
    await collision.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "fixture-collision-1", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    const clear = page.getByRole("button", { name: "Clear selection" });
    await clear.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "Matched road collisions" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Fatal", exact: true })).toHaveAttribute("aria-pressed", "true");
    expect(errors).toEqual([]);
  });
}

test("fixture unavailable road replaces points and failed request can retry", async ({ page }) => {
  await fixtureApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Exposure", exact: true }).click();
  const roads = page.getByRole("combobox", { name: "Road segment" });
  await roads.selectOption("fixture-road-1");
  await expect(page.getByText("3 of 3 matched collisions")).toBeVisible();
  await roads.selectOption("fixture-road-2");
  await expect(page.getByText(/Matched collision locations unavailable/)).toBeVisible();
  await expect(page.getByRole("button", { name: /fixture-collision/ })).toHaveCount(0);
  await page.route("**/segments/fixture-road-2/collisions", (route) => route.fulfill({ status: 503, body: "unavailable" }));
  await page.getByRole("button", { name: "Retry matched collisions" }).click();
  await expect(page.getByText("Could not load matched collisions.")).toBeVisible();
  await expect(page.getByRole("button", { name: /fixture-collision/ })).toHaveCount(0);
  await page.unroute("**/segments/fixture-road-2/collisions");
  await page.getByRole("button", { name: "Retry matched collisions" }).click();
  await expect(page.getByText(/Matched collision locations unavailable/)).toBeVisible();
});
