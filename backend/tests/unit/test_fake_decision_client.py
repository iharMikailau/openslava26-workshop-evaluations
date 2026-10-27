from workshop_evals.adapters.outbound.fake_decision_client import FakeDecisionClient
from workshop_evals.domain.decision_catalog import DECISION_MODELS
from workshop_evals.domain.decision_lab import ChoiceQuestion, NoulQuestion, ScoreQuestion


async def test_simulation_covers_types_disagreement_and_error():
    questions = [
        NoulQuestion(id="ok", type="noul", instructions="Supported?"),
        NoulQuestion(id="demo-error", type="noul", instructions="Simulated failure?"),
        ChoiceQuestion(
            id="kind", type="choice", instructions="Which?", criteria={"a": "A", "b": "B"}
        ),
        ScoreQuestion(id="score", type="score", instructions="Quality?", criteria=["Low", "High"]),
    ]
    client = FakeDecisionClient()
    results = [await client.decide(m, "item", {}, questions) for m in DECISION_MODELS]
    assert all(result.simulated for result in results)
    assert results[0].answers["ok"].probability != results[1].answers["ok"].probability
    assert results[0].answers["kind"].value == "a"
    assert results[0].answers["score"].normalized == 0.25
    assert results[2].question_errors["demo-error"].code == "simulated_error"


def test_demo_and_injected_clients_are_bound():
    from workshop_evals.adapters.inbound.http.app import build_container
    from workshop_evals.config.settings import Settings

    fake = FakeDecisionClient()
    assert isinstance(build_container(Settings(fake_llm=True)).decision_client, FakeDecisionClient)
    assert build_container(Settings(fake_llm=False), decision_client=fake).decision_client is fake
