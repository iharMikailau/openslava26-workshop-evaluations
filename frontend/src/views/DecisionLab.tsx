import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DecisionConfig, DecisionItem, DecisionModel, DecisionQuestion, DecisionRun, EvalCase } from "../api/types";
import type { Catalog } from "../hooks/useCatalog";
import { parseDecisionExchange } from "../lib/decisionExchange";
import { decisionVerdict, summarizeDecisions } from "../lib/decisionMetrics";

const newItem = (n: number): DecisionItem => ({ id: `item-${n}`, prompt: "", answer: "", reference: null, evidence: null, labels: {} });
const examples: DecisionQuestion[] = [
  { id: "supported", type: "noul", instructions: "Does the evidence support the answer?", criteria: { true: "Supported by the evidence", false: "Not supported" } },
  { id: "compliance", type: "choice", instructions: "Does the answer follow the instruction?", criteria: { follows: "Follows the instruction", misses: "Misses the instruction", unsure: "Cannot determine" } },
  { id: "quality", type: "score", instructions: "How complete is the answer?", criteria: ["Missing", "Partial", "Complete"] },
];
function download(data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = "decision-lab.json"; a.click(); URL.revokeObjectURL(url);
}

export function DecisionLab({ catalog, openModels }: { catalog: Catalog; openModels: () => void }) {
  const [judges, setJudges] = useState<DecisionModel[]>([]);
  const [config, setConfig] = useState<DecisionConfig>({ items: [newItem(1)], questions: [structuredClone(examples[0])], judge_ids: ["jev-1-14"], baseline_model_id: null });
  const [candidate, setCandidate] = useState(catalog.models.find(m => m.role !== "judge")?.id ?? "");
  const [category, setCategory] = useState(catalog.datasets[0]?.category ?? "");
  const [cases, setCases] = useState<EvalCase[]>([]);
  const [run, setRun] = useState<DecisionRun | null>(null);
  const [thresholds, setThresholds] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [imported, setImported] = useState(false);
  useEffect(() => { api.decisionJudges().then(setJudges).catch(e => setError(String(e))); }, []);
  useEffect(() => { if (category) api.listCases(category).then(setCases).catch(e => setError(String(e))); }, [category]);
  useEffect(() => {
    if (!run || imported || (run.status !== "pending" && run.status !== "running")) return;
    const timer = window.setTimeout(() => api.getDecisionRun(run.id).then(setRun).catch(e => setError(String(e))), 500);
    return () => clearTimeout(timer);
  }, [run, imported]);
  const updateItem = (index: number, patch: Partial<DecisionItem>) => setConfig(c => ({ ...c, items: c.items.map((item, i) => i === index ? { ...item, ...patch } : item) }));
  const updateQuestion = (index: number, question: DecisionQuestion) => setConfig(c => {
    const old = c.questions[index];
    const items = old.id !== question.id || old.type !== question.type ? c.items.map(item => {
      const labels = { ...item.labels }; delete labels[old.id]; return { ...item, labels };
    }) : c.items;
    return { ...c, items, questions: c.questions.map((q, i) => i === index ? question : q) };
  });
  async function generate(index: number) {
    setBusy(true); setError("");
    try { const completion = await api.generateDecisionAnswer({ model_id: candidate, prompt: config.items[index].prompt }); if (completion.error) throw new Error(completion.error); updateItem(index, { answer: completion.text }); }
    catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function start() {
    setBusy(true); setError("");
    try {
      const checked = parseDecisionExchange(JSON.stringify({ version: 1, kind: "decision-lab-input", config }));
      if (checked.kind !== "decision-lab-input") throw new Error("Invalid input");
      const created = await api.createDecisionRun(checked.config); setImported(false); setThresholds({}); setRun(created);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  function exportExchange(value: unknown) {
    try { download(parseDecisionExchange(JSON.stringify(value))); setError(""); }
    catch (e) { setError(`Export failed: ${String(e)}`); }
  }
  async function load(file: File | undefined) {
    if (!file) return;
    try {
      const parsed = parseDecisionExchange(await file.text());
      if (parsed.kind === "decision-lab-input") { setConfig(parsed.config); setRun(null); setImported(false); }
      else { setRun(parsed.run); setThresholds(parsed.thresholds); setImported(true); }
      setError("");
    } catch (e) { setError(`Import failed: ${String(e)}`); }
  }
  const metrics = run ? summarizeDecisions(run, thresholds) : null;
  return <section className="split decision-lab">
    <div className="decision-lab__setup">
    <div className="card decision-lab__section">
    <h1 className="card__title">Decision judges · inputs</h1>
    <label>Dataset category <select value={category} onChange={e => setCategory(e.target.value)}>{catalog.datasets.map(d => <option key={d.category}>{d.category}</option>)}</select></label>
    <label>Load case into first item <select value="" onChange={e => { const found = cases.find(c => c.id === e.target.value); if (found) updateItem(0, { prompt: found.prompt, reference: found.reference ?? null }); }}><option value="">Choose a case</option>{cases.map(c => <option key={c.id} value={c.id}>{c.id}</option>)}</select></label>
    {cases.length > 0 && <details><summary>Dataset rubric hints</summary>{cases.map(c => c.rubric?.length ? <p key={c.id}>{c.id}: {c.rubric.join("; ")}</p> : null)}</details>}
    <label>Candidate for generation <select value={candidate} onChange={e => setCandidate(e.target.value)}>{catalog.models.filter(m => m.role !== "judge").map(m => <option key={m.id} value={m.id}>{m.display_name}</option>)}</select></label>
    {config.items.map((item, i) => <fieldset key={i}><legend>Item {i + 1}</legend>
      <label>Item ID <input value={item.id} onChange={e => updateItem(i, { id: e.target.value })} /></label>
      <label>Prompt <textarea value={item.prompt} onChange={e => updateItem(i, { prompt: e.target.value })} /></label>
      <label>Reference (optional) <textarea value={item.reference ?? ""} onChange={e => updateItem(i, { reference: e.target.value || null })} /></label>
      <label>Evidence (optional) <textarea value={item.evidence ?? ""} onChange={e => updateItem(i, { evidence: e.target.value || null })} /></label>
      <label>Answer <textarea value={item.answer} onChange={e => updateItem(i, { answer: e.target.value })} /></label>
      <button className="btn" type="button" disabled={busy || !item.prompt.trim()} onClick={() => void generate(i)}>Generate answer</button>
      {config.questions.map(q => <label key={q.id}>Human label: {q.id} <select value={q.id in item.labels ? String(item.labels[q.id]) : ""} onChange={e => { const labels = { ...item.labels }; if (!e.target.value) delete labels[q.id]; else labels[q.id] = q.type === "noul" ? e.target.value === "true" : q.type === "score" ? Number(e.target.value) : e.target.value; updateItem(i, { labels }); }}>
        <option value="">Unlabeled</option>{q.type === "noul" ? <><option value="true">Yes</option><option value="false">No</option></> : q.type === "choice" ? Object.keys(q.criteria).map(k => <option key={k} value={k}>{k}</option>) : q.criteria.map((v, n) => <option key={n} value={n}>{n}: {v}</option>)}
      </select></label>)}
      {config.items.length > 1 && <button className="btn" type="button" onClick={() => setConfig(c => ({ ...c, items: c.items.filter((_, n) => n !== i) }))}>Remove item</button>}
    </fieldset>)}
    <button className="btn" type="button" disabled={config.items.length >= 50} onClick={() => setConfig(c => ({ ...c, items: [...c.items, newItem(c.items.length + 1)] }))}>Add item</button>
    </div>
    <div className="card decision-lab__section">
    <h2 className="card__title">Criteria</h2>
    <p>Use narrow questions. Human labels are never sent to judges. Changing a question ID or type clears its labels in the editable form.</p>
    {config.questions.map((q, i) => <fieldset key={i}><legend>Question {i + 1}</legend>
      <label>Question ID <input value={q.id} onChange={e => updateQuestion(i, { ...q, id: e.target.value })} /></label>
      <label>Type <select value={q.type} onChange={e => { const type = e.target.value as DecisionQuestion["type"]; const sample = examples.find(x => x.type === type)!; updateQuestion(i, { ...structuredClone(sample), id: q.id }); }}><option value="noul">Noul (yes/no)</option><option value="choice">Choice</option><option value="score">Score</option></select></label>
      <label>Instructions <textarea value={q.instructions} onChange={e => updateQuestion(i, { ...q, instructions: e.target.value })} /></label>
      {q.type === "noul" ? <>{["true", "false"].map(key => <label key={key}>{key} description <input value={q.criteria[key] ?? ""} onChange={e => { const criteria = { ...q.criteria }; if (e.target.value) criteria[key] = e.target.value; else delete criteria[key]; updateQuestion(i, { ...q, criteria }); }} /></label>)}</> : q.type === "choice" ? <label>Options (one ID: description per line)<textarea key={`${q.id}-${q.type}`} defaultValue={Object.entries(q.criteria).map(([k,v]) => `${k}: ${v}`).join("\n")} onBlur={e => { const entries = e.target.value.split("\n").map(line => { const at = line.indexOf(":"); return at < 0 ? [line.trim(), ""] : [line.slice(0,at).trim(), line.slice(at+1).trim()]; }); const duplicate = new Set(entries.map(([id]) => id)).size !== entries.length; updateQuestion(i, { ...q, criteria: duplicate ? { "": "Duplicate option IDs" } : Object.fromEntries(entries) }); }} /></label> : <label>Ordered levels (one description per line)<textarea value={q.criteria.join("\n")} onChange={e => updateQuestion(i, { ...q, criteria: e.target.value.split("\n") })} /></label>}
      {config.questions.length > 1 && <button className="btn" type="button" onClick={() => setConfig(c => ({ ...c, questions: c.questions.filter((_, n) => n !== i), items: c.items.map(item => { const labels = { ...item.labels }; delete labels[q.id]; return { ...item, labels }; }) }))}>Remove question</button>}
    </fieldset>)}
    <label>Add example <select value="" onChange={e => { const q = examples[Number(e.target.value)]; if (q) setConfig(c => ({ ...c, questions: [...c.questions, structuredClone(q)] })); }}><option value="">Choose an example</option>{examples.map((q, i) => <option key={q.id} value={i}>{q.id}</option>)}</select></label>
    </div>
    <div className="card decision-lab__section">
    <h2 className="card__title">Judges</h2>
    {judges.map(j => <label className="decision-lab__judge" key={j.id}><input type="checkbox" checked={config.judge_ids.includes(j.id)} onChange={e => setConfig(c => ({ ...c, judge_ids: e.target.checked ? [...c.judge_ids, j.id] : c.judge_ids.filter(id => id !== j.id) }))} /> {j.display_name} ({j.model_id}) — {j.key_configured ? "key configured" : "key missing"}</label>)}
    <label>Optional conventional LLM baseline <select value={config.baseline_model_id ?? ""} onChange={e => setConfig(c => ({ ...c, baseline_model_id: e.target.value || null }))}><option value="">None</option>{catalog.models.filter(m => m.role !== "candidate").map(m => <option key={m.id} value={m.id}>{m.display_name}</option>)}</select></label>
    <p>All decision models use the shared OpenRouter credential.</p>
    <button className="btn" type="button" onClick={openModels}>Open Models and credentials</button>
    </div>
    <button className="btn btn--primary decision-lab__run" type="button" disabled={busy} onClick={() => void start()}>Run judgments</button>
    <div className="card decision-lab__section">
    <h2 className="card__title">JSON exchange</h2>
    <button className="btn" type="button" onClick={() => exportExchange({ version: 1, kind: "decision-lab-input", config })}>Download inputs</button>
    <label>Import inputs or results <input type="file" accept="application/json,.json" onChange={e => void load(e.target.files?.[0])} /></label>
    </div>
    </div>
    <div className="decision-lab__output">
    {error && <div className="banner" role="alert">{error}</div>}
    {busy && <p role="status">Working…</p>}
    {!run && !error && <div className="empty">Choose or enter a prompt, add an answer and select decision judges. Run the comparison to see each criterion, its uncertainty, and agreement with human labels here.</div>}
    {run && <div className="card decision-lab__section decision-lab__results"><h2 className="card__title">Results {imported && "(imported, read-only)"}</h2><p>{run.status}: {run.completed}/{run.total} judgments. {run.error?.message}</p>
      <button className="btn" type="button" onClick={() => exportExchange({ version: 1, kind: "decision-lab-result", run, thresholds })}>Download results</button>
      <p>Runs are held in process memory and disappear on restart. Exports contain supplied content and labels.</p>
      <p>Threshold tuning on this sample is exploration. Test a separate fresh set before adoption. Judge agreement is not accuracy; confidence is not quality. A false positive is a false acceptance only when yes means acceptable; a false negative is a false rejection in that case.</p>
      {run.config.questions.map(q => <section key={q.id}><h3>{q.id}: {q.instructions}</h3><details><summary>Frozen criterion and answer space</summary><pre>{JSON.stringify(q.criteria, null, 2)}</pre></details>
        {q.type === "noul" && <label>Yes threshold <input type="number" min="0" max="1" step="0.01" value={thresholds[q.id] ?? 0.5} onChange={e => { const n = Number(e.target.value); if (n >= 0 && n <= 1) setThresholds(t => ({ ...t, [q.id]: n })); }} /></label>}
        <pre>{JSON.stringify(metrics?.questions[q.id], null, 2)}</pre>
        <table><thead><tr><th>Item</th>{[...run.config.judge_ids, ...(run.config.baseline_model_id ? [run.config.baseline_model_id] : [])].map(j => <th key={j}>{j}</th>)}</tr></thead><tbody>{run.config.items.map(item => <tr key={item.id}><th><details><summary>{item.id} · label {String(item.labels[q.id] ?? "unlabeled")}</summary><pre>{JSON.stringify(item, null, 2)}</pre></details></th>{[...run.config.judge_ids, ...(run.config.baseline_model_id ? [run.config.baseline_model_id] : [])].map(j => { const row = run.results.find(r => r.item_id === item.id && r.judge_id === j); const answer = row?.answers[q.id]; return <td key={j}>{row ? <details><summary>{row.simulated ? "Simulated · " : ""}{answer ? answer.type === "noul" ? `yes probability ${answer.probability ?? "unavailable"}; verdict ${String(decisionVerdict(answer, q, thresholds[q.id] ?? 0.5))}` : `${answer.value}` : row.question_errors[q.id]?.message ?? row.error?.message ?? "Unavailable"}</summary><p>Requested: {row.requested_model}; returned: {row.returned_model ?? "unknown"}; cost: {row.usage.cost_usd ?? "unknown"}; latency: {row.usage.latency_ms ?? "unknown"} ms</p><pre>{JSON.stringify({ answer, usage: row.usage, error: row.error, question_error: row.question_errors[q.id] }, null, 2)}</pre>{j === run.config.baseline_model_id && answer?.rationale && <p>LLM baseline rationale: {answer.rationale}</p>}</details> : "Pending"}</td>; })}</tr>)}</tbody></table>
      </section>)}
    </div>}
    </div>
  </section>;
}
