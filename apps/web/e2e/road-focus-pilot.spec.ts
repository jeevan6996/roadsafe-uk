import { expect, test } from "@playwright/test";
import type { Metadata, SegmentFeature } from "../src/App";
import type { SegmentCollisions } from "../src/roadCollisions";

const api = process.env.ROADSAFE_API_URL ?? "http://127.0.0.1:8000/api/v1";

for (const width of [1440, 390, 320]) {
  test(`verified pilot road focus and collision evidence at ${width}px`, async ({ page, request }, info) => {
    const errors: string[] = [];
    let tiles = 0;
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => {
      if (response.url().includes("tile.openstreetmap.org/") && response.ok()) tiles += 1;
    });
    await page.setViewportSize({ width, height: 900 });
    const releaseResponse = await request.get(`${api}/release`);
    expect(releaseResponse.ok()).toBeTruthy();
    const release = await releaseResponse.json();
    expect(release.verified_bundle).toBe(true);
    expect(release.bundle.profile).toBe("pilot");
    const metadataResponse = await request.get(`${api}/metadata`);
    expect(metadataResponse.ok()).toBeTruthy();
    const metadata = await metadataResponse.json() as Metadata;
    const networkResponse = await request.get(`${api}/segments`);
    expect(networkResponse.ok()).toBeTruthy();
    expect(networkResponse.headers()["x-roadsafe-snapshot"]).toBe(metadataResponse.headers()["x-roadsafe-snapshot"]);
    const network = await networkResponse.json() as { features: SegmentFeature[] };
    expect(network.features).toHaveLength(256);
    const ordered = [...network.features].sort((a, b) => a.properties.segment_key.localeCompare(b.properties.segment_key));
    // Choose by identity and count availability, not by risk ranking or model outcome.
    const road = ordered.find((feature) => feature.properties.collision_count > 0)!;
    const empty = ordered.find((feature) => feature.properties.collision_count === 0)!;
    expect(road).toBeDefined();
    expect(empty).toBeDefined();
    const pointsResponse = await request.get(`${api}/segments/${encodeURIComponent(road.properties.segment_key)}/collisions`);
    expect(pointsResponse.ok()).toBeTruthy();
    const evidence = await pointsResponse.json() as SegmentCollisions;
    expect(evidence.available).toBe(true);
    expect(evidence.collision_sha256).toBe(metadata.collision_sha256);
    expect(evidence.network_sha256).toBe(metadata.network_sha256);
    expect(evidence.collisions).toHaveLength(road.properties.collision_count);
    expect(evidence.collisions.filter((point) => point.severity <= 2)).toHaveLength(road.properties.ksi_count);

    await page.goto("/");
    await page.getByRole("button", { name: "Exposure", exact: true }).click();
    const roads = page.getByRole("combobox", { name: "Road segment" });
    await roads.selectOption(road.properties.segment_key);
    const matches = page.getByRole("region", { name: "Matched road collisions" });
    await expect(matches.getByText(`${evidence.collisions.length} of ${evidence.collisions.length} matched collisions`)).toBeVisible();
    const first = evidence.collisions[0];
    const entry = matches.getByRole("button").filter({ hasText: first.collision_id });
    await entry.focus();
    await page.keyboard.press("Enter");
    await expect(matches.getByRole("heading", { name: first.collision_id, exact: true })).toBeVisible();
    await expect(roads).toHaveValue(road.properties.segment_key);
    await expect(page.getByRole("region", { name: "Collision map" })).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
    await expect.poll(() => tiles).toBeGreaterThan(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    await page.screenshot({ path: info.outputPath(`focused-road-pilot-${width}.png`), fullPage: true });

    await matches.getByRole("button", { name: "Close collision details" }).click();
    for (const mode of ["Screening", "Retrospective", "Observed"]) {
      await page.getByRole("button", { name: mode, exact: true }).click();
      await expect(roads).toHaveValue(road.properties.segment_key);
      await expect(matches.getByText(`${evidence.collisions.length} of ${evidence.collisions.length} matched collisions`)).toBeVisible();
    }
    await roads.selectOption(empty.properties.segment_key);
    await expect(matches.getByText("0 of 0 matched collisions")).toBeVisible();
    await expect(matches.getByRole("button").filter({ hasText: first.collision_id })).toHaveCount(0);
    await page.getByRole("button", { name: "Clear selection" }).click();
    await expect(matches).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}
