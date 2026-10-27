import json
from pathlib import Path

from workshop_evals.domain.decision_lab import LabRun
from workshop_evals.domain.decision_metrics import summarize


def test_shared_fixture_and_threshold_equality():
    data = json.loads(Path("tests/fixtures/decision_metrics.json").read_text())
    run = LabRun.model_validate(data["run"])
    assert summarize(run)["questions"]["ok"]["judges"]["jev-1-14"] == data["expected"]
    changed = summarize(run, {"ok": 0.9})["questions"]["ok"]["judges"]["jev-1-14"]
    assert changed["fp"] == 0 and changed["fn"] == 1


def test_empty_denominators_and_pending():
    data = json.loads(Path("tests/fixtures/decision_metrics.json").read_text())
    run = LabRun.model_validate(data["run"])
    run.results = []
    summary = summarize(run)["questions"]["ok"]["judges"]["jev-1-14"]
    assert summary["pending"] == 4 and summary["errors"] == 0
    assert summary["accuracy"] is None and summary["false_positive_rate"] is None


def test_choice_ordinal_and_overlapping_agreement():
    run = LabRun.model_validate(
        {
            "id": "r",
            "status": "completed",
            "config": {
                "questions": [
                    {
                        "id": "category",
                        "type": "choice",
                        "instructions": "Which?",
                        "criteria": {"a": "A", "b": "B"},
                    },
                    {
                        "id": "scale",
                        "type": "score",
                        "instructions": "How?",
                        "criteria": ["Bad", "OK", "Good"],
                    },
                    {
                        "id": "short",
                        "type": "score",
                        "instructions": "How?",
                        "criteria": ["Bad", "Good"],
                    },
                ],
                "items": [
                    {
                        "id": "one",
                        "prompt": "Q",
                        "answer": "A",
                        "labels": {"category": "a", "scale": 2, "short": 1},
                    }
                ],
                "judge_ids": ["jev-1-14", "gpt-6-luna-decisions"],
            },
            "results": [
                {
                    "item_id": "one",
                    "judge_id": "jev-1-14",
                    "requested_model": "one",
                    "answers": {
                        "category": {"type": "choice", "value": "b"},
                        "scale": {"type": "score", "value": 1.0, "normalized": 0.5},
                        "short": {"type": "score", "value": 0.5, "normalized": 0.5},
                    },
                },
                {
                    "item_id": "one",
                    "judge_id": "gpt-6-luna-decisions",
                    "requested_model": "two",
                    "answers": {
                        "category": {"type": "choice", "value": "b"},
                    },
                },
            ],
        }
    )
    summary = summarize(run)["questions"]
    assert summary["category"]["judges"]["jev-1-14"]["confusion"]["a"]["b"] == 1
    assert summary["category"]["agreement"][0]["agreement"] == 1
    assert summary["scale"]["agreement"][0]["overlap"] == 0
    assert summary["scale"]["judges"]["jev-1-14"]["mae"] == 1
    assert summary["short"]["judges"]["jev-1-14"]["mae"] == 0.5
