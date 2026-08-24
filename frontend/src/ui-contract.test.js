import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("./main.jsx", import.meta.url), "utf8");
const components = await readFile(
  new URL("./components.jsx", import.meta.url),
  "utf8",
);
const uiSource = `${source}\n${components}`;

test("reference surfaces and connected mutations are present in the UI", () => {
  for (const surface of [
    "ProjectsScreen",
    "SourcesScreen",
    "SkillsScreen",
    "Canvas",
    "CitationPanel",
    "DiffCard",
    "SettingsModal",
    "CommandPalette",
    "NewProjectModal",
  ]) {
    assert.match(uiSource, new RegExp(`function ${surface}\\b`));
  }
  for (const contract of [
    "/v1/projects",
    "/v1/sources",
    "/v1/skills",
    "/v1/workspace/preferences",
    "/v1/approvals/",
    "/v1/patches/",
    "/v1/runs/",
    "Cancel run",
    "Resume run",
    "subscribeToEvents",
  ]) {
    assert.match(source, new RegExp(contract.replaceAll("/", "\\/")));
  }
});

test("interactive reference states expose keyboard and assistive semantics", () => {
  assert.match(source, /role="dialog"\s+aria-modal="true"/);
  assert.match(source, /role="alert"/);
  assert.match(source, /role="status"/);
  assert.match(source, /aria-label="Send message"/);
  assert.match(source, /aria-expanded=\{open === skill\.id\}/);
  assert.match(source, /event\.key === "Enter" \|\| event\.key === " "/);
  assert.match(source, /aria-pressed=\{status !== "all"\}/);
});
