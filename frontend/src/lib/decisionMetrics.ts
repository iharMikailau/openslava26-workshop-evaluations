import type { DecisionAnswer, DecisionQuestion, DecisionRun } from "../api/types";

type Verdict = boolean | string | number;
export function decisionVerdict(answer: DecisionAnswer | undefined, question: DecisionQuestion, threshold: number): Verdict | null {
  if (!answer || answer.type !== question.type) return null;
  if (answer.type === "noul") return answer.probability === null ? answer.verdict : answer.probability >= threshold;
  return answer.value;
}

export function summarizeDecisions(run: DecisionRun, thresholds: Record<string, number> = {}) {
  const questions: Record<string, { judges: Record<string, Record<string, unknown>>; agreement: Array<{ left: string; right: string; overlap: number; agreement: number | null }> }> = {};
  const judges = [...run.config.judge_ids, ...(run.config.baseline_model_id ? [run.config.baseline_model_id] : [])];
  for (const question of run.config.questions) {
    const threshold = thresholds[question.id] ?? 0.5;
    if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) throw new Error("Invalid threshold");
    const summaries: Record<string, Record<string, unknown>> = {};
    for (const judge of judges) {
      let successful = 0, errors = 0, pending = 0;
      const pairs: Array<[Verdict, Verdict]> = [];
      const labeled = run.config.items.filter(item => question.id in item.labels).length;
      for (const item of run.config.items) {
        const row = run.results.find(r => r.item_id === item.id && r.judge_id === judge);
        if (!row) { pending++; continue; }
        const actual = decisionVerdict(row.answers[question.id], question, threshold);
        if (actual === null) { errors++; continue; }
        successful++;
        if (question.id in item.labels) pairs.push([item.labels[question.id], actual]);
      }
      const summary: Record<string, unknown> = { total: run.config.items.length, labeled, unlabeled: run.config.items.length - labeled, successful, errors, pending, comparable: pairs.length };
      if (question.type === "noul") {
        const count = (e: boolean, a: boolean) => pairs.filter(([x, y]) => x === e && y === a).length;
        const tp = count(true, true), fp = count(false, true), tn = count(false, false), fn = count(true, false);
        Object.assign(summary, { tp, fp, tn, fn, accuracy: pairs.length ? (tp + tn) / pairs.length : null, false_positive_rate: fp + tn ? fp / (fp + tn) : null, false_negative_rate: fn + tp ? fn / (fn + tp) : null });
      } else if (question.type === "choice") {
        const confusion: Record<string, Record<string, number>> = {};
        for (const e of Object.keys(question.criteria)) confusion[e] = Object.fromEntries(Object.keys(question.criteria).map(a => [a, 0]));
        for (const [e, a] of pairs) confusion[String(e)][String(a)]++;
        Object.assign(summary, { confusion, agreement: pairs.length ? pairs.filter(([e, a]) => e === a).length / pairs.length : null });
      } else {
        summary.mae = pairs.length ? pairs.reduce((sum, [e, a]) => sum + Math.abs(Number(e) - Number(a)), 0) / pairs.length : null;
      }
      summaries[judge] = summary;
    }
    const agreement: Array<{ left: string; right: string; overlap: number; agreement: number | null }> = [];
    for (let i = 0; i < judges.length; i++) for (let j = i + 1; j < judges.length; j++) {
      const pairs: Array<[Verdict, Verdict]> = [];
      for (const item of run.config.items) {
        const a = run.results.find(r => r.item_id === item.id && r.judge_id === judges[i]);
        const b = run.results.find(r => r.item_id === item.id && r.judge_id === judges[j]);
        const av = decisionVerdict(a?.answers[question.id], question, threshold), bv = decisionVerdict(b?.answers[question.id], question, threshold);
        if (av !== null && bv !== null) pairs.push([av, bv]);
      }
      agreement.push({ left: judges[i], right: judges[j], overlap: pairs.length, agreement: pairs.length ? pairs.filter(([a, b]) => a === b).length / pairs.length : null });
    }
    questions[question.id] = { judges: summaries, agreement };
  }
  return { questions };
}
