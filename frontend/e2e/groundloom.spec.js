import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("creates a project, runs the persistent collaborator, reviews, and accepts a proposal", async ({ page }) => {
  const projectName = `Playwright project ${Date.now()}`;
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

  await page.locator(".page-header").getByRole("button", { name: "New Project", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Start a grounded workspace" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Project name").fill(projectName);
  await dialog.getByLabel("Project brief").fill("Create a concise grounded guide for field operators.");
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();

  await expect(page.getByText(projectName, { exact: true })).toBeVisible();
  const composer = page.getByRole("textbox", { name: "Ask Copilot, or describe a change…" });
  await composer.fill("Draft the first grounded section.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("PROPOSED CHANGE", { exact: true })).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: "Accept changes", exact: true }).click();
  await page.getByRole("button", { name: /^Content/ }).click();
  await expect(page.getByText("Content is empty", { exact: true })).not.toBeVisible();
});

test("persists settings and exposes the command palette navigation", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "Settings" });
  await expect(settings).toBeVisible();
  const initialVersion = await settings.locator("small.muted").innerText();
  const budget = settings.getByLabel("Daily token budget");
  await budget.fill("100123");
  await settings.getByRole("button", { name: "Save settings", exact: true }).click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const reopened = page.getByRole("dialog", { name: "Settings" });
  await expect(reopened.getByLabel("Daily token budget")).toHaveValue("100123");
  await expect(reopened.locator("small.muted")).not.toHaveText(initialVersion);
  await reopened.getByRole("button", { name: "Close settings dialog" }).click();

  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await palette.getByRole("button", { name: "Open Sources" }).click();
  await expect(page.getByRole("heading", { name: "Sources", exact: true })).toBeVisible();
});

test("projects surface has no serious or critical accessibility violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact));
  expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
});
