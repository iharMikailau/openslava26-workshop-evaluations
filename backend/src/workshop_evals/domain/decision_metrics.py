"""Per-question, coverage-aware metrics for decision lab snapshots."""

from collections import Counter
from itertools import combinations

from workshop_evals.domain.decision_lab import (
    ChoiceAnswer,
    ChoiceQuestion,
    Judgment,
    LabRun,
    NoulAnswer,
    NoulQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)


def verdict(answer, question: Question, threshold: float):
    if isinstance(question, NoulQuestion) and isinstance(answer, NoulAnswer):
        if answer.probability is not None:
            return answer.probability >= threshold
        return answer.verdict
    if isinstance(question, ChoiceQuestion) and isinstance(answer, ChoiceAnswer):
        return answer.value
    if isinstance(question, ScoreQuestion) and isinstance(answer, ScoreAnswer):
        return answer.value
    return None


def summarize(run: LabRun, thresholds: dict[str, float] | None = None) -> dict:
    thresholds = thresholds or {}
    result = {"questions": {}}
    judges = list(run.config.judge_ids)
    if run.config.baseline_model_id:
        judges.append(run.config.baseline_model_id)
    by_key: dict[tuple[str, str], Judgment] = {(r.item_id, r.judge_id): r for r in run.results}
    for question in run.config.questions:
        threshold = thresholds.get(question.id, 0.5)
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        summaries = {}
        for judge in judges:
            total = len(run.config.items)
            labeled = sum(question.id in item.labels for item in run.config.items)
            pairs = []
            errors = 0
            pending = 0
            successful = 0
            for item in run.config.items:
                judgment = by_key.get((item.id, judge))
                if judgment is None:
                    pending += 1
                    continue
                value = (
                    verdict(judgment.answers.get(question.id), question, threshold)
                    if judgment
                    else None
                )
                if value is None:
                    errors += 1
                    continue
                successful += 1
                if question.id in item.labels:
                    pairs.append((item.labels[question.id], value))
            summary = {
                "total": total,
                "labeled": labeled,
                "unlabeled": total - labeled,
                "successful": successful,
                "errors": errors,
                "pending": pending,
                "comparable": len(pairs),
            }
            if isinstance(question, NoulQuestion):
                counts = Counter((expected, actual) for expected, actual in pairs)
                tp, fp = counts[(True, True)], counts[(False, True)]
                tn, fn = counts[(False, False)], counts[(True, False)]
                summary.update(
                    tp=tp,
                    fp=fp,
                    tn=tn,
                    fn=fn,
                    accuracy=(tp + tn) / len(pairs) if pairs else None,
                    false_positive_rate=fp / (fp + tn) if fp + tn else None,
                    false_negative_rate=fn / (fn + tp) if fn + tp else None,
                )
            elif isinstance(question, ChoiceQuestion):
                confusion = {
                    expected: dict.fromkeys(question.criteria, 0)
                    for expected in question.criteria
                }
                for expected, actual in pairs:
                    confusion[expected][actual] += 1
                summary.update(
                    agreement=sum(expected == actual for expected, actual in pairs) / len(pairs)
                    if pairs
                    else None,
                    confusion=confusion,
                )
            else:
                summary["mae"] = (
                    sum(abs(expected - actual) for expected, actual in pairs) / len(pairs)
                    if pairs
                    else None
                )
            summaries[judge] = summary
        agreement = []
        for left, right in combinations(judges, 2):
            overlap = []
            for item in run.config.items:
                a, b = by_key.get((item.id, left)), by_key.get((item.id, right))
                av = verdict(a.answers.get(question.id), question, threshold) if a else None
                bv = verdict(b.answers.get(question.id), question, threshold) if b else None
                if av is not None and bv is not None:
                    overlap.append((av, bv))
            agreement.append(
                {
                    "left": left,
                    "right": right,
                    "overlap": len(overlap),
                    "agreement": sum(a == b for a, b in overlap) / len(overlap)
                    if overlap
                    else None,
                }
            )
        result["questions"][question.id] = {"judges": summaries, "agreement": agreement}
    return result
