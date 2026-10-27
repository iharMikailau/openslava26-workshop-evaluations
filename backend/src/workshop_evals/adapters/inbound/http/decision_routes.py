"""HTTP boundary for the decision lab."""

import json
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from workshop_evals.domain.decision_catalog import DECISION_MODELS
from workshop_evals.domain.decision_lab import LabConfig, LabRun
from workshop_evals.domain.models import Completion

router = APIRouter(prefix="/api")
MAX_BYTES = 1024 * 1024


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1)
    prompt: str | None = None
    case_id: str | None = None

    @model_validator(mode="after")
    def check_input(self):
        if bool(self.prompt and self.prompt.strip()) == bool(self.case_id and self.case_id.strip()):
            raise ValueError("Provide exactly one prompt or case ID")
        return self


async def _body(request: Request, schema: type[BaseModel]) -> BaseModel:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="Request exceeds 1 MiB")
    try:
        return schema.model_validate_json(bytes(body))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_context=False)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid JSON") from exc


@router.get("/decision-judges")
def decision_judges() -> list[dict]:
    return [
        {
            "id": model.id,
            "display_name": model.display_name,
            "model_id": model.model_id,
            "api_key_env": model.api_key_env,
            "key_configured": bool(os.environ.get(model.api_key_env, "").strip()),
        }
        for model in DECISION_MODELS
    ]


@router.post("/decision-lab/generate", response_model=Completion)
async def generate(request: Request) -> Completion:
    req = await _body(request, GenerateRequest)
    assert isinstance(req, GenerateRequest)
    container = request.app.state.container
    if req.case_id:
        case = container.datasets.get_case(req.case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Unknown case")
        prompt = case.prompt
    else:
        prompt = req.prompt or ""
    try:
        return await container.decision_chat.generate(req.model_id, prompt)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/decision-lab/runs", response_model=LabRun, status_code=202)
async def create_run(request: Request, background: BackgroundTasks) -> LabRun:
    config = await _body(request, LabConfig)
    assert isinstance(config, LabConfig)
    service = request.app.state.container.decision_lab
    try:
        run = service.create_run(config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background.add_task(service.execute_run, run.id)
    return run


@router.get("/decision-lab/runs/{run_id}", response_model=LabRun)
def get_run(run_id: str, request: Request) -> LabRun:
    run = request.app.state.container.decision_lab.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown decision run")
    return run
