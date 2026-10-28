import { expect, test, type Locator, type Page } from "@playwright/test";

async function tabTo(page: Page, target: Locator) {
  await expect(target).toBeVisible();
  for (let step = 0; step < 24; step += 1) {
    if (await target.evaluate((element) => element === document.activeElement))
      return;
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
}

for (const width of [1440, 390, 320]) {
  test(`search has a visible keyboard focus indicator at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const search = page.getByRole("textbox", { name: "Search collision ID" });
    await tabTo(page, search);
    await expect(search).toBeFocused();
    expect(
      await search.evaluate((element) => element.matches(":focus-visible")),
    ).toBe(true);
    const outline = await search.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        style: style.outlineStyle,
        width: parseFloat(style.outlineWidth),
      };
    });
    expect(outline.style).not.toBe("none");
    expect(outline.width).toBeGreaterThanOrEqual(2);
  });
}

for (const width of [1440, 320]) {
  test(`keyboard-only road investigation exports evidence and clears selection at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/");
    await expect(page.getByText("1791", { exact: true })).toBeVisible({
      timeout: 15_000,
    });
    const retrospective = page.getByRole("button", {
      name: "Retrospective",
      exact: true,
    });
    await expect(retrospective).toBeEnabled();

    const observed = page.getByRole("button", {
      name: "Observed",
      exact: true,
    });
    await tabTo(page, observed);
    await expect(observed).toHaveAttribute("aria-pressed", "true");
    await page.keyboard.press("Tab");
    const exposure = page.getByRole("button", {
      name: "Exposure",
      exact: true,
    });
    await expect(exposure).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(exposure).toHaveAttribute("aria-pressed", "true");
    await expect(observed).toHaveAttribute("aria-pressed", "false");

    const search = page.getByRole("textbox", {
      name: "Search road or segment",
    });
    await tabTo(page, search);
    await page.keyboard.type("no-such-road-xyz");
    const roads = page.getByRole("combobox", { name: "Road segment" });
    await expect(roads).toHaveText("No matching segments");
    await page.keyboard.press("ControlOrMeta+A");
    await page.keyboard.press("Backspace");
    await expect(roads.locator("option")).toHaveCount(257);

    await tabTo(page, roads);
    await page.keyboard.press("m");
    await page.keyboard.press("Tab");
    await expect(roads).not.toHaveValue("");
    const selected = await roads.inputValue();
    await tabTo(page, retrospective);
    await page.keyboard.press("Space");
    await expect(retrospective).toHaveAttribute("aria-pressed", "true");
    await expect(roads).toHaveValue(selected);

    const exportButton = page.getByRole("button", { name: "Export evidence" });
    await tabTo(page, exportButton);
    const downloaded = page.waitForEvent("download");
    await page.keyboard.press("Enter");
    const download = await downloaded;
    const stream = await download.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream) chunks.push(chunk);
    const evidence = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    expect(evidence.segment.key).toBe(selected);
    expect(evidence.retrospective.method).toBe("Poisson-gamma Empirical Bayes");
    await expect(page.getByRole("status")).toHaveText("Evidence exported");

    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("button", { name: "Clear selection" }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(roads).toHaveValue("");
    await expect(exportButton).toBeDisabled();
    await tabTo(page, page.locator(".source-details > summary"));
    await page.keyboard.press("Enter");
    await expect(page.locator(".source-details")).toHaveAttribute("open", "");
    expect(errors).toEqual([]);
  });
}
