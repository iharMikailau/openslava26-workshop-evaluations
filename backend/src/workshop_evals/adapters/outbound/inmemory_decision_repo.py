"""Process-local snapshots of decision lab runs."""

from workshop_evals.domain.decision_lab import LabRun


class InMemoryDecisionRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, LabRun] = {}

    def save(self, run: LabRun) -> None:
        self._runs[run.id] = run.model_copy(deep=True)

    def get(self, run_id: str) -> LabRun | None:
        run = self._runs.get(run_id)
        return run.model_copy(deep=True) if run else None
