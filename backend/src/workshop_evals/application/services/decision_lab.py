"""Orchestrate serial decision judgments over frozen supplied answers."""

import uuid

from workshop_evals.application.ports.decision_lab import (
    DecisionClientPort,
    DecisionRunRepositoryPort,
)
from workshop_evals.application.services.decision_baseline import DecisionChatService
from workshop_evals.domain.decision_catalog import DECISION_MODELS
from workshop_evals.domain.decision_lab import DecisionError, LabConfig, LabRun


class DecisionLabService:
    def __init__(
        self,
        client: DecisionClientPort,
        runs: DecisionRunRepositoryPort,
        chat: DecisionChatService | None = None,
    ) -> None:
        self._client = client
        self._runs = runs
        self._chat = chat
        self._models = {model.id: model for model in DECISION_MODELS}

    def create_run(self, config: LabConfig) -> LabRun:
        if any(judge not in self._models for judge in config.judge_ids):
            raise ValueError("Unknown decision judge")
        if config.baseline_model_id and self._chat is None:
            raise ValueError("Baseline is unavailable")
        if config.baseline_model_id and self._chat:
            self._chat.validate_baseline(config.baseline_model_id)
        run = LabRun(
            id=uuid.uuid4().hex,
            config=config.model_copy(deep=True),
            total=len(config.items) * (len(config.judge_ids) + bool(config.baseline_model_id)),
        )
        self._runs.save(run)
        return run.model_copy(deep=True)

    def get_run(self, run_id: str) -> LabRun | None:
        return self._runs.get(run_id)

    async def execute_run(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        run.status = "running"
        self._runs.save(run)
        try:
            for item in run.config.items:
                for judge in run.config.judge_ids:
                    result = await self._client.decide(
                        self._models[judge],
                        item.id,
                        item.state(),
                        [q.model_copy(deep=True) for q in run.config.questions],
                    )
                    run.results.append(result)
                    run.completed += 1
                    self._runs.save(run)
                if run.config.baseline_model_id and self._chat:
                    result = await self._chat.judge(
                        run.config.baseline_model_id,
                        item.id,
                        item.state(),
                        [q.model_copy(deep=True) for q in run.config.questions],
                    )
                    run.results.append(result)
                    run.completed += 1
                    self._runs.save(run)
            run.status = "completed"
        except Exception:
            run.status = "failed"
            run.error = DecisionError(
                code="orchestration_error", message="Decision run failed unexpectedly."
            )
        self._runs.save(run)
