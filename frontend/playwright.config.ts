import { defineConfig, devices } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { tmpdir } from "node:os";
import path from "node:path";
import { loadEnv } from "vite";

// The E2E suite runs the real API wired to the offline demo client, so scores are
// deterministic and no model or API key is needed. Ports come from BACKEND_PORT and
// FRONTEND_PORT (environment or frontend/.env), the same variables the dev server reads.
const env = { ...loadEnv("development", process.cwd(), ""), ...process.env };
const backendPort = env.BACKEND_PORT || "8000";
const frontendUrl = `http://localhost:${env.FRONTEND_PORT || "5173"}`;
const e2eModelsOverlay = path.join(tmpdir(), `workshop-evals-models-${randomUUID()}.yaml`);
const e2eDatasetsOverlay = path.join(tmpdir(), `workshop-evals-datasets-${randomUUID()}.json`);

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 1,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: frontendUrl,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // Per-run overlays keep model add/remove in the suite from touching the
      // real gitignored runtime catalogues. Provider keys are cleared
      // so credential tests start from a known "no key" state.
      command:
        `OPENAI_API_KEY= OPENROUTER_API_KEY= ANTHROPIC_API_KEY= WORKSHOP_EVALS_FAKE_LLM=1 WORKSHOP_EVALS_MODELS_OVERLAY=${e2eModelsOverlay} WORKSHOP_EVALS_DATASETS_OVERLAY=${e2eDatasetsOverlay} ../backend/.venv/bin/uvicorn workshop_evals.adapters.inbound.http.app:app --host 127.0.0.1 --port ${backendPort}`,
      url: `http://127.0.0.1:${backendPort}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "COVERAGE=1 npm run dev",
      url: frontendUrl,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
