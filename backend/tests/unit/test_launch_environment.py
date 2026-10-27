from __future__ import annotations

import os

from workshop_evals.application.services.model_management import ModelManagementService
from workshop_evals.config.settings import load_launch_environment


def test_launch_environment_loads_file_key_and_preserves_exported_value(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=file-key\nFILE_ONLY=loaded\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("FILE_ONLY", raising=False)

    load_launch_environment(tmp_path)

    assert os.environ["OPENROUTER_API_KEY"] == "file-key"
    assert os.environ["FILE_ONLY"] == "loaded"


def test_launch_environment_prefers_process_environment(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "environment-key")

    load_launch_environment(tmp_path)

    assert os.environ["OPENROUTER_API_KEY"] == "environment-key"


def test_session_key_update_is_shared_and_blank_key_is_not_detected(tmp_path, monkeypatch):
    from workshop_evals.adapters.outbound.yaml_env_catalog import YamlModelCatalog

    base = tmp_path / "models.yaml"
    base.write_text(
        "models:\n"
        "  - id: gpt\n    display_name: GPT\n    model_id: openai/gpt\n"
        "    provider: openai_compat\n    base_url: https://openrouter.ai/api/v1\n"
        "    api_key_env: OPENROUTER_API_KEY\n"
        "  - id: claude\n    display_name: Claude\n    model_id: anthropic/claude\n"
        "    provider: openai_compat\n    base_url: https://openrouter.ai/api/v1\n"
        "    api_key_env: OPENROUTER_API_KEY\n"
        "  - id: deepseek\n    display_name: DeepSeek\n    model_id: deepseek/flash\n"
        "    provider: openai_compat\n    base_url: https://openrouter.ai/api/v1\n"
        "    api_key_env: OPENROUTER_API_KEY\n"
        "  - id: qwen\n    display_name: Qwen\n    model_id: qwen/max\n"
        "    provider: openai_compat\n    base_url: https://openrouter.ai/api/v1\n"
        "    api_key_env: OPENROUTER_API_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "   ")
    service = ModelManagementService(YamlModelCatalog(base), lambda _: None)

    assert all(not model["key_detected"] for model in service.list_all())
    service.set_credential("OPENROUTER_API_KEY", "session-key")
    assert service.credential_status("OPENROUTER_API_KEY")
    assert all(model["key_detected"] for model in service.list_all())
