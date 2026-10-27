import json
from pathlib import Path

from workshop_evals.adapters.outbound.fake_llm_client import FakeLLMClient
from workshop_evals.adapters.outbound.yaml_env_catalog import YamlModelCatalog
from workshop_evals.application.services.decision_baseline import DecisionChatService
from workshop_evals.domain.decision_lab import NoulQuestion, ScoreQuestion


async def test_generation_and_typed_baseline_keep_labels_out(tmp_path):
    prompts = []

    def handler(model, messages, params):
        prompts.append(messages[-1]["content"])
        if len(prompts) == 1:
            return "Generated once"
        return json.dumps(
            {
                "ok": {"value": True, "rationale": "supported", "confidence": 1},
                "score": {"value": 1},
            }
        )

    catalogue = YamlModelCatalog(Path("data/models.yaml"), tmp_path / "overlay.yaml")
    model = catalogue.list_models()[0]
    service = DecisionChatService(FakeLLMClient(handler=handler), catalogue)
    completion = await service.generate(model.id, "Question")
    questions = [
        NoulQuestion(id="ok", type="noul", instructions="Supported?"),
        ScoreQuestion(id="score", type="score", instructions="Quality?", criteria=["Bad", "Good"]),
    ]
    result = await service.judge(
        model.id, "one", {"prompt": "Question", "answer": completion.text}, questions
    )
    assert len(prompts) == 2 and "labels" not in prompts[1]
    assert result.answers["ok"].verdict is True and result.answers["ok"].probability is None
    assert result.answers["score"].normalized == 1 and result.usage.cost_usd is None
    assert "confidence" not in type(result.answers["ok"]).model_fields


async def test_malformed_baseline_is_error(tmp_path):
    catalogue = YamlModelCatalog(Path("data/models.yaml"), tmp_path / "overlay.yaml")
    model = catalogue.list_models()[0]
    service = DecisionChatService(FakeLLMClient(default="not JSON"), catalogue)
    result = await service.judge(
        model.id, "one", {}, [NoulQuestion(id="ok", type="noul", instructions="OK?")]
    )
    assert result.error.code == "invalid_baseline"


async def test_demo_baseline_is_simulated(tmp_path):
    from workshop_evals.adapters.outbound.demo_client import make_demo_client

    catalogue = YamlModelCatalog(Path("data/models.yaml"), tmp_path / "overlay.yaml")
    model = catalogue.list_models()[0]
    service = DecisionChatService(make_demo_client(), catalogue, simulated=True)
    result = await service.judge(
        model.id, "one", {}, [NoulQuestion(id="ok", type="noul", instructions="OK?")]
    )
    assert result.simulated and result.answers["ok"].verdict is True
