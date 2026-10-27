"""Generation and conventional chat baseline for the decision lab."""

import json
import time

from workshop_evals.application.ports.llm_client import LLMClientPort
from workshop_evals.application.ports.model_catalog import ModelCatalogPort
from workshop_evals.domain.decision_lab import (
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionError,
    DecisionUsage,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)
from workshop_evals.domain.models import Completion, RunParams

DECISION_BASELINE_SYSTEM = "Return typed decision-lab judgments as JSON."


class DecisionChatService:
    def __init__(
        self, client: LLMClientPort, models: ModelCatalogPort, *, simulated: bool = False
    ) -> None:
        self._client = client
        self._models = models
        self._simulated = simulated

    def validate_baseline(self, model_id: str) -> None:
        model = self._models.get_model(model_id)
        if model is None or not model.enabled or not model.usable_as_judge():
            raise ValueError("Unknown baseline judge")

    async def generate(self, model_id: str, prompt: str) -> Completion:
        model = self._models.get_model(model_id)
        if model is None or not model.enabled or not model.usable_as_candidate():
            raise ValueError("Unknown candidate model")
        return await self._client.chat(model, [{"role": "user", "content": prompt}], RunParams())

    async def judge(
        self, model_id: str, item_id: str, state: dict[str, str | None], questions: list[Question]
    ) -> Judgment:
        model = self._models.get_model(model_id)
        if model is None or not model.enabled or not model.usable_as_judge():
            raise ValueError("Unknown baseline judge")
        result = Judgment(
            item_id=item_id,
            judge_id=model_id,
            requested_model=model.model_id,
            simulated=self._simulated,
        )
        prompt = (
            "Judge the supplied state against each question. Return only a JSON object keyed by "
            "question ID; each value must be an object with 'value' and optional 'rationale'. "
            "For noul use a Boolean, for choice use an option ID, and for score use an integer "
            "zero-based level. Do not include probabilities or confidence.\n"
            + json.dumps({"state": state, "questions": [q.model_dump() for q in questions]})
        )
        started = time.perf_counter()
        completion = await self._client.chat(
            model,
            [
                {"role": "system", "content": DECISION_BASELINE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            RunParams(),
        )
        result.returned_model = completion.model_id
        result.usage = DecisionUsage(
            input_tokens=completion.usage.prompt_tokens,
            output_tokens=completion.usage.completion_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            cost_usd=None,
        )
        if completion.error:
            result.error = DecisionError(code="baseline_error", message=completion.error)
            return result
        try:
            answers = json.loads(completion.text)
            if not isinstance(answers, dict):
                raise ValueError("not an object")
        except (ValueError, TypeError):
            result.error = DecisionError(
                code="invalid_baseline", message="Baseline returned invalid JSON."
            )
            return result
        for question in questions:
            try:
                raw = answers[question.id]
                if not isinstance(raw, dict):
                    raise ValueError("invalid answer")
                value = raw["value"]
                rationale = raw.get("rationale")
                if rationale is not None and not isinstance(rationale, str):
                    raise ValueError("invalid rationale")
                if isinstance(question, NoulQuestion) and type(value) is bool:
                    answer = NoulAnswer(type="noul", verdict=value, rationale=rationale)
                elif (
                    isinstance(question, ChoiceQuestion)
                    and isinstance(value, str)
                    and value in question.criteria
                ):
                    answer = ChoiceAnswer(type="choice", value=value, rationale=rationale)
                elif isinstance(question, ScoreQuestion) and type(value) is int:
                    answer = ScoreAnswer.from_raw(
                        value, len(question.criteria), rationale=rationale
                    )
                else:
                    raise ValueError("invalid value")
                result.answers[question.id] = answer
            except (KeyError, TypeError, ValueError):
                result.question_errors[question.id] = DecisionError(
                    code="invalid_baseline_answer", message="Missing or invalid baseline answer."
                )
        return result
