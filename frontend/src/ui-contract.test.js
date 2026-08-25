import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("./main.jsx", import.meta.url), "utf8");
const components = await readFile(
  new URL("./components.jsx", import.meta.url),
  "utf8",
);
const aiComponents = await readFile(
  new URL("./ai/AgentEventLabel.jsx", import.meta.url),
  "utf8",
);
const skillAuthor = await readFile(
  new URL("./ai/SkillAuthorPanel.jsx", import.meta.url),
  "utf8",
);
const styles = await readFile(new URL("./styles.css", import.meta.url), "utf8");
const referenceStyles = await readFile(
  new URL("./ui/reference-theme.css", import.meta.url),
  "utf8",
);
const uiSource = `${source}\n${components}\n${aiComponents}\n${skillAuthor}`;

test("reference surfaces and connected mutations are present in the UI", () => {
  assert.match(source, /AgentEventLabel/);
  assert.match(aiComponents, /function AgentEventLabel/);
  assert.match(source, /SkillAuthorPanel/);
  assert.match(skillAuthor, /function SkillAuthorPanel/);
  for (const surface of [
    "ProjectsScreen",
    "SourcesScreen",
    "SkillsScreen",
    "Canvas",
    "CitationPanel",
    "TypedBlockBody",
    "ValidationPanel",
    "DiffCard",
    "SettingsModal",
    "CommandPalette",
    "NewProjectModal",
  ]) {
    assert.match(uiSource, new RegExp(`function ${surface}\\b`));
  }
  for (const contract of [
    "/v1/projects",
    "/v1/projects/page",
    "/v1/sources",
    "/v1/skills",
    "/v1/skills/ai-drafts",
    "/v1/skill-versions/",
    "Repair draft",
    "Create repaired draft",
    "/v1/workspace/preferences",
    "/v1/approvals/",
    "/v1/patches/",
    "/v1/runs/",
    "Active skills",
    "skill_version_ids",
    "/v1/skills/",
    "/v1/source-versions/",
    "/v1/projects/",
    "Validation checklist",
    "source-row-actions",
    "Versions",
    "sourceId",
    "Fork to workspace",
    "Cancel run",
    "Resume run",
    "subscribeToEvents",
  ]) {
    assert.match(source, new RegExp(contract.replaceAll("/", "\\/")));
  }
  for (const typedBlock of ["ordered_procedure", "source_list", "typed-table", "figure-placeholder"]) {
    assert.match(source, new RegExp(typedBlock));
  }
});

test("interactive reference states expose keyboard and assistive semantics", () => {
  assert.doesNotMatch(source, /\balert\(/);
  assert.match(source, /role="dialog"\s+aria-modal="true"/);
  assert.match(source, /role="alert"/);
  assert.match(source, /data-error-kind=\{classifyError\(error\)\}/);
  assert.match(source, /Permission denied/);
  assert.match(source, /Temporary service issue/);
  assert.match(source, /role="status"/);
  assert.match(source, /aria-label="Send message"/);
  assert.match(source, /aria-expanded=\{open === skill\.id\}/);
  assert.match(source, /event\.key === "Enter" \|\| event\.key === " "/);
  assert.match(source, /aria-pressed=\{status === value\}/);
  assert.match(source, /className="skill-scope-heading"/);
  assert.match(source, /aria-label="Search skills"/);
});

test("reference shell keeps branding compact and prevents narrow viewport overflow", () => {
  assert.match(source, /className="brand-copy"/);
  assert.match(source, /className="brand-subtitle"/);
  assert.match(source, /className="nav-label"/);
  assert.match(uiSource, /className="page-header-title"/);
  assert.match(source, /className="project-filters"/);
  assert.match(source, /filter-button/);
  assert.match(source, /className="content-type-grid"/);
  assert.match(source, /className="source-dropzone"/);
  assert.match(source, /className="new-project-footer"/);
  assert.match(styles, /--panel: #121518/);
  assert.match(styles, /\.main-shell[\s\S]*overflow-x: hidden/);
  assert.match(styles, /\.sidebar \.brand-copy[\s\S]*display: none/);
  assert.match(styles, /\.toolbar \.search-box[\s\S]*flex: 1 1 100%/);
  assert.match(styles, /\.project-grid[\s\S]*grid-template-columns: 1fr/);
  assert.match(styles, /\.page > \.empty-state[\s\S]*border: 1\.5px dashed/);
  assert.match(styles, /\.modal-backdrop[\s\S]*backdrop-filter: blur\(2px\)/);
  assert.match(styles, /\.modal-field input,[\s\S]*background: var\(--panel-2\)/);
  for (const exactReferenceDimension of [
    /\.sidebar[\s\S]*width: 210px/,
    /\.source-rail[\s\S]*width: 42px/,
    /\.source-flyout[\s\S]*width: 296px/,
    /\.copilot[\s\S]*width: 348px/,
    /\.canvas-header[\s\S]*height: 52px/,
  ]) {
    assert.match(referenceStyles, exactReferenceDimension);
  }
});
