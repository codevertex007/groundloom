import { defineConfig, devices } from "@playwright/test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const apiPort = Number(process.env.E2E_API_PORT || 8010);
const webPort = Number(process.env.E2E_WEB_PORT || 5174);
const runId = `${process.pid}`;
const directory = dirname(fileURLToPath(import.meta.url));
const root = resolve(directory, "..");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: [
    {
      command: `${process.env.PYTHON || "python"} -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: root,
      url: `http://127.0.0.1:${apiPort}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        PYTHONPATH: resolve(root, "backend"),
        GROUNDLOOM_ENV: "test",
        GROUNDLOOM_DATABASE_URL: `sqlite:///./backend/data/playwright-${runId}.db`,
        GROUNDLOOM_OBJECT_STORE_PATH: `./backend/data/playwright-${runId}-objects`,
        GROUNDLOOM_CORS_ORIGINS: `http://127.0.0.1:${webPort}`,
        GROUNDLOOM_PUBLIC_BASE_URL: `http://127.0.0.1:${apiPort}`,
        GROUNDLOOM_LOCAL_USER_ID: "local-user",
        GROUNDLOOM_LOCAL_WORKSPACE_ID: "local-workspace",
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
      cwd: directory,
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        VITE_API_URL: `http://127.0.0.1:${apiPort}`,
      },
    },
  ],
});
