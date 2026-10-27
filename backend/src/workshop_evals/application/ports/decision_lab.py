"""Driven ports for decision judgments and process-local lab runs."""

from typing import Protocol

from workshop_evals.domain.decision_catalog import DecisionModel
from workshop_evals.domain.decision_lab import Judgment, LabRun, Question


class DecisionClientPort(Protocol):
    async def decide(
        self, model: DecisionModel, item_id: str, state: dict[str, str | None],
        questions: list[Question],
    ) -> Judgment: ...


class DecisionRunRepositoryPort(Protocol):
    def save(self, run: LabRun) -> None: ...

    def get(self, run_id: str) -> LabRun | None: ...
