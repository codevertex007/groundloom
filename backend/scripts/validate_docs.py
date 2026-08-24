"""Small deterministic documentation gate for links and requirement IDs."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def main() -> int:
    markdown = list(DOCS.rglob("*.md"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in markdown)
    ids = re.findall(r"\b(?:FR|UI|NFR|ARCH|DATA|AGENT|TOOL|API|EVT|SEC|OPS|TEST)-[A-Z0-9-]+\b", text)
    duplicates = sorted({item for item in ids if ids.count(item) > 1 and item.startswith(("ADR-",))})
    if duplicates:
        raise SystemExit(f"Duplicate documentation identifiers: {duplicates}")
    matrix = (DOCS / "validation" / "requirements-test-matrix.md").read_text(encoding="utf-8")
    required = ["FR-PROJECT-001", "FR-SOURCE-001", "FR-SKILL-001", "FR-AGENT-001", "FR-CONTENT-001", "FR-QUALITY-001", "FR-EXPORT-001"]
    missing = [item for item in required if item not in matrix]
    if missing:
        raise SystemExit(f"Traceability matrix is missing: {missing}")
    for path in markdown:
        # The bundled Deep Agents reference mirrors an external monorepo and
        # intentionally contains links to source paths not shipped here.
        if "ref" in path.relative_to(DOCS).parts:
            continue
        for link in re.findall(r"\]\(([^)#]+)", path.read_text(encoding="utf-8")):
            if link.startswith(("http://", "https://", "#")):
                continue
            target = (path.parent / link).resolve()
            if not target.exists():
                raise SystemExit(f"Broken documentation link: {path} -> {link}")
    print(f"Validated {len(markdown)} markdown documents and requirement traceability")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
