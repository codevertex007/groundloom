import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("matches stable projects and sources empty-state baselines", async ({ page }) => {
  test.skip(process.platform !== "win32", "Committed visual baselines use the pinned Windows Chromium lane");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await page.evaluate(() => document.fonts?.ready);
  await expect(page.locator(".app-shell")).toHaveScreenshot("projects-empty.png", {
    animations: "disabled",
    caret: "hide",
  });

  await page.getByRole("button", { name: "Sources", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sources", exact: true })).toBeVisible();
  await expect(page.locator(".app-shell")).toHaveScreenshot("sources-empty.png", {
    animations: "disabled",
    caret: "hide",
  });
});

test("creates a project, runs the persistent collaborator, reviews, and accepts a proposal", async ({
  page,
}) => {
  const projectName = `Playwright project ${Date.now()}`;
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

  await page
    .locator(".page-header")
    .getByRole("button", { name: "New Project", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Start a grounded workspace",
  });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Project name").fill(projectName);
  await dialog
    .getByLabel("Project brief")
    .fill("Create a concise grounded guide for field operators.");
  const activeSkill = dialog.locator(".select-list").nth(1).getByRole("button").first();
  await expect(activeSkill).toBeVisible();
  await activeSkill.click();
  await expect(activeSkill).toHaveAttribute("aria-pressed", "true");
  await dialog
    .getByRole("button", { name: "Create project", exact: true })
    .click();

  await expect(page.getByText(projectName, { exact: true })).toBeVisible();
  const composer = page.getByRole("textbox", {
    name: "Ask Copilot, or describe a change…",
  });
  await composer.fill("Draft the first grounded section.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("PROPOSED CHANGE", { exact: true })).toBeVisible({
    timeout: 15_000,
  });
  await expect(
    page.getByText(/Run (completed|running|queued)/),
  ).toBeVisible();

  await page
    .getByRole("button", { name: "Accept changes", exact: true })
    .click();
  await page.getByRole("button", { name: /^Content/ }).click();
  await page.getByRole("button", { name: "Review", exact: true }).click();
  const review = page.getByRole("dialog", { name: "Validation checklist" });
  await expect(review.getByText("Ready for review", { exact: true })).toBeVisible();
  await review.getByRole("button", { name: "Done", exact: true }).click();
  await expect(
    page.getByText("Content is empty", { exact: true }),
  ).not.toBeVisible();
});

test("rejects a proposed change without changing canonical content", async ({
  page,
}) => {
  const projectName = `Rejected project ${Date.now()}`;
  await page.goto("/");
  await page
    .locator(".page-header")
    .getByRole("button", { name: "New Project", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Start a grounded workspace",
  });
  await dialog.getByLabel("Project name").fill(projectName);
  await dialog
    .getByLabel("Project brief")
    .fill("Create a reviewable note that can be rejected safely.");
  await dialog
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page.getByText(projectName, { exact: true })).toBeVisible();

  await page
    .getByRole("textbox", { name: "Ask Copilot, or describe a change…" })
    .fill("Draft a change that the reviewer will reject.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("PROPOSED CHANGE", { exact: true })).toBeVisible({
    timeout: 15_000,
  });
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.getByText("PROPOSED CHANGE", { exact: true })).not.toBeVisible();
  await page.getByRole("button", { name: /^Content/ }).click();
  await expect(page.getByText("Content is empty", { exact: true })).toBeVisible();
});

test("persists settings and exposes the command palette navigation", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "Settings" });
  await expect(settings).toBeVisible();
  const initialVersion = await settings.locator("small.muted").innerText();
  const budget = settings.getByLabel("Daily token budget");
  await budget.fill("100123");
  await settings
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const reopened = page.getByRole("dialog", { name: "Settings" });
  await expect(reopened.getByLabel("Daily token budget")).toHaveValue("100123");
  await expect(reopened.locator("small.muted")).not.toHaveText(initialVersion);
  await reopened.getByRole("button", { name: "Close settings dialog" }).click();

  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await palette.getByRole("button", { name: "Open Sources" }).click();
  await expect(
    page.getByRole("heading", { name: "Sources", exact: true }),
  ).toBeVisible();
});

