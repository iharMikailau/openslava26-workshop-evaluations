import { expect, test } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Evaluate" })).toBeVisible();
});

test("switches between the views", async ({ page }) => {
  const tabs = page.locator(".tabs");

  await tabs.getByRole("link", { name: "Matrix" }).click();
  await expect(page.getByRole("button", { name: "Run matrix" })).toBeVisible();

  await tabs.getByRole("link", { name: "Compare" }).click();
  await expect(page.getByText("Candidate A")).toBeVisible();

  await tabs.getByRole("link", { name: "Ensemble" }).click();
  await expect(page.getByText("Panel of judges")).toBeVisible();

  await tabs.getByRole("link", { name: "Judge reliability" }).click();
  await expect(page.getByRole("button", { name: "Measure agreement" })).toBeVisible();

  await tabs.getByRole("link", { name: "Playground" }).click();
  await expect(page.getByRole("button", { name: "Evaluate" })).toBeVisible();
});

for (const width of [1440, 768]) {
  test(`spaces screen sections and actions at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });

    for (const name of [
      "Playground", "Matrix", "Compare", "Ensemble", "Judge reliability", "Datasets", "Models",
    ]) {
      await page.locator(".tabs").getByRole("link", { name, exact: true }).click();
      const column = page.locator(".split > div").first();
      await expect(column.locator(":scope > .card").first()).toBeVisible();

      // Measure rendered gaps, including the button after the final setup card.
      const gaps = await column.evaluate((element) => {
        const children = Array.from(element.children);
        return children.flatMap((child, index) => {
          const previous = children[index - 1];
          if (!previous?.classList.contains("card")) return [];
          return [child.getBoundingClientRect().top - previous.getBoundingClientRect().bottom];
        });
      });
      for (const gap of gaps) {
        expect(gap, `${name}: gap between setup sections or action`).toBeCloseTo(16, 0);
      }
    }
  });
}

test("toggles light and dark theme", async ({ page }) => {
  const html = page.locator("html");
  const before = await html.getAttribute("data-theme");
  await page.getByTitle("Toggle light and dark").click();
  await expect(html).not.toHaveAttribute("data-theme", before ?? "");
});

test("loads the catalogue of mechanisms", async ({ page }) => {
  await expect(page.locator(".check__label", { hasText: "Exact match" })).toBeVisible();
  await expect(page.locator(".check__label", { hasText: "LLM as judge" })).toBeVisible();
  await expect(page.locator(".check__label", { hasText: "BLEU" })).toBeVisible();
});
