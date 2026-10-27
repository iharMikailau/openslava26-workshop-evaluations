from workshop_evals.domain.decision_catalog import DECISION_MODELS


def test_catalogue_is_separate_and_uses_one_shared_key():
    assert {model.model_id for model in DECISION_MODELS} == {
        "typesafe/jev-1.14", "openai/gpt-6-luna-decisions", "microsoft/microsoft-decision-1"
    }
    assert {model.api_key_env for model in DECISION_MODELS} == {"OPENROUTER_API_KEY"}
    assert len({model.id for model in DECISION_MODELS}) == 3


def test_decision_models_are_not_in_shipped_chat_catalogue(tmp_path):
    from pathlib import Path

    from workshop_evals.adapters.outbound.yaml_env_catalog import YamlModelCatalog

    catalogue = YamlModelCatalog(Path("data/models.yaml"), tmp_path / "overlay.yaml")
    chat_models = {model.model_id for model in catalogue.all_models()}
    assert chat_models.isdisjoint(model.model_id for model in DECISION_MODELS)
