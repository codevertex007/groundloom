import pytest
from app.content_types import validate_block_payload


@pytest.mark.parametrize(
    ("block_type", "payload"),
    [
        ("heading", {"block_type": "heading", "text": "A heading"}),
        ("paragraph", {"block_type": "paragraph", "text": "A paragraph"}),
        ("ordered_procedure", {"block_type": "ordered_procedure", "items": ["First"]}),
        ("unordered_procedure", {"block_type": "unordered_procedure", "items": ["First"]}),
        ("objective_list", {"block_type": "objective_list", "items": ["Objective"]}),
        ("warning", {"block_type": "warning", "text": "Warning"}),
        ("note", {"block_type": "note", "text": "Note"}),
        ("table", {"block_type": "table", "columns": ["A"], "rows": [["B"]]}),
        ("figure", {"block_type": "figure", "alt_text": "A diagram"}),
        ("quiz", {"block_type": "quiz", "items": [{"question": "Why?"}]}),
        ("checklist", {"block_type": "checklist", "items": ["Check"]}),
        ("source_list", {"block_type": "source_list", "items": ["Source"]}),
    ],
)
def test_supported_content_block_payloads_are_valid(block_type, payload):
    assert validate_block_payload(block_type, payload) == []


@pytest.mark.parametrize(
    ("block_type", "payload", "code"),
    [
        ("not_supported", {"text": "x"}, "UNKNOWN_BLOCK_TYPE"),
        ("paragraph", {"block_type": "heading", "text": "x"}, "BLOCK_TYPE_MISMATCH"),
        ("paragraph", {"block_type": "paragraph", "text": ""}, "INVALID_BLOCK_PAYLOAD"),
        ("ordered_procedure", {"block_type": "ordered_procedure", "items": []}, "INVALID_BLOCK_PAYLOAD"),
        ("table", {"block_type": "table", "columns": ["A", "B"], "rows": [["one"]]}, "INVALID_BLOCK_PAYLOAD"),
        ("figure", {"block_type": "figure"}, "INVALID_BLOCK_PAYLOAD"),
    ],
)
def test_invalid_content_block_payloads_have_stable_codes(block_type, payload, code):
    findings = validate_block_payload(block_type, payload)
    assert findings
    assert findings[0]["code"] == code
