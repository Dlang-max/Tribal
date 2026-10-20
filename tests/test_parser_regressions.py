"""Integration regressions from public-input review, independent of internals."""
import json

import pytest

from tribal import validate_document


def document(body="Useful text.\n", **changes):
    metadata = dict(schema_version=1, id="00000000-0000-4000-8000-000000000001",
                    title="Example", knowledge_base="fixture-kb", domain="research",
                    kind="finding", summary="A summary.")
    metadata.update(changes)
    return "---\n" + "".join(f"{key}: {json.dumps(value)}\n" for key, value in metadata.items()) + "---\n" + body


@pytest.mark.parametrize("changes", [
    {"summary": "\ud800"},
    {"contexts": [{"key": "root", "type": "filesystem", "locator": "file:///\ud800"}]},
    {"sources": [{"type": "observation", "locator": "\ud800"}]},
    {"x_extra": "\ud800"},
])
def test_yaml_escaped_surrogates_produce_diagnostics_instead_of_crashing(changes):
    result = validate_document(document(**changes))
    assert result["valid"] is False
    errors = [d for d in result["diagnostics"] if d["severity"] == "error"]
    assert errors
    assert all(d["hint"] for d in errors)
    json.dumps(result, ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize("marker", ["%%", "<!--"])
def test_comment_markers_inside_inline_code_do_not_hide_following_structure(marker):
    body = f"Text `{marker}`\n\n# Real heading\n[[Real]]\n"
    result = validate_document(document(body))
    assert result["valid"], result["diagnostics"]
    doc = result["document"]
    assert [h["text"] for h in doc["headings"]] == ["Real heading"]
    assert [link["target_text"] for link in doc["links"]] == ["Real"]
    assert doc["body"] == body


@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\u0085", "\x0b", "\x0c"])
def test_only_lf_separates_physical_source_lines_and_block_spans(separator):
    body = f"before{separator}after\n\n# Heading\n\n```text\nexample\n```\n"
    result = validate_document(document(body))
    assert result["valid"], result["diagnostics"]
    doc = result["document"]
    canonical = doc["canonical_markdown"].encode("utf-8")
    code = next(b for b in doc["blocks"] if b["kind"] == "code")
    assert canonical[code["start_byte"]:code["end_byte"]] == b"```text\nexample\n```\n"
    heading = next(b for b in doc["blocks"] if b["kind"] == "heading")
    assert canonical[heading["start_byte"]:heading["end_byte"]] == b"# Heading\n"


def test_self_anchor_with_empty_display_alias_remains_malformed_literal():
    result = validate_document(document("# Heading\n\n[[#Heading|]]\n"))
    assert result["valid"]
    assert result["document"]["links"] == []
    assert any(d["code"] == "W_WIKILINK_SYNTAX" for d in result["diagnostics"])


@pytest.mark.parametrize("indent", ["    ", "\t"])
def test_overindented_fence_does_not_count_as_a_closing_fence(indent):
    result = validate_document(document(f"```text\nexample\n{indent}```\n"))
    assert not result["valid"]
    assert any(d["code"] == "E_UNCLOSED_FENCE" for d in result["diagnostics"])


def test_closed_fence_in_deep_list_and_quote_is_valid():
    body = "- outer\n  - inner\n    - deeper\n      > ```text\n      > example\n      > ```\n"
    result = validate_document(document(body))
    assert result["valid"], result["diagnostics"]
    assert any(block["kind"] == "code" for block in result["document"]["blocks"])
