import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { parseDecisionExchange } from "../../src/lib/decisionExchange";

test("exchange round trips and rejects invalid data", () => {
  const fixture = JSON.parse(readFileSync("../backend/tests/fixtures/decision_metrics.json", "utf8"));
  const result = { version: 1, kind: "decision-lab-result", run: fixture.run, thresholds: { ok: 0.5 } };
  expect(parseDecisionExchange(JSON.stringify(result))).toEqual(result);
  const input = { version: 1, kind: "decision-lab-input", config: fixture.run.config };
  expect(parseDecisionExchange(JSON.stringify(input))).toEqual(input);
  expect(() => parseDecisionExchange(JSON.stringify({ ...input, version: 2 }))).toThrow();
  const badLabel = structuredClone(input); badLabel.config.items[0].labels.ok = "yes";
  expect(() => parseDecisionExchange(JSON.stringify(badLabel))).toThrow();
  const badProb = structuredClone(result); badProb.run.results[0].answers.ok.probability = 1.2;
  expect(() => parseDecisionExchange(JSON.stringify(badProb))).toThrow();
  const credential = structuredClone(result); credential.run.results[0].usage.api_key = "secret";
  expect(() => parseDecisionExchange(JSON.stringify(credential))).toThrow();
});
