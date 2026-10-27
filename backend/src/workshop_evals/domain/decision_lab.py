"""Typed, text-only contracts for decision-judge experiments."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


NonEmpty = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=True)]


class NoulQuestion(StrictModel):
    id: NonEmpty
    type: Literal["noul"]
    instructions: NonEmpty
    criteria: dict[Literal["true", "false"], NonEmpty] = Field(default_factory=dict)


class ChoiceQuestion(StrictModel):
    id: NonEmpty
    type: Literal["choice"]
    instructions: NonEmpty
    criteria: dict[NonEmpty, NonEmpty] = Field(min_length=2, max_length=20)


class ScoreQuestion(StrictModel):
    id: NonEmpty
    type: Literal["score"]
    instructions: NonEmpty
    criteria: list[NonEmpty] = Field(min_length=2, max_length=10)


Question = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]
Label = StrictBool | StrictInt | str


class LabItem(StrictModel):
    id: NonEmpty
    prompt: NonEmpty
    answer: NonEmpty
    reference: str | None = None
    evidence: str | None = None
    labels: dict[str, Label] = Field(default_factory=dict)

    def state(self) -> dict[str, str | None]:
        return {
            "prompt": self.prompt,
            "answer": self.answer,
            "reference": self.reference,
            "evidence": self.evidence,
        }


class LabConfig(StrictModel):
    items: list[LabItem] = Field(min_length=1, max_length=50)
    questions: list[Question] = Field(min_length=1, max_length=20)
    judge_ids: list[NonEmpty] = Field(min_length=1)
    baseline_model_id: NonEmpty | None = None

    @model_validator(mode="after")
    def validate_identifiers_and_labels(self) -> LabConfig:
        questions = {question.id: question for question in self.questions}
        if len(questions) != len(self.questions):
            raise ValueError("question IDs must be unique")
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("item IDs must be unique")
        if len(set(self.judge_ids)) != len(self.judge_ids):
            raise ValueError("judge IDs must be unique")
        for item in self.items:
            for question_id, label in item.labels.items():
                question = questions.get(question_id)
                if question is None:
                    raise ValueError(f"unknown label question: {question_id}")
                if isinstance(question, NoulQuestion) and type(label) is not bool:
                    raise ValueError(f"label for {question_id} must be Boolean")
                if isinstance(question, ChoiceQuestion) and (
                    not isinstance(label, str) or label not in question.criteria
                ):
                    raise ValueError(f"label for {question_id} must name an option")
                if isinstance(question, ScoreQuestion) and (
                    type(label) is not int or not 0 <= label < len(question.criteria)
                ):
                    raise ValueError(f"label for {question_id} must be a valid level")
        return self


class NoulAnswer(StrictModel):
    type: Literal["noul"]
    probability: Probability | None = None
    verdict: bool | None = None
    rationale: str | None = None


class ChoiceAnswer(StrictModel):
    type: Literal["choice"]
    value: NonEmpty
    probabilities: dict[str, Probability] | None = None
    confidence: Probability | None = None
    rationale: str | None = None


class ScoreAnswer(StrictModel):
    type: Literal["score"]
    value: Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
    normalized: Probability
    probabilities: list[Probability] | None = None
    confidence: Probability | None = None
    rationale: str | None = None

    @classmethod
    def from_raw(cls, value: float, level_count: int, **kwargs: object) -> ScoreAnswer:
        if not 2 <= level_count <= 10 or not 0 <= value <= level_count - 1:
            raise ValueError("score must be within the ordered levels")
        return cls(type="score", value=value, normalized=value / (level_count - 1), **kwargs)


Answer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]


class DecisionError(StrictModel):
    code: NonEmpty
    message: NonEmpty


class DecisionUsage(StrictModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    latency_ms: int | None = Field(default=None, ge=0)
    attempts: int = Field(default=1, ge=0)


class Judgment(StrictModel):
    item_id: NonEmpty
    judge_id: NonEmpty
    requested_model: NonEmpty
    returned_model: str | None = None
    answers: dict[str, Answer] = Field(default_factory=dict)
    raw_answers: dict[str, dict] = Field(default_factory=dict)
    question_errors: dict[str, DecisionError] = Field(default_factory=dict)
    error: DecisionError | None = None
    usage: DecisionUsage = Field(default_factory=DecisionUsage)
    simulated: bool = False


class LabRun(StrictModel):
    id: NonEmpty
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    config: LabConfig
    results: list[Judgment] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    completed: int = Field(default=0, ge=0)
    error: DecisionError | None = None


class InputExchange(StrictModel):
    version: Literal[1]
    kind: Literal["decision-lab-input"]
    config: LabConfig


class ResultExchange(StrictModel):
    version: Literal[1]
    kind: Literal["decision-lab-result"]
    run: LabRun
    thresholds: dict[str, Probability] = Field(default_factory=dict)
