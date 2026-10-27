"""Deterministic simulated decisions for the offline workshop."""

from workshop_evals.domain.decision_catalog import DecisionModel
from workshop_evals.domain.decision_lab import (
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionError,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)


class FakeDecisionClient:
    async def decide(
        self,
        model: DecisionModel,
        item_id: str,
        state: dict[str, str | None],
        questions: list[Question],
    ) -> Judgment:
        result = Judgment(
            item_id=item_id,
            judge_id=model.id,
            requested_model=model.model_id,
            returned_model=model.model_id,
            simulated=True,
        )
        for question in questions:
            if model.id == "microsoft-decision-1" and question.id == "demo-error":
                result.question_errors[question.id] = DecisionError(
                    code="simulated_error", message="Simulated decision error."
                )
            elif isinstance(question, NoulQuestion):
                result.answers[question.id] = NoulAnswer(
                    type="noul", probability=0.2 if model.id == "gpt-6-luna-decisions" else 0.8
                )
            elif isinstance(question, ChoiceQuestion):
                options = list(question.criteria)
                chosen = options[1] if model.id == "gpt-6-luna-decisions" else options[0]
                result.answers[question.id] = ChoiceAnswer(
                    type="choice",
                    value=chosen,
                    probabilities={option: float(option == chosen) for option in options},
                    confidence=0.8,
                )
            elif isinstance(question, ScoreQuestion):
                result.answers[question.id] = ScoreAnswer.from_raw(
                    0.25,
                    len(question.criteria),
                    confidence=0.95,
                    probabilities=[0.75, 0.25] + [0.0] * (len(question.criteria) - 2),
                )
        return result
