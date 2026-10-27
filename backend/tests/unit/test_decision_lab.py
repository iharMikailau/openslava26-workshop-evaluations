import pytest
from pydantic import ValidationError

from workshop_evals.domain.decision_lab import LabConfig, NoulAnswer, ScoreAnswer


def config():
    return {
        "questions": [
            {"id": "ok", "type": "noul", "instructions": "Supported?"},
            {
                "id": "kind",
                "type": "choice",
                "instructions": "Which?",
                "criteria": {"a": "A", "b": "B"},
            },
            {
                "id": "quality",
                "type": "score",
                "instructions": "Quality?",
                "criteria": ["Low", "High"],
            },
        ],
        "items": [
            {
                "id": "one",
                "prompt": "Q",
                "answer": "A",
                "labels": {"ok": True, "kind": "a", "quality": 1},
            }
        ],
        "judge_ids": ["jev"],
    }


def test_labels_are_separate_from_state():
    parsed = LabConfig.model_validate(config())
    assert "labels" not in parsed.items[0].state()
    assert LabConfig.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize(
    "question,label",
    [("ok", 1), ("kind", "other"), ("quality", True), ("quality", 2), ("missing", False)],
)
def test_invalid_labels(question, label):
    data = config()
    data["items"][0]["labels"] = {question: label}
    with pytest.raises(ValidationError):
        LabConfig.model_validate(data)


def test_duplicates_bounds_and_extra_fields():
    data = config()
    data["questions"].append(data["questions"][0])
    with pytest.raises(ValidationError):
        LabConfig.model_validate(data)
    data = config()
    data["items"][0]["image"] = "data:image/png;base64,..."
    with pytest.raises(ValidationError):
        LabConfig.model_validate(data)
    data = config()
    data["questions"][2]["criteria"] = ["one"]
    with pytest.raises(ValidationError):
        LabConfig.model_validate(data)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_probabilities(value):
    with pytest.raises(ValidationError):
        NoulAnswer(type="noul", probability=value)
    with pytest.raises(ValidationError):
        ScoreAnswer(type="score", value=0, normalized=value)


def test_score_normalization_and_bounds():
    assert ScoreAnswer.from_raw(1.5, 4).normalized == 0.5
    with pytest.raises(ValueError):
        ScoreAnswer.from_raw(4, 4)
    with pytest.raises(ValueError):
        ScoreAnswer.from_raw(float("nan"), 4)


def test_versioned_exchange_round_trip_and_unknown_version():
    from workshop_evals.domain.decision_lab import InputExchange, LabRun, ResultExchange

    parsed = LabConfig.model_validate(config())
    inputs = InputExchange(version=1, kind="decision-lab-input", config=parsed)
    assert InputExchange.model_validate_json(inputs.model_dump_json()) == inputs
    result = ResultExchange(
        version=1, kind="decision-lab-result", run=LabRun(id="run", config=parsed)
    )
    assert ResultExchange.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError):
        InputExchange.model_validate({**inputs.model_dump(), "version": 2})
