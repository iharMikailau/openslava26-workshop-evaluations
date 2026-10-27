# Workshop Evals — Backend

A small, API-first service for running a matrix of **prompts × models × evaluation
mechanisms**. It powers the hands-on workshop on evaluating generative-AI systems and is
built so the frontend (or any client) can drive it over plain HTTP.

## Why Python

The backend is written in Python with FastAPI for three reasons:

1. **Evaluation ecosystem.** The libraries for talking to local and hosted models
   (OpenAI-compatible servers such as Ollama, plus the Anthropic SDK) are first-class in
   Python, and the scoring logic — code execution, SQL execution, statistical agreement —
   is concise and dependency-light in the standard library.
2. **Readability as a teaching tool.** Workshop attendees read this code. Python keeps the
   evaluation mechanisms legible without ceremony.
3. **Clean separation.** FastAPI exposes an OpenAPI contract, so the frontend is a
   replaceable client rather than a coupled component.

## Architecture

Ports and adapters (hexagonal). The domain holds pure scoring logic with no I/O; the
application layer orchestrates use cases through ports; adapters wire in HTTP, model
providers, datasets and storage.

```
src/workshop_evals/
  domain/        pure evaluation logic (scoring, statistics, model types)
  application/   use cases + ports (interfaces)
  adapters/      inbound HTTP (FastAPI) + outbound providers/repositories
  config/        settings
```

## Requirements

- Python 3.11+
- For the free path: [Ollama](https://ollama.com) running locally
- Optional: `OPENROUTER_API_KEY` for the recommended hosted catalogue (paid credits required).
  Direct OpenAI and Anthropic models can be added manually in Models.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
uvicorn workshop_evals.adapters.inbound.http.app:app --reload
```

The interactive API docs are then served at `http://localhost:8000/docs`. Add `--port <n>` to
use another port (or set `WORKSHOP_EVALS_PORT` for the `workshop-evals` launcher), and point the
frontend at it with `BACKEND_PORT=<n>`.

## Test

```bash
pytest                 # unit + integration (no network, no model calls)
pytest -m real_llm     # opt-in: exercises a live local model via Ollama
```

## Configuration

When launching from `backend/`, copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.
The backend loads only that launch-directory `.env`; exported environment values take
precedence. Alternatively, set the key through Models → Session credentials for the current
process. Local Ollama models need no key. To use direct OpenAI or Anthropic models, add them
in Models and set the corresponding key. Runtime catalogue overlays override the base
catalogue by model id. Edit `data/models.yaml` only to change the shipped catalogue.

### Decision judges lab API

`GET /api/decision-judges` lists the separate decision catalogue and shared key status
without making provider requests. `POST /api/decision-lab/generate` takes a chat
`model_id` and either `prompt` or `case_id`; it generates one candidate answer.
For example:

```json
{"model_id": "qwen3-4b", "prompt": "What color is the sky?"}
```

Submit supplied answers to `POST /api/decision-lab/runs`. The response is `202` with
an ID; poll `GET /api/decision-lab/runs/{id}` for progress and partial results:

```json
{
  "items": [{"id": "one", "prompt": "Question", "answer": "Answer", "labels": {"ok": true}}],
  "questions": [{"id": "ok", "type": "noul", "instructions": "Is the answer supported?"}],
  "judge_ids": ["jev-1-14"]
}
```

Human labels are kept out of provider state. Requests to these write endpoints are
limited to 1 MiB. Runs are stored in process memory and disappear on restart; export
results from the lab for later review. Live decision calls use `OPENROUTER_API_KEY`;
demo mode returns clearly marked simulated results without provider calls.
