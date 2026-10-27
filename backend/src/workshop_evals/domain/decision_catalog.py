"""Static catalogue of models that implement the Decisions API, not chat."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionModel:
    id: str
    display_name: str
    model_id: str
    api_key_env: str = "OPENROUTER_API_KEY"


DECISION_MODELS = (
    DecisionModel("jev-1-14", "TypeSafe: Jev 1.14", "typesafe/jev-1.14"),
    DecisionModel(
        "gpt-6-luna-decisions", "OpenAI: GPT-6 Luna Decisions", "openai/gpt-6-luna-decisions"
    ),
    DecisionModel(
        "microsoft-decision-1", "Microsoft: Microsoft-Decision-1", "microsoft/microsoft-decision-1"
    ),
)
