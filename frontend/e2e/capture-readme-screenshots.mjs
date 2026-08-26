// One-off capture script for README screenshots. Not part of the test
// suite: run manually with `node e2e/capture-readme-screenshots.mjs` from
// frontend/. Boots real backend + frontend dev servers against an isolated
// throwaway sqlite db (mirrors playwright.config.js's webServer setup),
// drives the real UI through the same flow as the e2e spec, and saves PNGs.
import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const directory = dirname(fileURLToPath(import.meta.url));
const root = resolve(directory, "..", "..");
const outDir = resolve(root, "docs", "assets", "screenshots");
mkdirSync(outDir, { recursive: true });

const apiPort = 8090;
const webPort = 5190;
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

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`http://127.0.0.1:${webPort}`);
  await page.getByRole("heading", { name: "Projects" }).waitFor();
  await page.evaluate(() => document.fonts?.ready);

  await page.screenshot({ path: resolve(outDir, "projects-empty.png") });

  const projectName = "Caffeine and Sleep Quality";
  await page.locator(".page-header").getByRole("button", { name: "New Project", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Start a grounded workspace" });
  await dialog.waitFor();
  await dialog.getByLabel("Project name").fill(projectName);
  await dialog
    .getByLabel("Project brief")
    .fill("Investigate how caffeine timing affects sleep quality and summarize the evidence for a general audience.");
  const activeSkill = dialog.locator(".select-list").nth(1).getByRole("button").first();
  await activeSkill.waitFor();
  await activeSkill.click();
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();

  await page.getByText(projectName, { exact: true }).waitFor();
  const composer = page.getByRole("textbox", { name: "Ask Copilot, or describe a change…" });
  await composer.fill("Draft the first grounded section on caffeine timing and sleep quality.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page.getByText("PROPOSED CHANGE", { exact: true }).waitFor({ timeout: 20_000 });
  await page.waitForTimeout(400);

  await page.screenshot({ path: resolve(outDir, "workspace-proposal.png") });

  await page.getByRole("button", { name: "Accept changes", exact: true }).click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: resolve(outDir, "workspace-accepted.png") });

  await browser.close();
  killAll();
  console.log("Saved screenshots to", outDir);
}

main().catch((err) => {
  console.error(err);
  killAll();
  process.exit(1);
});
