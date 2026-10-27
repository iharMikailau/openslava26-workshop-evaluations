import { expect, test } from "./fixtures";

const pages = [
  ["/playground", "Playground", "Evaluate"], ["/matrix", "Matrix", "Run matrix"],
  ["/compare", "Compare", "Candidate A"], ["/ensemble", "Ensemble", "Panel of judges"],
  ["/judge-reliability", "Judge reliability", "Measure agreement"],
  ["/decision-judges", "Decision judges", "Run judgments"],
  ["/datasets", "Datasets", "Add case"], ["/models", "Models", "Add model"],
] as const;

for (const [path, label, content] of pages) {
  test(`direct entry and refresh: ${label}`, async ({ page }) => {
    const actions: string[] = [];
    page.on("request", request => { if (request.method() !== "GET" && request.url().includes("/api/")) actions.push(request.url()); });
    await page.goto(path);
    const nav = page.locator(".tabs").getByRole("link", { name: label, exact: true });
    await expect(nav).toHaveAttribute("href", path);
    for (let i = 0; i < 2; i++) {
      await expect(page).toHaveURL(new RegExp(`${path}$`));
      await expect(nav).toHaveAttribute("aria-current", "page");
      await expect(page.getByText(content, { exact: true }).first()).toBeVisible();
      if (!i) await page.reload();
    }
    expect(actions).toEqual([]);
  });
}

test("history, native links and theme", async ({ page, context }) => {
  await page.goto("/matrix");
  await page.goto("/");
  await expect(page).toHaveURL(/\/playground$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/matrix$/);
  await page.goForward();
  await expect(page).toHaveURL(/\/playground$/);
  await page.getByTitle("Toggle light and dark").click();
  const theme = await page.locator("html").getAttribute("data-theme");
  await page.evaluate(() => { (window as unknown as { marker: number }).marker = 42; });
  const nav = page.locator(".tabs");
  await nav.getByRole("link", { name: "Matrix", exact: true }).click();
  await nav.getByRole("link", { name: "Models", exact: true }).click();
  await page.goBack();
  await expect(page).toHaveURL(/\/matrix$/);
  await expect(nav.getByRole("link", { name: "Matrix", exact: true })).toHaveAttribute("aria-current", "page");
  await page.goForward();
  await expect(page).toHaveURL(/\/models$/);
  expect(await page.evaluate(() => (window as unknown as { marker: number }).marker)).toBe(42);
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme!);
  const [newPage] = await Promise.all([
    context.waitForEvent("page"),
    nav.getByRole("link", { name: "Models", exact: true }).click({ button: "middle" }),
  ]);
  await expect(newPage).toHaveURL(/\/models$/);
  await expect(newPage.getByRole("button", { name: "Add model" })).toBeVisible();
});

test("unknown page remains usable when catalogue fails", async ({ page }) => {
  await page.route("**/api/catalog/**", route => route.fulfill({ status: 503, body: "unavailable" }));
  const failure = page.waitForResponse(response => response.url().includes("/api/catalog/") && response.status() === 503);
  await page.goto("/missing-page");
  await failure;
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await expect(page).toHaveURL(/\/missing-page$/);
  await expect(page.locator('.tabs [aria-current="page"]')).toHaveCount(0);
  await page.goto("/models/missing");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await expect(page.locator('.tabs [aria-current="page"]')).toHaveCount(0);
  await page.unrouteAll();
  await page.getByRole("link", { name: "Go to Playground" }).click();
  await expect(page).toHaveURL(/\/playground$/);
  await expect(page.getByRole("button", { name: "Evaluate" })).toBeVisible();
});

test("navigation resets local forms and starts no provider actions", async ({ page }) => {
  const actions: string[] = [];
  page.on("request", request => { if (request.method() !== "GET" && request.url().includes("/api/")) actions.push(request.url()); });
  await page.goto("/decision-judges");
  await page.getByRole("textbox", { name: "Prompt", exact: true }).fill("temporary draft");
  await page.locator(".tabs").getByRole("link", { name: "Matrix", exact: true }).click();
  await page.locator(".tabs").getByRole("link", { name: "Decision judges" }).click();
  await expect(page.getByRole("textbox", { name: "Prompt", exact: true })).not.toHaveValue("temporary draft");
  expect(actions).toEqual([]);
});
