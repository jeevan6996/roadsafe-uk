import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { parseArgs } from "node:util";
import { chromium, expect } from "@playwright/test";

const { values } = parseArgs({
  options: {
    output: { type: "string" },
    url: { type: "string", default: "http://127.0.0.1:5173" },
    api: { type: "string", default: "http://127.0.0.1:8000/api/v1/" },
    channel: { type: "string" },
    "hold-ms": { type: "string", default: "10000" },
  },
});
assert(values.output, "Provide a fresh directory with --output.");
const holdMs = Number(values["hold-ms"]);
assert(Number.isInteger(holdMs) && holdMs >= 0 && holdMs <= 30_000, "Invalid --hold-ms.");
const api = new URL(values.api);
if (!api.pathname.endsWith("/")) api.pathname += "/";
const output = resolve(values.output);
await mkdir(dirname(output), { recursive: true });
await mkdir(output);

const browser = await chromium.launch({
  channel: values.channel,
  timeout: 30_000,
  args: ["--enable-unsafe-swiftshader"],
});
let context;

try {
  context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: output, size: { width: 1440, height: 900 } },
  });
  context.setDefaultTimeout(10_000);
  context.setDefaultNavigationTimeout(30_000);
  const page = await context.newPage();
  if (values.channel === "chrome" && process.platform === "darwin") {
    // Enlarge Chrome's backing window so video includes the emulated viewport's footer.
    const session = await context.newCDPSession(page);
    try {
      const { windowId } = await session.send("Browser.getWindowForTarget");
      await session.send("Browser.setWindowBounds", { windowId, bounds: { width: 1440, height: 1000 } });
    } finally {
      await session.detach();
    }
  }
  const video = page.video();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const tiles = new Set();
  page.on("response", response => {
    if (response.url().includes("tile.openstreetmap.org/") && response.ok()) tiles.add(response.url());
  });
  async function getJson(endpoint) {
    const response = await context.request.get(new URL(endpoint, api).href, { timeout: 15_000 });
    assert(response.ok(), `${endpoint}: HTTP ${response.status()}`);
    return response.json();
  }
  const release = await getJson("release");
  assert.equal(release.verified_bundle, true, "A verified serving bundle is required.");
  assert.equal(release.bundle.profile, "pilot");
  assert.equal(release.bundle.year, 2024);
  assert.equal(release.bundle.records, 1791);
  assert.equal(release.bundle.segments, 256);
  const metadata = await getJson("metadata");
  const network = await getJson("segments");
  assert.equal(network.features.length, 256);
  const feature = [...network.features].sort((a, b) =>
    a.properties.segment_key.localeCompare(b.properties.segment_key),
  )[0];
  const map = page.getByRole("region", { name: "Collision map" });
  async function ready() {
    await expect(map).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
    await expect.poll(() => tiles.size).toBeGreaterThan(0);
  }
  // These pauses are for reading the recording, not application readiness.
  const hold = () => page.waitForTimeout(holdMs);

  await page.goto(values.url);
  await expect(page.getByText("1791", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Retrospective", exact: true })).toBeEnabled();
  await ready();
  const assetURLs = await page.locator('script[type="module"][src], link[rel="stylesheet"][href]').evaluateAll(elements =>
    elements.map(element => element instanceof HTMLScriptElement ? element.src : element.href),
  );
  assert(assetURLs.length > 0, "No production entry assets found.");
  const frontendAssets = {};
  for (const url of assetURLs) {
    assert(new URL(url).pathname.startsWith("/assets/"), "Use the production preview, not the dev server.");
    const response = await context.request.get(url, { timeout: 15_000 });
    assert(response.ok(), `Cannot fingerprint ${url}`);
    frontendAssets[url] = createHash("sha256").update(await response.body()).digest("hex");
  }
  await page.screenshot({ path: join(output, "observed.png") });
  await hold();
  await page.getByRole("button", { name: "Fatal", exact: true }).click();
  await ready();
  await hold();
  await page.getByRole("button", { name: "Exposure", exact: true }).click();
  await ready();
  await hold();
  await page.getByRole("textbox", { name: "Search road or segment" }).fill(feature.properties.road_number);
  await page.getByRole("combobox", { name: "Road segment" }).selectOption(feature.properties.segment_key);
  await ready();
  await page.screenshot({ path: join(output, "selected.png") });
  await hold();
  await page.getByRole("button", { name: "Screening", exact: true }).click();
  await ready();
  await hold();
  await page.getByRole("button", { name: "Retrospective", exact: true }).click();
  await ready();
  await page.screenshot({ path: join(output, "retrospective.png") });
  await hold();

  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 10_000 }),
    page.getByRole("button", { name: "Export evidence" }).click(),
  ]);
  const evidencePath = join(output, "selected-evidence.json");
  await download.saveAs(evidencePath);
  const evidence = JSON.parse(await readFile(evidencePath, "utf8"));
  assert.equal(evidence.segment.key, feature.properties.segment_key);
  assert.deepEqual(evidence.segment.geometry, feature.geometry);
  assert.deepEqual(evidence.provenance, metadata);
  assert.equal(evidence.retrospective.method, "Poisson-gamma Empirical Bayes");
  await expect(page.getByRole("status")).toHaveText("Evidence exported");
  await hold();
  await page.locator(".source-details > summary").click();
  await page.screenshot({ path: join(output, "source-and-scope.png") });
  await hold();
  assert.deepEqual(errors, [], "Application errors occurred during capture.");
  await context.close();
  await rename(await video.path(), join(output, "roadsafe-pilot.webm"));

  const artifacts = {};
  for (const name of ["roadsafe-pilot.webm", "observed.png", "selected.png", "retrospective.png", "source-and-scope.png", "selected-evidence.json"]) {
    artifacts[name] = createHash("sha256").update(await readFile(join(output, name))).digest("hex");
  }
  await writeFile(join(output, "capture.json"), JSON.stringify({
    captured_at: new Date().toISOString(),
    status: "capture-complete-pending-visual-review",
    capture_kind: holdMs === 0 ? "smoke" : "presentation",
    presentation_hold_ms: holdMs,
    published_release: false,
    web_url: values.url,
    viewport: { width: 1440, height: 900 },
    browser: browser.version(),
    channel: values.channel ?? "bundled Chromium",
    release,
    segment_key: feature.properties.segment_key,
    tile_responses: tiles.size,
    page_errors: errors,
    frontend_assets: frontendAssets,
    artifacts,
  }, null, 2) + "\n", { flag: "wx" });
  console.log(`Capture complete; encoded-frame visual review is pending: ${output}`);
} finally {
  try {
    await context?.close();
  } finally {
    await browser.close();
  }
}
