import { expect, test } from "./fixtures";

const pages = ["Playground", "Matrix", "Compare", "Ensemble", "Judge reliability", "Decision judges", "Datasets", "Models"];

for (const theme of ["light", "dark"] as const) {
  test(`theme, navigation and responsive containment in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      for (const name of pages) {
        const link = page.getByRole("link", { name, exact: true });
        await link.click();
        await expect(link).toHaveAttribute("aria-current", "page");
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name} at ${width}`).toBe(true);
        if (width === 390) {
          expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44);
          const gaps = await page.locator(".split > div").first().evaluateAll(columns => columns.flatMap(column => Array.from(column.children).flatMap((child, i, children) => i > 0 && children[i - 1].classList.contains("card") ? [child.getBoundingClientRect().top - children[i - 1].getBoundingClientRect().bottom] : [])));
          for (const gap of gaps) expect(gap).toBeCloseTo(16, 0);
        }
      }
      if (width === 390) expect((await page.getByTitle("Toggle light and dark").boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
  });
}

test("toggle preserves form and result; keyboard focus and fallback fonts remain usable", async ({ page }) => {
  await page.goto("/playground");
  await page.getByRole("button", { name: "Custom" }).click();
  await page.getByLabel("Prompt").fill("Say the word positive.");
  await page.getByLabel("Reference answer (optional)").fill("positive");
  await page.locator(".check", { hasText: "Exact match" }).locator("input").check();
  const evaluate = page.getByRole("button", { name: "Evaluate", exact: true });
  await evaluate.hover();
  expect(await evaluate.evaluate(el => getComputedStyle(el).backgroundColor)).toBe(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() === "#0e7490" ? "rgb(14, 116, 144)" : "rgb(34, 211, 238)"));
  await evaluate.click();
  await expect(page.getByText("Model response", { exact: true })).toBeVisible();
  const response = await page.locator(".response").last().innerText();
  await page.getByTitle("Toggle light and dark").click();
  await expect(page.locator(".response").last()).toHaveText(response);
  await expect(page.getByLabel("Prompt")).toHaveValue("Say the word positive.");
  await page.addStyleTag({ content: ':root { --font-sans: system-ui, sans-serif; --font-mono: monospace; }' });
  await expect(page.getByText("Model response", { exact: true })).toBeVisible();
  await page.keyboard.press("Tab");
  expect(await page.locator(":focus").evaluate(el => getComputedStyle(el).outlineStyle)).not.toBe("none");
});

test("disabled and reduced motion retain textual feedback", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/decision-judges");
  await expect(page.getByRole("button", { name: "Generate answer" })).toBeDisabled();
  expect(await page.locator(".btn").first().evaluate(el => getComputedStyle(el).transitionDuration)).toBe("0s");
  await page.goto("/playground");
  await page.getByRole("button", { name: "Custom" }).click();
  await page.getByLabel("Prompt").fill("Say positive");
  await page.getByLabel("Reference answer (optional)").fill("positive");
  await page.locator(".check", { hasText: "Exact match" }).locator("input").check();
  await page.route("**/api/evaluate", async route => { await new Promise(resolve => setTimeout(resolve, 500)); await route.continue(); });
  await page.getByRole("button", { name: "Evaluate", exact: true }).click();
  await expect(page.getByRole("button", { name: "Evaluating…" })).toBeDisabled();
  await expect(page.getByText("Model response", { exact: true })).toBeVisible();
});

for (const theme of ["light", "dark"] as const) {
  test(`populated wide results remain contained in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/matrix");
    await page.getByLabel("Category").selectOption("sentiment_classification");
    await page.getByRole("button", { name: "Run matrix" }).click();
    await expect(page.getByText(/Results — completed/)).toBeVisible({ timeout: 30000 });
    await expect(page.locator(".gate-verdict")).toContainText(/BLOCKED|PASS/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("link", { name: "Decision judges" }).click();
    await page.getByLabel("Prompt", { exact: true }).fill("A long question " + "identifier".repeat(50));
    await page.getByRole("textbox", { name: "Answer", exact: true }).fill("Blue");
    await page.getByRole("button", { name: "Run judgments" }).click();
    await expect(page.getByText("completed: 1/1 judgments.")).toBeVisible();
    await expect(page.getByText(/Simulated · yes probability/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await page.locator(".decision-lab__results table").evaluate(el => getComputedStyle(el).overflowX)).toBe("auto");
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download results" }).click();
    await page.getByLabel("Import inputs or results").setInputFiles((await (await download).path())!);
    await expect(page.getByText("Results (imported, read-only)")).toBeVisible();
  });
}

test("rendered semantic colors meet contrast targets", async ({ page }) => {
  for (const theme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/playground");
    const ratios = await page.evaluate(() => {
      const parent = document.createElement("div");
      parent.innerHTML = '<div class="card"><span class="muted">Text</span><button class="btn btn--primary">Action</button><span class="chip chip--pass">Pass</span><span class="chip chip--partial">Partial</span><span class="chip chip--fail">Fail</span><input type="text"></div>';
      document.body.append(parent);
      const color = (selector: string, property: "color" | "backgroundColor" | "borderTopColor") => getComputedStyle(parent.querySelector(selector)!).getPropertyValue(property === "backgroundColor" ? "background-color" : property === "borderTopColor" ? "border-top-color" : "color");
      const luminance = (rgb: string) => {
        const channels = rgb.match(/\d+/g)!.slice(0, 3).map(Number).map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
      };
      const contrast = (a: string, b: string) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
      const pair = (sel: string) => contrast(color(sel, "color"), color(sel, "backgroundColor"));
      const values = { text: contrast(color(".muted", "color"), color(".card", "backgroundColor")), action: pair(".btn"), pass: pair(".chip--pass"), partial: pair(".chip--partial"), fail: pair(".chip--fail"), control: contrast(color("input", "borderTopColor"), color("input", "backgroundColor")) };
      parent.remove(); return values;
    });
    console.log(`${theme} rendered contrast: ${JSON.stringify(ratios)}`);
    for (const [name, ratio] of Object.entries(ratios)) expect(ratio, `${theme} ${name}`).toBeGreaterThanOrEqual(name === "control" ? 3 : 4.5);
  }
});
