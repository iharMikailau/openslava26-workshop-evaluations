import type { DecisionConfig, DecisionRun } from "../api/types";

type Obj = Record<string, unknown>;
const object = (x: unknown): x is Obj => !!x && typeof x === "object" && !Array.isArray(x);
const text = (x: unknown): x is string => typeof x === "string" && x.trim().length > 0;
const nullableText = (x: unknown) => x === null || typeof x === "string";
const prob = (x: unknown) => typeof x === "number" && Number.isFinite(x) && x >= 0 && x <= 1;
const keys = (x: Obj, allowed: string[]) => Object.keys(x).every(k => allowed.includes(k));
function assert(ok: unknown, message: string): asserts ok { if (!ok) throw new Error(message); }
function configCheck(value: unknown): asserts value is DecisionConfig {
  assert(object(value) && keys(value, ["items", "questions", "judge_ids", "baseline_model_id"]), "Invalid configuration");
  const c = value as Obj;
  assert(Array.isArray(c.questions) && c.questions.length > 0 && c.questions.length <= 20, "Invalid questions");
  assert(Array.isArray(c.items) && c.items.length > 0 && c.items.length <= 50, "Invalid items");
  assert(Array.isArray(c.judge_ids) && c.judge_ids.length > 0 && c.judge_ids.every(text) && new Set(c.judge_ids).size === c.judge_ids.length, "Invalid judges");
  assert(c.baseline_model_id === null || c.baseline_model_id === undefined || text(c.baseline_model_id), "Invalid baseline");
  const qs = c.questions as Obj[];
  const ids = new Set<string>();
  for (const q of qs) {
    assert(object(q) && keys(q, ["id", "type", "instructions", "criteria"]) && text(q.id) && text(q.instructions) && !ids.has(q.id), "Invalid question");
    ids.add(q.id as string);
    if (q.type === "noul") assert(q.criteria === undefined || (object(q.criteria) && keys(q.criteria, ["true", "false"]) && Object.values(q.criteria).every(text)), "Invalid Noul criteria");
    else if (q.type === "choice") assert(object(q.criteria) && Object.keys(q.criteria).length >= 2 && Object.keys(q.criteria).length <= 20 && Object.keys(q.criteria).every(text) && Object.values(q.criteria).every(text), "Invalid Choice criteria");
    else if (q.type === "score") assert(Array.isArray(q.criteria) && q.criteria.length >= 2 && q.criteria.length <= 10 && q.criteria.every(text), "Invalid Score criteria");
    else throw new Error("Unsupported question type");
  }
  const itemIds = new Set<string>();
  for (const item of c.items as Obj[]) {
    assert(object(item) && keys(item, ["id", "prompt", "answer", "reference", "evidence", "labels"]) && text(item.id) && !itemIds.has(item.id) && text(item.prompt) && text(item.answer), "Invalid item");
    itemIds.add(item.id as string);
    assert(item.reference === undefined || nullableText(item.reference), "Invalid reference");
    assert(item.evidence === undefined || nullableText(item.evidence), "Invalid evidence");
    assert(item.labels === undefined || object(item.labels), "Invalid labels");
    for (const [id, label] of Object.entries((item.labels ?? {}) as Obj)) {
      const q = qs.find(q => q.id === id);
      assert(q, "Label refers to unknown question");
      if (q.type === "noul") assert(typeof label === "boolean", "Invalid Boolean label");
      if (q.type === "choice") assert(typeof label === "string" && label in (q.criteria as Obj), "Invalid choice label");
      if (q.type === "score") assert(Number.isInteger(label) && (label as number) >= 0 && (label as number) < (q.criteria as unknown[]).length, "Invalid score label");
    }
  }
}
function resultCheck(value: unknown): asserts value is DecisionRun {
  assert(object(value) && keys(value, ["id", "status", "config", "results", "total", "completed", "error"]) && text(value.id) && ["pending", "running", "completed", "failed"].includes(String(value.status)), "Invalid run");
  configCheck(value.config);
  assert(Array.isArray(value.results) && Number.isInteger(value.total) && Number.isInteger(value.completed) && (value.total as number) >= 0 && (value.completed as number) >= 0 && (value.completed as number) <= (value.total as number), "Invalid progress");
  const config = value.config as DecisionConfig;
  const validError = (v: unknown) => v === null || (object(v) && keys(v, ["code", "message"]) && text(v.code) && text(v.message));
  assert(validError(value.error), "Invalid error");
  const seen = new Set<string>();
  for (const r of value.results as Obj[]) {
    assert(object(r) && keys(r, ["item_id", "judge_id", "requested_model", "returned_model", "answers", "raw_answers", "question_errors", "error", "usage", "simulated"]), "Invalid judgment");
    assert(text(r.item_id) && config.items.some(i => i.id === r.item_id) && text(r.judge_id) && [...config.judge_ids, config.baseline_model_id].includes(r.judge_id) && text(r.requested_model) && nullableText(r.returned_model), "Invalid judgment identity");
    const key = `${r.item_id}\0${r.judge_id}`; assert(!seen.has(key), "Duplicate judgment"); seen.add(key);
    assert(object(r.answers) && object(r.question_errors) && object(r.raw_answers) && validError(r.error) && typeof r.simulated === "boolean", "Invalid judgment details");
    assert(object(r.usage) && keys(r.usage, ["input_tokens", "output_tokens", "cost_usd", "latency_ms", "attempts"]), "Invalid usage");
    for (const v of Object.values(r.usage)) assert(v === null || (typeof v === "number" && Number.isFinite(v) && v >= 0), "Invalid usage value");
    for (const [id, err] of Object.entries(r.question_errors)) assert(config.questions.some(q => q.id === id) && validError(err) && err !== null, "Invalid question error");
    for (const [id, raw] of Object.entries(r.raw_answers)) {
      const q = config.questions.find(q => q.id === id);
      assert(q && object(raw) && raw.type === q.type, "Invalid raw answer");
      if (q.type === "noul") assert(keys(raw, ["type", "noul"]) && prob(raw.noul), "Invalid raw Noul");
      if (q.type === "choice") {
        assert(keys(raw, ["type", "choice", "probabilities", "confidence"]) && typeof raw.choice === "string" && raw.choice in q.criteria && object(raw.probabilities), "Invalid raw Choice");
        assert(Object.keys(raw.probabilities).length === Object.keys(q.criteria).length && Object.keys(q.criteria).every(k => prob((raw.probabilities as Obj)[k])) && Math.abs(Object.values(raw.probabilities).reduce<number>((a, b) => a + Number(b), 0) - 1) <= 0.001 && Number(raw.probabilities[raw.choice as string]) >= Math.max(...Object.values(raw.probabilities).map(Number)) && (raw.confidence === undefined || raw.confidence === null || prob(raw.confidence)), "Invalid raw Choice values");
      }
      if (q.type === "score") {
        assert(keys(raw, ["type", "score", "probabilities", "legend", "confidence"]) && typeof raw.score === "number" && Number.isFinite(raw.score) && raw.score >= 0 && raw.score <= q.criteria.length - 1 && object(raw.probabilities) && object(raw.legend), "Invalid raw Score");
        assert(Object.keys(raw.probabilities).length === q.criteria.length && Object.keys(raw.legend).length === q.criteria.length && q.criteria.every((level, n) => prob((raw.probabilities as Obj)[String(n)]) && (raw.legend as Obj)[String(n)] === level) && Math.abs(Object.values(raw.probabilities).reduce<number>((a, b) => a + Number(b), 0) - 1) <= 0.001 && (raw.confidence === undefined || raw.confidence === null || prob(raw.confidence)), "Invalid raw Score values");
      }
    }
    for (const [id, answer] of Object.entries(r.answers)) {
      const q = config.questions.find(q => q.id === id);
      assert(q && object(answer) && answer.type === q.type, "Invalid answer type");
      if (q.type === "noul") assert(keys(answer, ["type", "probability", "verdict", "rationale"]) && (answer.probability === null || prob(answer.probability)) && (answer.verdict === null || typeof answer.verdict === "boolean") && nullableText(answer.rationale) && (answer.probability !== null || answer.verdict !== null), "Invalid Noul answer");
      if (q.type === "choice") {
        assert(keys(answer, ["type", "value", "probabilities", "confidence", "rationale"]) && typeof answer.value === "string" && answer.value in q.criteria && (answer.confidence === null || prob(answer.confidence)) && nullableText(answer.rationale), "Invalid Choice answer");
        if (answer.probabilities !== null) assert(object(answer.probabilities) && Object.keys(answer.probabilities).length === Object.keys(q.criteria).length && Object.keys(q.criteria).every(k => prob((answer.probabilities as Obj)[k])) && Math.abs(Object.values(answer.probabilities).reduce<number>((a, b) => a + Number(b), 0) - 1) <= 0.001 && Number(answer.probabilities[answer.value as string]) >= Math.max(...Object.values(answer.probabilities).map(Number)), "Invalid Choice distribution");
      }
      if (q.type === "score") {
        assert(keys(answer, ["type", "value", "normalized", "probabilities", "confidence", "rationale"]) && typeof answer.value === "number" && Number.isFinite(answer.value) && answer.value >= 0 && answer.value <= q.criteria.length - 1 && prob(answer.normalized) && Math.abs(Number(answer.normalized) - answer.value / (q.criteria.length - 1)) < 1e-9 && (answer.confidence === null || prob(answer.confidence)) && nullableText(answer.rationale), "Invalid Score answer");
        if (answer.probabilities !== null) assert(Array.isArray(answer.probabilities) && answer.probabilities.length === q.criteria.length && answer.probabilities.every(prob) && Math.abs(answer.probabilities.reduce((a, b) => a + b, 0) - 1) <= 0.001, "Invalid Score distribution");
      }
    }
  }
}
export type DecisionExchange = { version: 1; kind: "decision-lab-input"; config: DecisionConfig } | { version: 1; kind: "decision-lab-result"; run: DecisionRun; thresholds: Record<string, number> };
export function parseDecisionExchange(source: string): DecisionExchange {
  const data: unknown = JSON.parse(source);
  assert(object(data) && data.version === 1, "Unsupported exchange version");
  if (data.kind === "decision-lab-input") {
    assert(keys(data, ["version", "kind", "config"]), "Invalid input exchange");
    configCheck(data.config);
    const c = data.config as DecisionConfig;
    c.baseline_model_id ??= null;
    for (const q of c.questions) if (q.type === "noul") q.criteria ??= {};
    for (const i of c.items) { i.reference ??= null; i.evidence ??= null; i.labels ??= {}; }
    return data as DecisionExchange;
  }
  assert(data.kind === "decision-lab-result" && keys(data, ["version", "kind", "run", "thresholds"]), "Invalid result exchange");
  resultCheck(data.run);
  assert(object(data.thresholds) && Object.entries(data.thresholds).every(([id, n]) => (data.run as DecisionRun).config.questions.some(q => q.id === id && q.type === "noul") && prob(n)), "Invalid thresholds");
  return data as DecisionExchange;
}
