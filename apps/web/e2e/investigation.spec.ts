import { expect, test } from "@playwright/test";
import type { Metadata, SegmentFeature } from "../src/App";

const api = process.env.ROADSAFE_API_URL ?? "http://127.0.0.1:8000/api/v1";

test("real pilot investigation and canonical evidence download", async ({ page, request }, info) => {
  const errors: string[] = [];
  const tiles: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("response", response => {
    if (response.url().includes("tile.openstreetmap.org/") && response.ok()) tiles.push(response.url());
  });
  const metadataResponse = await request.get(`${api}/metadata`);
  expect(metadataResponse.ok()).toBeTruthy();
  const metadata = await metadataResponse.json() as Metadata & { records: number };
  expect(metadata.records).toBe(1791);
  expect(metadata.scope).toBe("West Yorkshire 2024 pilot");
  const networkResponse = await request.get(`${api}/segments`);
  expect(networkResponse.ok()).toBeTruthy();
  const network = await networkResponse.json() as { features: SegmentFeature[] };
  expect(network.features).toHaveLength(256);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "RoadSafe UK", exact: true })).toBeVisible();
  await expect(page.getByText("1791", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retrospective", exact: true })).toBeEnabled();
  await expect.poll(() => tiles.length).toBeGreaterThan(0);
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  await expect(page.getByRole("region", { name: "Collision map" })).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
  await page.screenshot({ path: info.outputPath("observed-desktop.png") });

  await page.getByRole("button", { name: "Fatal", exact: true }).click();
  await expect(page.getByRole("button", { name: "Fatal", exact: true })).toHaveClass("selected");
  await page.getByRole("button", { name: "Exposure", exact: true }).click();
  await page.getByRole("textbox", { name: "Search road or segment" }).fill("no-such-road-xyz");
  await expect(page.getByRole("combobox", { name: "Road segment" })).toHaveText("No matching segments");
  await page.getByRole("textbox", { name: "Search road or segment" }).fill("");
  // Stable ordering avoids choosing a road based on a dramatic model outcome.
  const feature = [...network.features].sort((a, b) => a.properties.segment_key.localeCompare(b.properties.segment_key))[0];
  await page.getByRole("combobox", { name: "Road segment" }).selectOption(feature.properties.segment_key);
  await expect(page.getByRole("button", { name: "Export evidence" })).toBeEnabled();
  await expect(page.getByRole("heading", { name: feature.properties.road_number, exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Collision map" })).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
  await page.screenshot({ path: info.outputPath("selected-desktop.png") });
  await page.getByRole("button", { name: "Screening", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Road segment" })).toHaveValue(feature.properties.segment_key);
  await page.getByRole("button", { name: "Retrospective", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Road segment" })).toHaveValue(feature.properties.segment_key);
  await expect(page.getByRole("region", { name: "Collision map" })).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
  await page.screenshot({ path: info.outputPath("retrospective-desktop.png") });

  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export evidence" }).click();
  const download = await downloaded;
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const exported = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  expect(exported.segment.geometry).toEqual(feature.geometry);
  expect(exported.segment.key).toBe(feature.properties.segment_key);
  expect(exported.observed.matched_collisions).toBe(feature.properties.collision_count);
  expect(exported.observed.matched_ksi_collisions).toBe(feature.properties.ksi_count);
  expect(exported.provenance).toEqual(metadata);
  expect(exported.retrospective.method).toBe("Poisson-gamma Empirical Bayes");
  await download.saveAs(info.outputPath("selected-evidence.json"));
  await page.getByRole("button", { name: "Clear selection" }).click();
  await expect(page.getByRole("button", { name: "Export evidence" })).toBeDisabled();
  expect(errors).toEqual([]);
});

for (const width of [390, 320]) {
  test(`mobile ${width}px has accessible controls without page overflow`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Retrospective", exact: true })).toBeEnabled();
    await expect(page.getByText("1791", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    await expect(page.getByRole("region", { name: "Collision map" })).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
    await page.screenshot({ path: info.outputPath(`observed-mobile-${width}.png`), fullPage: true });
    await page.getByRole("button", { name: "Exposure", exact: true }).click();
    await page.getByRole("combobox", { name: "Road segment" }).selectOption({ index: 1 });
    await page.getByRole("button", { name: "Retrospective", exact: true }).click();
    await expect(page.getByRole("button", { name: "Export evidence" })).toBeEnabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    await expect(page.getByRole("region", { name: "Collision map" })).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
    await page.screenshot({ path: info.outputPath(`retrospective-mobile-${width}.png`), fullPage: true });
  });
}
