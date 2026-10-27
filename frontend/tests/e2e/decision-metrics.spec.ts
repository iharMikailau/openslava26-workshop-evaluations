import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { DecisionRun } from "../../src/api/types";
import { decisionVerdict, summarizeDecisions } from "../../src/lib/decisionMetrics";

test("shared metrics fixture and fixed baseline verdict", () => {
  const fixture = JSON.parse(readFileSync("../backend/tests/fixtures/decision_metrics.json", "utf8"));
  const run = fixture.run as DecisionRun;
  expect(summarizeDecisions(run).questions.ok.judges["jev-1-14"]).toEqual(fixture.expected);
  const baseline = { type: "noul", probability: null, verdict: true, rationale: null } as const;
  const question = run.config.questions[0];
  expect(decisionVerdict(baseline, question, 0.1)).toBe(true);
  expect(decisionVerdict(baseline, question, 0.9)).toBe(true);
});
