"""Typed immutable content-block payload contracts."""

from typing import Any

CONTENT_BLOCK_TYPES = frozenset(
    {
        "heading",
        "paragraph",
        "ordered_procedure",
        "unordered_procedure",
        "objective_list",
        "warning",
        "note",
        "table",
        "figure",
        "quiz",
        "checklist",
        "source_list",
    }
)
_TEXT_BLOCK_TYPES = frozenset({"heading", "paragraph", "warning", "note"})
_LIST_BLOCK_TYPES = frozenset(
    {"ordered_procedure", "unordered_procedure", "objective_list", "quiz", "checklist", "source_list"}
)


def _finding(code: str, message: str, block_type: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message}
    if block_type is not None:
        result["block_type"] = block_type
    return result


def validate_block_payload(block_type: Any, payload: Any) -> list[dict[str, Any]]:
    """Return deterministic findings for one typed block payload.

    Payloads remain JSON-shaped so immutable history and provider output stay
    forward-compatible, but every supported type has a bounded required shape.
    """
    if not isinstance(block_type, str) or block_type not in CONTENT_BLOCK_TYPES:
        return [_finding("UNKNOWN_BLOCK_TYPE", "The content block type is unsupported.", str(block_type))]
    if not isinstance(payload, dict):
        return [_finding("INVALID_BLOCK_PAYLOAD", "The content block payload must be an object.", block_type)]
    declared_type = payload.get("block_type", block_type)
    if declared_type != block_type:
        return [_finding("BLOCK_TYPE_MISMATCH", "Payload block_type does not match the stored type.", block_type)]

    if block_type in _TEXT_BLOCK_TYPES:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 20_000:
            return [_finding("INVALID_BLOCK_PAYLOAD", "Text blocks require 1–20,000 characters of text.", block_type)]
        return []

    if block_type in _LIST_BLOCK_TYPES:
        items = payload.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            return [_finding("INVALID_BLOCK_PAYLOAD", "List blocks require 1–100 items.", block_type)]
        for item in items:
            if isinstance(item, str):
                if not item.strip() or len(item) > 5_000:
                    return [_finding("INVALID_BLOCK_PAYLOAD", "List item text is empty or too large.", block_type)]
            elif isinstance(item, dict):
                if not item or any(not isinstance(key, str) for key in item):
                    return [_finding("INVALID_BLOCK_PAYLOAD", "List item objects must contain string keys.", block_type)]
            else:
                return [_finding("INVALID_BLOCK_PAYLOAD", "List items must be strings or objects.", block_type)]
        return []

    if block_type == "table":
        columns = payload.get("columns")
        rows = payload.get("rows")
        if not isinstance(columns, list) or not 1 <= len(columns) <= 50 or not all(
            isinstance(column, str) and column.strip() for column in columns
        ):
            return [_finding("INVALID_BLOCK_PAYLOAD", "Tables require 1–50 non-empty column names.", block_type)]
        if not isinstance(rows, list) or len(rows) > 100 or any(
            not isinstance(row, list) or len(row) != len(columns) for row in rows
        ):
            return [_finding("INVALID_BLOCK_PAYLOAD", "Table rows must match the column count and stay within bounds.", block_type)]
        return []

    if block_type == "figure":
        if not isinstance(payload.get("alt_text"), str) or not payload["alt_text"].strip():
            return [_finding("INVALID_BLOCK_PAYLOAD", "Figures require non-empty alt_text.", block_type)]
        if "asset_ref" in payload and not isinstance(payload["asset_ref"], str):
            return [_finding("INVALID_BLOCK_PAYLOAD", "Figure asset_ref must be a logical string reference.", block_type)]
        return []

    return [_finding("INVALID_BLOCK_PAYLOAD", "The content block payload is invalid.", block_type)]
