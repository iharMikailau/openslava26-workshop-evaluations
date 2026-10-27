# Decision judges lab

The lab compares typed decisions on a shared answer and context. Human labels are
stored separately from the state sent to judges. Input exports use version 1; this
synthetic example contains no real customer data:

```json
{
  "version": 1,
  "kind": "decision-lab-input",
  "config": {
    "items": [
      {
        "id": "sample-1",
        "prompt": "What color is the sky?",
        "answer": "Blue.",
        "reference": null,
        "evidence": "The sky appears blue on a clear day.",
        "labels": {"supported": true}
      }
    ],
    "questions": [
      {
        "id": "supported",
        "type": "noul",
        "instructions": "Does the evidence support the answer?",
        "criteria": {"true": "Supported", "false": "Not supported"}
      }
    ],
    "judge_ids": ["jev-1-14"],
    "baseline_model_id": null
  }
}
```

Result exports use `kind: "decision-lab-result"`, version `1`, a `run` snapshot,
and per-question `thresholds`. Exports contain supplied content and labels; handle
them accordingly. Unsupported versions are rejected.

In demo mode, decisions are simulated and require no provider key or network call.
The simulated judges deliberately disagree; a question with ID `demo-error` also
shows a simulated error for Microsoft-Decision-1. Live mode uses the shared
`OPENROUTER_API_KEY` and may incur provider charges.

## Try the lab

1. Open **Decision judges**. The three curated models are listed without a provider
   call. In live mode, set the shared OpenRouter key under **Models → Session
   credentials** (or use the backend environment). Demo mode needs no key.
2. Choose a dataset case or enter a prompt, reference, and evidence. Paste an answer,
   or select a chat candidate and click **Generate answer** once. Review the generated
   answer before starting judgments. Add supplied-answer items for a validation set.
3. Edit a narrow yes/no, Choice, or ordered Score criterion. For example, ask whether
   the evidence supports a claim, rather than asking for a general quality judgment.
   The dataset's rubric hints are source material, not automatically imposed criteria.
   Give each question a unique ID and add optional human labels separately for each item.
4. Select decision judges and, optionally, a conventional chat baseline. Click **Run
   judgments**. All selected judges receive the same frozen answer and criteria; labels
   are never sent to them. The baseline's rationale belongs to that baseline only.
5. Inspect results by criterion, including errors, native distributions, model IDs,
   latency, and reported cost. Missing cost is unknown. A Score is a zero-based
   weighted position; its normalized value divides by the highest level. Confidence
   is not answer quality or measured accuracy. Noul has a yes probability but no
   separate native confidence.
6. Review coverage and labeled comparisons. A false positive is a false acceptance
   only when yes means acceptable; a false negative is a false rejection in that case.
   Categorical agreement and raw-level ordinal MAE apply per question. Judge agreement
   describes overlapping predictions, not correctness. Missing labels and errors do not
   count as correct or incorrect predictions.
7. Adjust a yes threshold locally to explore saved probabilities without another
   provider call. Tuning and reporting on the same small set can overstate performance:
   evaluate a fresh, separate labeled set before adopting a threshold. Download the
   result snapshot for later offline review; process-memory runs disappear on restart.

The three model IDs are explicit, but provider routing or weights can change. Results
from older Jev benchmarks do not establish the accuracy of Jev 1.14 or the other
models on your task. This workshop does not implement a production monitor or
an automatic escalation policy.

Open the lab at `/decision-judges`. Leaving it resets local inputs and results; refresh restores the page only.
