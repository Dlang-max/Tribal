"""Black-box source partition tests derived from tribal_chunking_strategy.md."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tribal import chunk_document, validate_document
from acceptance_helpers import DOCUMENT_ID, REVISION_ID, diagnostic_codes, note

POLICY = "tribal-structure-bytes-v1"
FIXTURES = Path(__file__).parent / "acceptance_fixtures" / "markdown_v1" / "baseline"


def layout(authored, **kwargs):
    result = chunk_document(authored, **kwargs)
    assert result["valid"] is True, result["diagnostics"]
    canonical = validate_document(authored, path=kwargs.get("path", "note.md"))["document"]
    source = canonical["canonical_markdown"].encode("utf-8")
    chunks = result["chunks"]
    assert chunks, "a valid nonempty body has at least one chunk"
    assert result["document_id"] == canonical["metadata"]["id"]
    assert result["content_hash"] == hashlib.sha256(source).hexdigest()
    assert result["chunker_version"] == POLICY
    body = canonical["body"]
    body_start = len(source) - len(body.encode("utf-8"))
    assert result["body_start_byte"] == body_start
    cursor = body_start
    for ordinal, chunk in enumerate(chunks):
        assert chunk["ordinal"] == ordinal
        assert chunk["chunker_version"] == POLICY
        assert chunk["start_byte"] == cursor
        assert chunk["end_byte"] > cursor
        assert chunk["content"] == source[cursor:chunk["end_byte"]].decode("utf-8")
        cursor = chunk["end_byte"]
    assert cursor == len(source)
    assert "".join(chunk["content"] for chunk in chunks) == body
    json.dumps(result, allow_nan=False)
    return result


def contents(result):
    return [chunk["content"] for chunk in result["chunks"]]


@pytest.mark.parametrize("path", sorted(path.relative_to(FIXTURES).as_posix() for path in FIXTURES.rglob("*.md")))
def test_acceptance_vault_partitions_the_complete_body(path):
    layout((FIXTURES / path).read_text(encoding="utf-8"), path=path)


def test_revision_identity_is_attached_to_every_chunk():
    result = layout(note("intro\n\n## Method\n\nmeasure\n"), revision_id=REVISION_ID)
    assert result["revision_id"] == REVISION_ID
    assert all(chunk["revision_id"] == REVISION_ID for chunk in result["chunks"])
    assert result["document_id"] == DOCUMENT_ID


def test_preview_does_not_invent_a_persisted_revision():
    result = layout(note())
    assert result.get("revision_id") is None
    assert all(chunk.get("revision_id") is None for chunk in result["chunks"])


@pytest.mark.parametrize("body", ["\n\n界😀e\u0301\u2028x\n\n", "line without final newline", "\n\t\n  prose\n\n\n"])
def test_unicode_whitespace_and_canonical_final_newline_are_preserved(body):
    layout(note(body))


def test_transport_and_crlf_do_not_change_canonical_ranges():
    authored = note("前置き\n\n## 観察\n\n🌱 observation\n")
    transported = authored.replace("---\n", f"---\ntribal_base_revision: {REVISION_ID}\n", 1)
    baseline = layout(authored)
    submitted = layout(transported.replace("\n", "\r\n"))
    for key in ("content_hash", "chunks", "chunker_version"):
        assert submitted[key] == baseline[key]


def test_sections_include_every_root_heading_and_keep_heading_stack():
    sections = ["Introduction.\n\n", "# Seed observations\n\n", "### Deep\n\nText.\n\n",
                "## Method\n\nMeasure.\n\n", "Method result\n=============\n\nDone.\n"]
    result = layout(note("".join(sections)))
    assert contents(result) == sections
    assert [c["heading_path"] for c in result["chunks"]] == [[], ["Seed observations"],
        ["Seed observations", "Deep"], ["Seed observations", "Method"], ["Method result"]]
    assert [c["section_anchor"] for c in result["chunks"]] == [None, "Seed observations", "Deep", "Method", "Method result"]


def test_duplicate_and_formatted_headings_have_no_plain_unique_anchor():
    result = layout(note("## Same\n\none\n\n## Same\n\ntwo\n\n## *Styled*\n\nthree\n"))
    assert [c["section_anchor"] for c in result["chunks"]] == [None, None, None]
    assert [c["heading_path"] for c in result["chunks"]] == [["Same"], ["Same"], ["Styled"]]


def test_headings_inside_containers_and_opaque_blocks_do_not_make_sections():
    body = "## Actual\n\n> ## Quoted\n> text\n\n- ## Listed\n  text\n\n```md\n# Code\n```\n\n<!--\n# Hidden\n-->\n"
    result = layout(note(body))
    assert contents(result) == [body]
    assert result["chunks"][0]["heading_path"] == ["Actual"]


@pytest.mark.parametrize("size", [4095, 4096, 4097])
def test_exact_soft_boundary_counts_source_bytes(size):
    body = "界" * ((size - 1) // 3) + "x" * ((size - 1) % 3) + "\n"
    assert len(body.encode()) == size
    result = layout(note(body))
    assert contents(result) == [body]
    assert ("W_OVERSIZED_BLOCK" in diagnostic_codes(result)) is (size > 4096)
    if size > 4096:
        warning = next(d for d in result["diagnostics"] if d["code"] == "W_OVERSIZED_BLOCK")
        chunk = result["chunks"][0]
        assert warning["expected"] == 4096
        assert warning["actual"] == dict(start_byte=chunk["start_byte"], end_byte=chunk["end_byte"],
                                       bytes=size, unit_kind="paragraph")



@pytest.mark.parametrize("combined_bytes", [4096, 4097])
def test_adjacent_units_pack_together_if_and_only_if_complete_source_fits(combined_bytes):
    first = "a" * 2046 + "\n\n"
    second = "b" * (combined_bytes - len(first.encode()) - 2) + "\n\n"
    result = layout(note(first + second))
    assert len((first + second).encode()) == combined_bytes
    assert contents(result) == ([first + second] if combined_bytes == 4096 else [first, second])
    assert "W_OVERSIZED_BLOCK" not in diagnostic_codes(result)


def test_greedy_packing_attaches_blank_gaps_to_previous_unit_and_does_not_rebalance():
    first, second, third = "a" * 2998 + "\n\n", "b" * 1998 + "\n\n", "c" * 998 + "\n\n"
    result = layout(note(first + second + third))
    assert contents(result) == [first, second + third]
    assert "W_OVERSIZED_BLOCK" not in diagnostic_codes(result)


@pytest.mark.parametrize("expected_kind, protected", [
    ("code", "```python\n" + "# apparently a heading\n" * 230 + "```\n\n"),
    ("mermaid", "~~~mermaid\nflowchart TD\n" + "A-->B\n" * 700 + "~~~\n\n"),
    ("code", "    " + ("indented code\n    " * 320) + "last\n\n"),
    ("table", "| Value | Result |\n|---|---|\n" + "| 12345 | 67890 |\n" * 280 + "\n"),
    ("math", "$$\n" + "x = y + z\n\n" * 400 + "$$\n\n"),
    ("math", "\\[\n" + "x = y + z\n\n" * 400 + "\\]\n\n"),
    ("blockquote", "> " + "> quoted\n>\n" * 500 + "> last\n\n"),
    ("opaque", "<!--\n" + "opaque\n\n" * 600 + "-->\n\n"),
    ("definition", '[label]: https://example.test/\n    "' + "x" * 5000 + '"\n\n'),
    ("definition", "[^footnote]: reference\n" + "    continuation " + "x" * 5000 + "\n\n"),
])
def test_oversized_protected_blocks_are_kept_whole(expected_kind, protected):
    prefix, suffix = "Before.\n\n", "After.\n"
    result = layout(note(prefix + protected + suffix))
    assert contents(result) == [prefix, protected, suffix]
    assert "W_OVERSIZED_BLOCK" in diagnostic_codes(result)
    warnings = [d for d in result["diagnostics"] if d["code"] == "W_OVERSIZED_BLOCK"]
    assert warnings
    assert all(d["severity"] == "warning" and d["hint"] for d in warnings)
    oversized = result["chunks"][1]
    warning = next(d for d in warnings if d["actual"]["start_byte"] == oversized["start_byte"])
    assert warning["expected"] == 4096
    assert warning["actual"]["end_byte"] == oversized["end_byte"]
    assert warning["actual"]["bytes"] == len(protected.encode("utf-8"))
    assert warning["actual"]["unit_kind"] == expected_kind



def test_oversized_lists_split_only_between_complete_immediate_items():
    items = [f"- item {i}: " + "x" * 2150 + "\n  - nested one\n  - nested two\n" for i in range(3)]
    result = layout(note("".join(items)))
    assert contents(result) == items
    assert "W_OVERSIZED_BLOCK" not in diagnostic_codes(result)


def test_list_item_with_a_nested_diagram_stays_intact_when_oversized():
    first = "- diagram\n\n  ```mermaid\n  flowchart TD\n" + "  A-->B\n" * 600 + "  ```\n"
    second = "- next item\n"
    result = layout(note(first + second))
    assert contents(result) == [first, second]
    assert "W_OVERSIZED_BLOCK" in diagnostic_codes(result)
    warning = next(d for d in result["diagnostics"] if d["code"] == "W_OVERSIZED_BLOCK")
    assert warning["actual"]["unit_kind"] == "list_item"


def test_same_canonical_document_has_identical_layout_on_repeated_calls():
    authored = note("## Method\n\n" + "a" * 3000 + "\n\n" + "b" * 3000 + "\n")
    assert layout(authored) == layout(authored)


def test_chunk_warning_locations_use_submitted_input_before_transport_removal():
    authored = note("Short.\n\n" + "x" * 4097 + "\n")
    submitted = authored.replace("---\n", f"---\ntribal_base_revision: {REVISION_ID}\n", 1)
    result = layout(submitted.replace("\n", "\r\n"), path="positions.md")
    warning = next(d for d in result["diagnostics"] if d["code"] == "W_OVERSIZED_BLOCK")
    assert warning["path"] == "positions.md"
    assert warning["line"] == submitted.splitlines().index("x" * 4097) + 1
    assert warning["column"] == 1


@pytest.mark.parametrize("authored, code", [(note(""), "E_EMPTY_BODY"),
    (note("```python\nunclosed\n"), "E_UNCLOSED_FENCE"),
    (note(kind="wrong"), "E_FIELD_TYPE"), (b"\xff", "E_ENCODING")])
def test_invalid_documents_never_produce_partial_chunks(authored, code):
    result = chunk_document(authored)
    assert result["valid"] is False
    assert result["chunks"] == []
    assert code in diagnostic_codes(result)


def test_assignment_validation_is_preserved():
    result = chunk_document(note(), knowledge_base="other", domains=["research"])
    assert result["valid"] is False
    assert result["chunks"] == []
    assert "E_ASSIGNMENT" in diagnostic_codes(result)


def test_footnote_continuation_paragraphs_across_blank_lines_stay_one_definition():
    prefix, suffix = "Before.\n\n", "After.\n"
    definition = "[^observation]: first paragraph\n\n    " + "x" * 5000 + "\n\n"
    result = layout(note(prefix + definition + suffix))
    assert contents(result) == [prefix, definition, suffix]
    warning = next(d for d in result["diagnostics"] if d["code"] == "W_OVERSIZED_BLOCK")
    assert warning["actual"]["unit_kind"] == "definition"
