import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Search } from "lucide-react";
import { CommandPalette, EmptyState, PageHeader } from "./components";

describe("reference components", () => {
  it("renders the page header with navigation and metadata", () => {
    const markup = renderToStaticMarkup(
      <PageHeader
        eyebrow="WORKSPACE / PROJECTS"
        title="Projects"
        meta="2 total · 1 source"
        onBack={() => {}}
      />,
    );
    expect(markup).toContain('class="page-header"');
    expect(markup).toContain("Projects");
    expect(markup).toContain("2 total · 1 source");
    expect(markup).toContain('aria-label="Go back"');
  });

  it("renders an actionable empty state", () => {
    const markup = renderToStaticMarkup(
      <EmptyState
        icon={Search}
        title="No sources yet"
        body="Upload a source to begin."
        action={<button type="button">Upload source</button>}
      />,
    );
    expect(markup).toContain('class="empty-state"');
    expect(markup).toContain("No sources yet");
    expect(markup).toContain("Upload source");
  });

  it("renders every deterministic command palette route", () => {
    const markup = renderToStaticMarkup(
      <CommandPalette onClose={() => {}} onChoose={() => {}} onNew={() => {}} />,
    );
    expect(markup).toContain('role="dialog"');
    expect(markup).toContain("Open Projects");
    expect(markup).toContain("Open Sources");
    expect(markup).toContain("Open Skills");
    expect(markup).toContain("New Project");
  });
});
