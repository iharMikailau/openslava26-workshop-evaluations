from workshop_evals.adapters.outbound.fake_decision_client import FakeDecisionClient
from workshop_evals.adapters.outbound.inmemory_decision_repo import InMemoryDecisionRunRepository
from workshop_evals.application.services.decision_lab import DecisionLabService
from workshop_evals.domain.decision_lab import LabConfig


class RecordingClient(FakeDecisionClient):
    def __init__(self, repo):
        self.repo = repo
        self.calls = []
        self.progress = []

    async def decide(self, model, item_id, state, questions):
        self.progress.append(next(iter(self.repo._runs.values())).completed)
        self.calls.append((model.id, item_id, state, questions))
        return await super().decide(model, item_id, state, questions)


async def test_serial_snapshot_and_no_labels():
    repo = InMemoryDecisionRunRepository()
    client = RecordingClient(repo)
    service = DecisionLabService(client, repo)
    config = LabConfig.model_validate(
        {
            "items": [{"id": "one", "prompt": "Q", "answer": "A", "labels": {"ok": True}}],
            "questions": [{"id": "ok", "type": "noul", "instructions": "Supported?"}],
            "judge_ids": ["jev-1-14", "gpt-6-luna-decisions"],
        }
    )
    run = service.create_run(config)
    config.items[0].answer = "edited"
    await service.execute_run(run.id)
    finished = service.get_run(run.id)
    assert finished.status == "completed" and finished.completed == finished.total == 2
    assert len(client.calls) == 2
    assert client.progress == [0, 1]
    assert client.calls[0][2] == client.calls[1][2]
    assert client.calls[0][2]["answer"] == "A" and "labels" not in client.calls[0][2]
    assert client.calls[0][3] == client.calls[1][3]
    assert finished.config.items[0].answer == "A"
    finished.config.items[0].answer = "changed"
    assert service.get_run(run.id).config.items[0].answer == "A"


async def test_unexpected_failure_retains_partial_results():
    repo = InMemoryDecisionRunRepository()

    class FailingClient(RecordingClient):
        async def decide(self, model, item_id, state, questions):
            if self.calls:
                raise RuntimeError("secret")
            return await super().decide(model, item_id, state, questions)

    service = DecisionLabService(FailingClient(repo), repo)
    config = LabConfig.model_validate(
        {
            "items": [{"id": "one", "prompt": "Q", "answer": "A"}],
            "questions": [{"id": "ok", "type": "noul", "instructions": "Supported?"}],
            "judge_ids": ["jev-1-14", "gpt-6-luna-decisions"],
        }
    )
    run = service.create_run(config)
    await service.execute_run(run.id)
    finished = service.get_run(run.id)
    assert finished.status == "failed" and finished.completed == 1 and len(finished.results) == 1
    assert "secret" not in finished.model_dump_json()