test("pauses for plan approval and resumes the same collaborator thread", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "Settings" });
  await expect(settings).toBeVisible();
  const approvalToggle = settings.getByLabel("Require plan approval");
  if (!(await approvalToggle.isChecked())) await approvalToggle.check();
  await settings.getByRole("button", { name: "Save settings", exact: true }).click();

  await page.locator(".page-header").getByRole("button", { name: "New Project", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Start a grounded workspace" });
  await dialog.getByLabel("Project name").fill(`Approval project ${Date.now()}`);
  await dialog.getByLabel("Project brief").fill("Create a plan that requires explicit review.");
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();
  await page.getByRole("textbox", { name: "Ask Copilot, or describe a change…" }).fill("Draft a plan for review.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("Plan approval required", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Run waiting_for_approval", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Approve plan", exact: true }).click();
  await expect(page.getByText("PROPOSED CHANGE", { exact: true })).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const cleanup = page.getByRole("dialog", { name: "Settings" });
  await cleanup.getByLabel("Require plan approval").uncheck();
  await cleanup.getByRole("button", { name: "Save settings", exact: true }).click();
});

test("creates, validates, repairs, and publishes an AI-authored skill draft", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Skills", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Skills", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "starter", exact: true }).click();
  const starterCard = page.locator(".skill-card").filter({ hasText: "Source-grounded writing" });
  await expect(starterCard).toBeVisible();
  await starterCard.click();
  await starterCard.getByRole("button", { name: "Fork to workspace", exact: true }).click();
  await page.getByRole("button", { name: "All scopes", exact: true }).click();
  await expect(
    page.locator(".skill-card").filter({ hasText: "Source-grounded writing (fork)" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "AI author draft", exact: true }).click();
  await page.getByLabel("Skill author objective").fill("Create scoped editorial guidance for grounded drafts.");
  const slug = `browser-skill-${Date.now()}`;
  await page.getByLabel("Suggested skill slug").fill(slug);
  await page.getByLabel("Suggested skill name").fill("Browser editorial skill");
  await page.getByRole("button", { name: "Create AI draft", exact: true }).click();

  const card = page.locator(".skill-card").filter({ hasText: "Browser editorial skill" });
  await expect(card).toBeVisible();
  await card.click();
  await expect(card.getByText("draft", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Validate", exact: true }).click();
  await expect(card.getByText("valid", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(card.getByText("published", { exact: true })).toBeVisible();
});

test("shows reconnect state after a dropped activity stream", async ({ page }) => {
  let dropped = false;
  await page.route("**/*", async (route) => {
    if (!route.request().url().includes("/events/stream")) {
      await route.continue();
      return;
    }
    if (!dropped) {
      dropped = true;
      await route.abort("connectionreset");
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
    await route.continue();
  });
  await page.goto("/");
  await page.locator(".page-header").getByRole("button", { name: "New Project", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Start a grounded workspace" });
  await dialog.getByLabel("Project name").fill(`Reconnect project ${Date.now()}`);
  await dialog.getByLabel("Project brief").fill("Reconnect the durable activity stream.");
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();
  await expect.poll(() => dropped, { timeout: 10_000 }).toBe(true);
  await expect(page.locator('[aria-label="Activity stream reconnecting"]')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('[aria-label="Activity stream connected"]')).toBeVisible({ timeout: 15_000 });
});

test("renders a distinct permission-denied state", async ({ page }) => {
  await page.route("**/v1/projects/page*", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({
          code: "PERMISSION_DENIED",
          message: "This workspace is not available to the current identity.",
          retryable: false,
        }),
      });
      return;
    }
    await route.continue();
  });
  await page.goto("/");
  const alert = page.getByRole("alert");
  await expect(alert).toHaveAttribute("data-error-kind", "permission");
  await expect(alert).toContainText("Permission denied");
  await expect(alert.getByRole("button", { name: "Dismiss" })).toBeVisible();
});

test("projects surface has no serious or critical accessibility violations", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((violation) =>
    ["serious", "critical"].includes(violation.impact),
  );
  expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
});

test("uploads evidence, grounds a project, and navigates a citation", async ({
  page,
}) => {
  const projectName = `Evidence project ${Date.now()}`;
  await page.goto("/");
  await page.getByRole("button", { name: "Sources", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sources", exact: true })).toBeVisible();

  await page.locator('input[type="file"]').first().setInputFiles({
    name: "field-guide.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Use 10 Nm for the service fastener. Inspect the seal before torqueing."),
  });
  await expect(page.getByText("field-guide", { exact: true })).toBeVisible();
  await expect(page.getByText("ready", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Open field-guide versions", exact: true }).click();
  const versions = page.getByRole("dialog", { name: "field-guide" });
  await expect(versions.getByText("v1", { exact: true })).toBeVisible();
  await expect(versions.getByRole("button", { name: /Upload source/ })).toBeVisible();
  await versions.locator('input[type="file"]').setInputFiles({
    name: "field-guide-revision.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Use 10 Nm for the service fastener. Inspect the seal before torqueing. Revised."),
  });
  await expect(page.getByText("v2", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await page
    .locator(".page-header")
    .getByRole("button", { name: "New Project", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Start a grounded workspace",
  });
  await dialog.getByLabel("Project name").fill(projectName);
  await dialog
    .getByLabel("Project brief")
    .fill("Create a grounded maintenance note from the field guide.");
  await dialog.locator(".select-list button").filter({ hasText: "field-guide" }).click();
  await dialog.getByRole("button", { name: "Create project", exact: true }).click();

  await expect(page.getByText(projectName, { exact: true })).toBeVisible();
  await page
    .getByRole("textbox", { name: "Ask Copilot, or describe a change…" })
    .fill("Draft a cited maintenance note about the service fastener.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("PROPOSED CHANGE", { exact: true })).toBeVisible({
    timeout: 15_000,
  });
  await page.getByRole("button", { name: "Accept changes", exact: true }).click();
  await page.getByRole("button", { name: /^Content/ }).click();
  await page.getByRole("button", { name: /cited/ }).first().click();
  await expect(page.getByText("IMMUTABLE EVIDENCE", { exact: true })).toBeVisible();
  await expect(page.getByText("Use 10 Nm for the service fastener.", { exact: false })).toBeVisible();
});
