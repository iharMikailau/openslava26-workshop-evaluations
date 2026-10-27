from fastapi.testclient import TestClient

from workshop_evals.adapters.inbound.http.app import build_container, create_app
from workshop_evals.config.settings import Settings


def setup_client():
    return TestClient(create_app(build_container(Settings(fake_llm=True))))


def input_config():
    return {
        "items": [{"id": "one", "prompt": "Q", "answer": "A", "labels": {"ok": True}}],
        "questions": [{"id": "ok", "type": "noul", "instructions": "Supported?"}],
        "judge_ids": ["jev-1-14", "gpt-6-luna-decisions"],
    }


def test_catalog_generation_and_run(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with setup_client() as client:
        judges = client.get("/api/decision-judges").json()
        assert len(judges) == 3 and all(not judge["key_configured"] for judge in judges)
        generated = client.post(
            "/api/decision-lab/generate", json={"model_id": "qwen3-4b", "prompt": "Q"}
        )
        assert generated.status_code == 200 and generated.json()["text"]
        created = client.post("/api/decision-lab/runs", json=input_config())
        assert created.status_code == 202
        run = client.get("/api/decision-lab/runs/" + created.json()["id"]).json()
        assert run["status"] == "completed" and run["completed"] == 2
        assert all(result["simulated"] for result in run["results"])


def test_invalid_missing_and_oversized():
    with setup_client() as client:
        assert client.get("/api/decision-lab/runs/missing").status_code == 404
        assert (
            client.post(
                "/api/decision-lab/generate", json={"model_id": "qwen3-4b", "case_id": "missing"}
            ).status_code
            == 404
        )
        invalid = input_config()
        invalid["items"][0]["labels"]["ok"] = "yes"
        assert client.post("/api/decision-lab/runs", json=invalid).status_code == 422
        assert (
            client.post("/api/decision-lab/runs", content=b" " * (1024 * 1024 + 1)).status_code
            == 413
        )


def test_live_missing_key_and_partial_demo_error(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with TestClient(create_app(build_container(Settings(fake_llm=False)))) as client:
        created = client.post("/api/decision-lab/runs", json=input_config())
        result = client.get("/api/decision-lab/runs/" + created.json()["id"]).json()
        assert all(row["error"]["code"] == "missing_key" for row in result["results"])
    with setup_client() as client:
        config = input_config()
        config["questions"][0]["id"] = "demo-error"
        config["items"][0]["labels"] = {}
        config["judge_ids"] = ["jev-1-14", "microsoft-decision-1"]
        created = client.post("/api/decision-lab/runs", json=config)
        result = client.get("/api/decision-lab/runs/" + created.json()["id"]).json()
        assert result["results"][0]["answers"] and result["results"][1]["question_errors"]
