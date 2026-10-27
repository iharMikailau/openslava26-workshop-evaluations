import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

test("simulated lab runs, retains snapshot, and replays thresholds locally", async ({ page }) => {
  await page.goto("/");
  let decisions = 0;
  page.on("request", r => { if (r.url().includes("/api/decision-lab/runs") && r.method() === "POST") decisions++; });
  await page.getByRole("link", { name: "Decision judges" }).click();
  await expect(page.getByText("TypeSafe: Jev 1.14")).toBeVisible();
  await expect(page.getByText("OpenAI: GPT-6 Luna Decisions")).toBeVisible();
  await expect(page.getByText("Microsoft: Microsoft-Decision-1")).toBeVisible();
  expect(decisions).toBe(0);
  await page.getByLabel("Prompt", { exact: true }).fill("What is the color?");
  await page.getByLabel("Evidence (optional)").fill("The sky is blue.");
  await page.getByRole("textbox", { name: "Answer", exact: true }).fill("Blue.");
  await page.getByLabel("Human label: supported").selectOption("false");
  await page.getByRole("button", { name: "Run judgments" }).click();
  await expect(page.getByText("completed: 1/1 judgments.")).toBeVisible();
  await expect(page.getByText("Simulated · yes probability", { exact: false })).toBeVisible();
  await expect(page.getByText('"fp": 1', { exact: false })).toBeVisible();
  await page.getByRole("textbox", { name: "Answer", exact: true }).fill("Changed later");
  await page.getByLabel("Yes threshold").fill("0.9");
  await expect(page.getByText('"fp": 0', { exact: false })).toBeVisible();
  expect(decisions).toBe(1);
  await page.getByText("item-1 · label false").click();
  await expect(page.getByText('"answer": "Blue."', { exact: false })).toBeVisible();
});

test("generation is separate and exported results import without requests", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Decision judges" }).click();
  let generations = 0, runs = 0;
  page.on("request", r => {
    if (r.method() === "POST" && r.url().includes("/decision-lab/generate")) generations++;
    if (r.method() === "POST" && r.url().includes("/decision-lab/runs")) runs++;
  });
  await page.getByRole("textbox", { name: "Prompt", exact: true }).fill("A question");
  await page.getByRole("button", { name: "Generate answer" }).click();
  await expect(page.getByRole("textbox", { name: "Answer", exact: true })).toHaveValue("positive");
  expect(generations).toBe(1); expect(runs).toBe(0);
  await page.getByRole("button", { name: "Run judgments" }).click();
  await expect(page.getByText("completed: 1/1 judgments.")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download results" }).click();
  const path = await (await download).path();
  await page.getByLabel("Import inputs or results").setInputFiles(path!);
  await expect(page.getByText("Results (imported, read-only)")).toBeVisible();
  const exportedAgain = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download results" }).click();
  const secondPath = await (await exportedAgain).path();
  expect(JSON.parse(readFileSync(secondPath!, "utf8"))).toEqual(JSON.parse(readFileSync(path!, "utf8")));
  expect(generations).toBe(1); expect(runs).toBe(1);
});

test("typed criteria validation and simulated uncertainty", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Decision judges" }).click();
  await page.getByRole("textbox", { name: "Prompt", exact: true }).fill("Q");
  await page.getByRole("textbox", { name: "Answer", exact: true }).fill("A");
  await page.getByLabel("Add example").selectOption("1");
  await page.getByLabel("Add example").selectOption("2");
  await page.getByLabel("Options (one ID: description per line)").fill("yes: Complies\nno: Does not comply\nunsure: Unknown");
  await page.getByLabel("Ordered levels (one description per line)").fill("Low\nHigh");
  await page.getByRole("button", { name: "Run judgments" }).click();
  await expect(page.getByText("completed: 1/1 judgments.")).toBeVisible();
  await expect(page.getByRole("heading", { name: /compliance:/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /quality:/ })).toBeVisible();
  await page.getByText("Simulated · 0.25").click();
  await expect(page.getByText('"confidence": 0.95', { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: /quality:/ }).locator("..").getByText(/cost: unknown/)).toBeVisible();
});

test("invalid criteria are rejected and baseline rationale is attributed", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Decision judges" }).click();
  await page.getByRole("textbox", { name: "Prompt", exact: true }).fill("Q");
  await page.getByRole("textbox", { name: "Answer", exact: true }).fill("A");
  await page.getByRole("textbox", { name: "Instructions", exact: true }).fill("");
  await page.getByRole("button", { name: "Run judgments" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid question");
  await page.getByRole("textbox", { name: "Instructions", exact: true }).fill("Acceptable?");
  await page.getByLabel("Optional conventional LLM baseline").selectOption("qwen3-4b");
  await page.getByRole("button", { name: "Run judgments" }).click();
  await expect(page.getByText("completed: 2/2 judgments.")).toBeVisible();
  await page.getByText("Simulated · yes probability unavailable; verdict true").click();
  await expect(page.getByText("LLM baseline rationale: Simulated baseline.")).toBeVisible();
});

test("choice and score labels are validated and survive a run", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Decision judges" }).click();
  await page.getByRole("textbox", { name: "Prompt", exact: true }).fill("Q");
  await page.getByRole("textbox", { name: "Answer", exact: true }).fill("A");
  await page.getByLabel("Add example").selectOption("1");
  await page.getByLabel("Add example").selectOption("2");
  await page.getByLabel("Human label: compliance").selectOption("follows");
  await page.getByLabel("Human label: quality").selectOption("2");
  await page.getByRole("button", { name: "Run judgments" }).click();
  await expect(page.getByText("completed: 1/1 judgments.")).toBeVisible();
  await expect(page.getByText("item-1 · label follows")).toBeVisible();
  await expect(page.getByText("item-1 · label 2")).toBeVisible();
});

test("partial simulated failures leave other decisions visible", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Decision judges" }).click();
  await page.getByRole("textbox", { name: "Prompt", exact: true }).fill("Q");
  await page.getByRole("textbox", { name: "Answer", exact: true }).fill("A");
  await page.getByRole("textbox", { name: "Question ID" }).fill("demo-error");
  await page.getByRole("checkbox", { name: /Microsoft: Microsoft-Decision-1/ }).check();
  await page.getByRole("button", { name: "Run judgments" }).click();
  await expect(page.getByText("completed: 2/2 judgments.")).toBeVisible();
  await expect(page.getByText("Simulated · Simulated decision error.")).toBeVisible();
  await expect(page.getByText("Simulated · yes probability 0.8", { exact: false })).toBeVisible();
});
