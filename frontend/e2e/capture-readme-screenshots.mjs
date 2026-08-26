// One-off capture script for README screenshots. Not part of the test
// suite: run manually with `node e2e/capture-readme-screenshots.mjs` from
// frontend/. Boots real backend + frontend dev servers against an isolated
// throwaway sqlite db (mirrors playwright.config.js's webServer setup),
// drives the real UI and API together, and saves a PNG.
import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const directory = dirname(fileURLToPath(import.meta.url));
const root = resolve(directory, "..", "..");
const outDir = resolve(root, "docs", "assets", "screenshots");
mkdirSync(outDir, { recursive: true });

const apiPort = 8091;
const webPort = 5191;
const runId = Date.now();

function waitForUrl(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolvePromise, reject) => {
    const attempt = async () => {
      try {
        const response = await fetch(url);
        if (response.ok) return resolvePromise();
      } catch {
        // not up yet
      }
      if (Date.now() > deadline) return reject(new Error(`Timed out waiting for ${url}`));
      setTimeout(attempt, 500);
    };
    attempt();
  });
}

const children = [];
function spawnServer(command, args, opts) {
  const child = spawn(command, args, { ...opts, stdio: "inherit" });
  children.push(child);
  return child;
}

function killAll() {
  for (const child of children) {
    try {
      child.kill();
    } catch {
      // already dead
    }
  }
}

process.on("exit", killAll);

const apiHeaders = {
  "Content-Type": "application/json",
  "X-User-ID": "local-user",
  "X-Workspace-ID": "local-workspace",
};

async function apiPost(path, body) {
  const response = await fetch(`http://127.0.0.1:${apiPort}${path}`, {
    method: "POST",
    headers: apiHeaders,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`POST ${path} -> ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

async function apiGet(path) {
  const response = await fetch(`http://127.0.0.1:${apiPort}${path}`, { headers: apiHeaders });
  if (!response.ok) {
    throw new Error(`GET ${path} -> ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

async function main() {
  const python = process.env.PYTHON || "python";
  spawnServer(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(apiPort)], {
    cwd: root,
    env: {
      ...process.env,
      PYTHONPATH: resolve(root, "backend"),
      GROUNDLOOM_ENV: "test",
      GROUNDLOOM_DATABASE_URL: `sqlite:///./backend/data/screenshot-${runId}.db`,
      GROUNDLOOM_OBJECT_STORE_PATH: `./backend/data/screenshot-${runId}-objects`,
      GROUNDLOOM_CORS_ORIGINS: `http://127.0.0.1:${webPort}`,
      GROUNDLOOM_PUBLIC_BASE_URL: `http://127.0.0.1:${apiPort}`,
      GROUNDLOOM_LOCAL_USER_ID: "local-user",
      GROUNDLOOM_LOCAL_WORKSPACE_ID: "local-workspace",
    },
  });
  await waitForUrl(`http://127.0.0.1:${apiPort}/health`, 60_000);

  spawnServer("npm", ["run", "dev", "--", "--host", "127.0.0.1", "--port", String(webPort)], {
    cwd: directory.replace(/e2e$/, ""),
    shell: true,
    env: { ...process.env, VITE_API_URL: `http://127.0.0.1:${apiPort}` },
  });
  await waitForUrl(`http://127.0.0.1:${webPort}`, 60_000);
  await new Promise((r) => setTimeout(r, 1500));

  // Build a project with real content through the same patch API a real
  // agent run proposes through, so the screenshot shows genuine typed
  // blocks (including the warning/note/objective_list callouts) rather
  // than hand-authored HTML.
  const project = await apiPost("/v1/projects", {
    name: "Turbine Field Service Certification",
    project_type: "knowledge_brief",
    brief: "Certification guide for field technicians servicing turbine units.",
  });
  const patch = await apiPost(`/v1/projects/${project.id}/patches`, {
    base_content_version_id: project.current_content_version_id,
    summary: "Turbine disassembly module",
    operations: [
      { op: "insert_after", payload: { block_type: "heading", text: "Turbine Disassembly" } },
      {
        op: "insert_after",
        payload: {
          block_type: "paragraph",
          text: "Safely disassembling the turbine module in preparation for inspection, following the manufacturer sequence and applicable electrical-safety standards.",
        },
      },
      {
        op: "insert_after",
        payload: {
          block_type: "objective_list",
          items: [
            "Apply lockout/tagout before beginning disassembly",
            "Remove the turbine casing in the specified sequence",
            "Extract and tag the rotor assembly without damage",
          ],
        },
      },
      {
        op: "insert_after",
        payload: {
          block_type: "warning",
          text: "Confirm the unit is de-energized and mechanically locked out. Residual rotor spin can cause severe injury.",
        },
      },
      {
        op: "insert_after",
        payload: {
          block_type: "note",
          text: "Calibration stickers must be current before use. Stage all tools on the service cart to maintain a clear egress path.",
        },
      },
    ],
  });
  await apiPost(`/v1/patches/${patch.id}/accept`, {
    expected_current_version_id: project.current_content_version_id,
  });
  await apiGet(`/v1/projects/${project.id}/content`);

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`http://127.0.0.1:${webPort}`);
  await page.getByRole("heading", { name: "Projects" }).waitFor();
  await page.evaluate(() => document.fonts?.ready);

  await page.getByText(project.name, { exact: true }).waitFor();
  await page.getByText(project.name, { exact: true }).click();
  await page.getByRole("button", { name: "Content", exact: true }).click();
  await page.getByText("Turbine Disassembly", { exact: true }).waitFor();
  await page.waitForTimeout(500);

  await page.screenshot({ path: resolve(outDir, "workspace-content.png") });

  await browser.close();
  killAll();
  console.log("Saved screenshot to", outDir);
}

main().catch((err) => {
  console.error(err);
  killAll();
  process.exit(1);
});
