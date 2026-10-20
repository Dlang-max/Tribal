"""Independent black-box conformance checks for Tribal Markdown v1.

Only public library/CLI contracts and the supplied fixture oracle are used.
No persistence, revision transaction, embedding, or rendering claims are made.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from tribal import validate_document, validate_vault


def fixture_root():
    here = Path(__file__).resolve().parent
    candidate = here / "acceptance_fixtures" / "markdown_v1"
    if (candidate / "manifest.json").is_file():
        return candidate
    raise RuntimeError("markdown_v1 acceptance fixture package is missing")


FIXTURES = fixture_root()
PROJECT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
TOKEN = "10000000-0000-4000-8000-000000000001"
SHA40 = "a" * 40
SHA64 = "b" * 64
CAP = 8_388_608


def properties(**changes):
    result = dict(schema_version=1, id=str(uuid.uuid4()), title="Example",
                  knowledge_base="fixture-kb", domain="research", kind="finding",
                  summary="A concise summary.")
    result.update(changes)
    return result


def note(body="A useful sentence.\n", *, fields=None, extra="", **changes):
    data = properties(**changes) if fields is None else fields
    # JSON scalars/collections are YAML 1.2 values. Each top-level key remains
    # a block mapping entry, and replacements cannot accidentally duplicate keys.
    header = "".join(f"{key}: {json.dumps(value, ensure_ascii=False)}\n"
                     for key, value in data.items())
    return f"---\n{header}{extra}---\n{body}"


def codes(result):
    return {item["code"] for item in result["diagnostics"]}


def assert_error(result, *expected):
    assert result["valid"] is False, result["diagnostics"]
    errors = {item["code"] for item in result["diagnostics"] if item["severity"] == "error"}
    assert errors.intersection(expected), result["diagnostics"]


def parsed(result):
    assert result["valid"] is True, result["diagnostics"]
    assert result["document"] is not None
    return result["document"]


def fixture(relative):
    return (FIXTURES / relative).read_text(encoding="utf-8")


def context(kind="experiment", **changes):
    result = dict(key="work", type=kind)
    result.update(changes)
    return result


def source(kind="experiment", **changes):
    result = dict(type=kind, locator="trial-12")
    result.update(changes)
    return result


def cli(*args, env=None):
    return subprocess.run([sys.executable, "-m", "tribal", "validate", *map(str, args)],
                          cwd=PROJECT, capture_output=True, text=True, env=env,
                          timeout=30)


def test_minimal_note_defaults_no_headings_and_json_serializable_results():
    authored = note()
    result = validate_document(authored)
    doc = parsed(result)
    assert result["path"] == "note.md"
    assert doc["headings"] == [] and doc["links"] == []
    assert doc["base_revision"] is None
    for key, value in dict(status="active", tags=[], aliases=[], contexts=[], scope={},
                           verification_state="unverified", sources=[]).items():
        assert doc["metadata"][key] == value
    assert doc["canonical_markdown"] == authored
    assert "status:" not in doc["canonical_markdown"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("kind", ["finding", "overview", "decision", "procedure", "reference"])
def test_all_document_kinds_allow_short_bodies_without_prescribed_sections(kind):
    parsed(validate_document(note(kind=kind)))


@pytest.mark.parametrize(("content", "code"), [
    (b"\xef\xbb\xbf" + note().encode(), "E_ENCODING"),
    ("\ufeff" + note(), "E_ENCODING"),
    (note() + "\x00", "E_ENCODING"),
    (b"\xff\xfe", "E_ENCODING"),
    ("ordinary project docs\n", "E_FRONTMATTER"),
    ("\n" + note(), "E_FRONTMATTER"),
    (note().replace("---\n", "--- \n", 1), "E_FRONTMATTER"),
    ("---\nschema_version: 1\n", "E_FRONTMATTER"),
    (note("\t  \n\n"), "E_EMPTY_BODY"),
], ids=["byte-bom", "text-bom", "nul", "invalid-utf8", "no-frontmatter",
        "leading-blank", "inexact-opening", "unclosed-frontmatter", "blank-body"])
def test_encoding_and_envelope(content, code):
    assert_error(validate_document(content, path="bad.md"), code)


@pytest.mark.parametrize("ending", ["\r\n", "\r", "\n"])
def test_line_ending_normalization_and_final_newline(ending):
    authored = note("# Example\n\nKeep  spacing, café, and e\u0301.\n", extra="# YAML comment\n")
    submitted = authored.rstrip("\n").replace("\n", ending)
    result = validate_document(submitted.encode())
    doc = parsed(result)
    assert doc["canonical_markdown"] == authored
    assert doc["body"] == "# Example\n\nKeep  spacing, café, and e\u0301.\n"
    assert doc["content_hash"] == hashlib.sha256(authored.encode()).hexdigest()
    assert "W_NORMALIZED" in codes(result)


@pytest.mark.parametrize("yaml", [
    "[one, two]\n", "{schema_version: 1}\n", "? [one, two]\n: value\n",
    "17: value\n", "scope:\n  1: value\n", "scope: {a: 1, a: 2}\n",
    "x_deep:\n  - details:\n      nested: 1\n      nested: 2\n",
    "title: First\ntitle: Second\n", "x_anchor: &anchor 1\n",
    "x_anchor: &anchor [1]\nx_alias: *anchor\n",
    "x_merge: {<<: {a: 1}}\n", "x_tag: !custom value\n",
    "x_inf: .inf\n", "scope: {value: -.Inf}\n", "x_nan: .nan\n",
])
def test_prohibited_yaml_is_rejected_at_any_depth(yaml):
    # Structural/nonmapping cases stand alone; other cases accompany valid fields.
    if yaml.startswith(("[", "{", "?")):
        content = f"---\n{yaml}---\nBody.\n"
    elif yaml.startswith("title:"):
        fields = properties()
        del fields["title"]
        content = note(fields=fields, extra=yaml)
    else:
        content = note(extra=yaml)
    assert_error(validate_document(content), "E_FRONTMATTER")


def test_yaml_12_legacy_boolean_words_dates_and_extensions_remain_json_values():
    result = validate_document(note(extra=(
        "x_yes: yes\nx_no: no\nx_on: on\nx_off: off\nx_date: 2026-10-20\n"
        "x_nested: [true, false, null, 12, 1.25]\n"
    ), scope={"nullable": None, "nested": [True, {"n": 2}]}))
    doc = parsed(result)
    assert [doc["metadata"][f"x_{key}"] for key in ("yes", "no", "on", "off")] == ["yes", "no", "on", "off"]
    assert doc["metadata"]["x_date"] == "2026-10-20"
    assert doc["metadata"]["x_nested"] == [True, False, None, 12, 1.25]
    assert doc["metadata"]["scope"] == {"nullable": None, "nested": [True, {"n": 2}]}
    assert "W_UNKNOWN_PROPERTY" not in codes(result)
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("field", list(properties()))
def test_every_required_field_is_required(field):
    fields = properties()
    del fields[field]
    assert_error(validate_document(note(fields=fields)), "E_REQUIRED_FIELD")


@pytest.mark.parametrize(("field", "value", "code"), [
    ("schema_version", "1", "E_FIELD_TYPE"), ("schema_version", True, "E_FIELD_TYPE"),
    ("schema_version", 2, "E_SCHEMA_VERSION"), ("schema_version", 1.0, "E_FIELD_TYPE"),
    ("id", "00000000-0000-0000-0000-000000000000", "E_FIELD_TYPE"),
    ("id", "ABCDEF00-0000-4000-8000-000000000001", "E_FIELD_TYPE"),
    ("id", "not-a-uuid", "E_FIELD_TYPE"), ("id", 4, "E_FIELD_TYPE"),
    ("title", " ", "E_REQUIRED_FIELD"), ("title", "two\nlines", "E_FIELD_TYPE"),
    ("title", "x" * 256, "E_FIELD_TYPE"), ("title", 1, "E_FIELD_TYPE"),
    ("summary", "  ", "E_REQUIRED_FIELD"), ("summary", ["text"], "E_FIELD_TYPE"),
    ("knowledge_base", "Bad_Key", "E_FIELD_TYPE"), ("domain", "a--b", "E_FIELD_TYPE"),
    ("domain", "a_", "E_FIELD_TYPE"), ("domain", "a" * 129, "E_FIELD_TYPE"),
    ("kind", "unknown", "E_FIELD_TYPE"), ("status", "deleted", "E_FIELD_TYPE"),
    ("verification_state", "complete", "E_FIELD_TYPE"),
    ("tags", "one", "E_FIELD_TYPE"), ("aliases", [1], "E_FIELD_TYPE"),
    ("contexts", {}, "E_CONTEXT"), ("scope", [], "E_FIELD_TYPE"),
    ("sources", {}, "E_SOURCE"), ("cssclasses", "one", "E_FIELD_TYPE"),
    ("verified_by", "  ", "E_FIELD_TYPE"), ("verified_by", "x" * 256, "E_FIELD_TYPE"),
    ("verified_at", "2026-10-20T12:00:00+00:00", "E_FIELD_TYPE"),
    ("verified_at", "2026-02-30T12:00:00Z", "E_FIELD_TYPE"),
])
def test_strict_field_types_formats_enums_and_lengths(field, value, code):
    # Schema-version wrong-type diagnostics have an explicit competing code in
    # the spec's minimum-conformance table, so accept either applicable code.
    alternatives = (code, "E_SCHEMA_VERSION") if field == "schema_version" else (code,)
    # Nested structures use E_FIELD_TYPE or their dedicated semantic code.
    if field in {"sources", "contexts", "verified_at"}:
        alternatives += ("E_FIELD_TYPE", "E_VERIFICATION")
    assert_error(validate_document(note(**{field: value})), *alternatives)


@pytest.mark.parametrize("field", ["status", "tags", "aliases", "contexts", "scope",
                                      "verification_state", "verified_at", "verified_by", "sources", "cssclasses"])
def test_optional_fields_cannot_be_null(field):
    assert_error(validate_document(note(**{field: None})), "E_FIELD_TYPE", "E_CONTEXT", "E_SOURCE", "E_VERIFICATION")


@pytest.mark.parametrize("tags", [["#tag"], ["123"], ["has space"], ["tag", "tag"], [""], ["bad!"]])
def test_invalid_tags_are_rejected(tags):
    assert_error(validate_document(note(tags=tags)), "E_FIELD_TYPE")


def test_valid_unicode_tags_and_unique_aliases_preserve_values():
    tags = ["botany/苗", "year2026", "with_under-score"]
    aliases = ["An alternative", "另一个名字"]
    doc = parsed(validate_document(note(tags=tags, aliases=aliases, cssclasses=["wide"])))
    assert doc["metadata"]["tags"] == tags
    assert doc["metadata"]["aliases"] == aliases
    assert_error(validate_document(note(aliases=["same", "same"])), "E_FIELD_TYPE")


def test_unknown_properties_warn_while_x_extensions_do_not():
    result = validate_document(note(extra="legacy_hint: keep me\nx_custom: {a: null}\n"))
    doc = parsed(result)
    assert doc["metadata"]["legacy_hint"] == "keep me"
    assert doc["metadata"]["x_custom"] == {"a": None}
    unknown = [d for d in result["diagnostics"] if d["code"] == "W_UNKNOWN_PROPERTY"]
    assert unknown and all(d["field"] != "x_custom" for d in unknown)


@pytest.mark.parametrize(("key", "code"), [("tribal_unknown", "E_TRANSPORT"),
    ("repository", "E_CONTEXT"), ("scope_branch", "E_CONTEXT"),
    ("scope_commit", "E_CONTEXT"), ("scope_environments", "E_CONTEXT")])
def test_reserved_and_obsolete_root_fields(key, code):
    assert_error(validate_document(note(**{key: "obsolete"})), code)


def test_registry_assignment_is_explicit_and_folder_does_not_define_domain():
    content = note(domain="research")
    parsed(validate_document(content, path="botany/note.md"))
    parsed(validate_document(content, knowledge_base="fixture-kb", domains=["research"]))
    assert_error(validate_document(content, knowledge_base="other"), "E_ASSIGNMENT")
    assert_error(validate_document(content, domains=["botany"]), "E_ASSIGNMENT")


@pytest.mark.parametrize("key", ["tribal_base_revision", '"tribal_base_revision"', "'tribal_base_revision'"])
@pytest.mark.parametrize("quoted", [TOKEN, f'"{TOKEN}"', f"'{TOKEN}'"])
def test_transport_all_scalar_quotes_and_key_quotes_remove_exactly_one_line(key, quoted):
    authored = note("# Example\n\nBody.\n", extra="# preserve comments\nx_number: 01\n")
    # Insert late in frontmatter, rather than assuming preferred export position.
    transport = f"{key}: {quoted} # transport comment\n"
    submitted = authored.replace("# preserve comments\n", "# preserve comments\n" + transport)
    doc = parsed(validate_document(submitted))
    assert doc["base_revision"] == TOKEN
    assert "tribal_base_revision" not in doc["metadata"]
    assert doc["canonical_markdown"] == authored
    assert doc["content_hash"] == hashlib.sha256(authored.encode()).hexdigest()


@pytest.mark.parametrize("transport", [
    "tribal_base_revision: nope\n", "tribal_base_revision: null\n",
    "tribal_base_revision: 1\n", "tribal_base_revision: []\n",
    'tribal_base_revision: "00000000-0000-0000-0000-000000000000"\n',
    f"tribal_base_revision: {TOKEN}\ntribal_base_revision: {TOKEN}\n",
    f'tribal_base_revision: "{TOKEN}\n  "\n',
    f"tribal_base_revision: >-\n  {TOKEN}\n",
    f"tribal_base_revision: {TOKEN} #" + "x" * 220 + "\n",
])
def test_invalid_transport_is_rejected_before_removal(transport):
    assert_error(validate_document(note(extra=transport)), "E_TRANSPORT", "E_FRONTMATTER")


def test_authored_yaml_formatting_affects_hash_but_transport_position_does_not():
    authored = note()
    moved = authored.replace("---\n", f"---\ntribal_base_revision: {TOKEN}\n", 1)
    a = parsed(validate_document(authored))
    b = parsed(validate_document(moved))
    requoted = authored.replace('title: "Example"', "title: 'Example'")
    c = parsed(validate_document(requoted))
    assert a["content_hash"] == b["content_hash"]
    assert a["content_hash"] != c["content_hash"]
    assert c["canonical_markdown"] == requoted


def test_fixture_hashes_and_base_tokens_match_independent_manifest_oracle():
    # These are static syntax/hash expectations; fixture scenarios involving
    # transactions and embeddings are deliberately outside this parser suite.
    for relative, expected in MANIFEST["files"].items():
        doc = parsed(validate_document(fixture(relative), path=Path(relative).name))
        assert doc["content_hash"] == expected["canonical_sha256"], relative
        assert doc["base_revision"] == expected["base_revision"], relative
        assert doc["metadata"]["id"] == expected["document_id"], relative


@pytest.mark.parametrize("root", ["file:///srv/plain", "file:///srv/plain/", "/srv/plain"])
def test_filesystem_sources_are_valid_with_explicit_directory_roots(root):
    contexts = [context("filesystem", locator=root)]
    sources = [source("code", locator="config/auth.json", context="work",
                      revision="configuration-edition-2026-10")]
    doc = parsed(validate_document(note(contexts=contexts, sources=sources)))
    # The public API does not define an effective-locator projection. Preserve
    # authored root/path/version rather than guessing a new return field.
    assert doc["metadata"]["contexts"] == contexts
    assert doc["metadata"]["sources"] == sources


@pytest.mark.parametrize("root", [".", "../notes", "notes/", "file:///srv/plain?q=1",
                                    "file:///srv/plain#part", "https://example.test"])
def test_filesystem_roots_cannot_implicitly_use_cwd_or_query_fragment(root):
    assert_error(validate_document(note(contexts=[context("filesystem", locator=root)])), "E_CONTEXT")


@pytest.mark.parametrize("locator", ["a//b.py", "a/./b.py", "a/../b.py", "../secret.py",
                                      "config/auth.py?x=1", "config/auth.py#part", "a\\b.py"])
def test_relative_file_sources_must_stay_within_explicit_root(locator):
    assert_error(validate_document(note(contexts=[context("filesystem", locator="file:///srv/plain")],
        sources=[source("file", locator=locator, context="work")])), "E_CONTEXT")


@pytest.mark.parametrize("kind", ["code", "file"])
def test_relative_file_or_code_source_needs_supported_explicit_context(kind):
    for contexts, selected in [([], None), ([context()], "work")]:
        src = source(kind, locator="config/auth.json")
        if selected:
            src["context"] = selected
        assert_error(validate_document(note(contexts=contexts, sources=[src])), "E_CONTEXT")
    parsed(validate_document(note(sources=[source(kind, locator="https://example.test/config/auth.json",
                                                   revision="edition-two")])))


@pytest.mark.parametrize("locator", ["https://example.test/repo.git", "/srv/repository",
                                      "git@example.test:organization/repo.git"])
def test_git_context_locator_profiles_and_full_object_ids(locator):
    contexts = [context("git_repository", locator=locator, details={"commit": SHA40, "branch": "main"})]
    doc = parsed(validate_document(note(contexts=contexts,
        sources=[source("publication", context="work", revision=SHA64,
                        details={"edition": "second-edition"})])))
    assert doc["metadata"]["sources"][0]["revision"] == SHA64


@pytest.mark.parametrize("contexts", [
    [context("git_repository")], [context("git_repository", locator="relative/repo")],
    [context("git_repository", locator="https://example.test/r.git", details={"commit": "deadbee"})],
    [context("git_repository", locator="https://example.test/r.git", details={"commit": "A" * 40})],
    [context("git_repository", locator="https://example.test/r.git", details={"branch": "  "})],
    [context(), context()], [context(label="  ")], [context(details=[])],
    [context(unrecognized="value")], [{"key": "work"}],
])
def test_context_shape_profile_and_uniqueness_failures(contexts):
    assert_error(validate_document(note(contexts=contexts)), "E_CONTEXT", "E_FIELD_TYPE")


@pytest.mark.parametrize("kind", ["publication", "experiment", "dataset", "code"])
def test_selected_context_controls_revision_namespace_for_every_source_type(kind):
    src = source(kind, locator="https://example.test/evidence", revision="second-edition")
    parsed(validate_document(note(sources=[src])))
    src["context"] = "work"
    assert_error(validate_document(note(contexts=[context("git_repository", locator="https://example.test/repo.git")],
                                        sources=[src])), "E_SOURCE")
    parsed(validate_document(note(contexts=[context("experiment")], sources=[src])))


def test_unknown_profiles_are_preserved_and_disclosed_without_git_assumptions():
    contexts = [context("community_survey", details={"respondents": 20, "optional": None}, x_note="keep")]
    sources = [source("field_record", context="work", revision="interview-edition-two", x_note=[1, None])]
    result = validate_document(note(contexts=contexts, sources=sources))
    doc = parsed(result)
    assert doc["metadata"]["contexts"] == contexts
    assert doc["metadata"]["sources"] == sources
    assert "W_CONTEXT_UNCHECKED" in codes(result)


def test_context_free_note_never_inherits_git_from_environment_or_neighbor(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "missing-git-dir"))
    # Intercept Git process launches without assuming any private parser design.
    original = subprocess.Popen
    def no_git(args, *a, **kw):
        command = args[0] if isinstance(args, (tuple, list)) else str(args).split()[0]
        assert Path(str(command)).name != "git", "validation must not probe Git"
        return original(args, *a, **kw)
    monkeypatch.setattr(subprocess, "Popen", no_git)
    plain = note(domain="authentication")
    git = note(domain="authentication", contexts=[context("git_repository", locator="https://example.test/repo.git")])
    result = validate_vault({"plain.md": plain, "git.md": git})
    assert result["valid"] is True, result["diagnostics"]
    assert result["documents"]["plain.md"]["document"]["metadata"]["contexts"] == []


@pytest.mark.parametrize("src", [
    {"locator": "trial"}, {"type": "experiment"}, source(locator=" "),
    source(unrecognized="not-in-details"), source(details=[]), source(context="absent"),
    source("test", details={}), source("test", details={"outcome": " "}),
    source("test", details={"outcome": "failed", "command": " "}),
    source(details={"line_start": 1}), source(details={"line_start": True, "line_end": 2}),
    source(details={"line_start": 0, "line_end": 2}), source(details={"line_start": 4, "line_end": 3}),
    source("web", locator="relative/page"), source("issue", locator="ftp://example.test/issue"),
    source("document", locator="not-a-uuid"),
    source("document", locator=TOKEN, revision="edition-two"),
    source("document", locator=TOKEN, context="work"),
])
def test_source_shape_and_known_profile_failures(src):
    assert_error(validate_document(note(contexts=[context()], sources=[src])), "E_SOURCE", "E_CONTEXT", "E_FIELD_TYPE")


def test_document_uuid_revision_and_failed_noncommand_test_are_valid_sources():
    sources = [source("document", locator=TOKEN, revision=TOKEN),
               source("test", details={"outcome": "failed", "line_start": 1, "line_end": 2})]
    parsed(validate_document(note(sources=sources)))


@pytest.mark.parametrize("omitted", ["verified_at", "verified_by", "sources"])
def test_verified_documents_require_all_three_evidence_fields(omitted):
    fields = properties(verification_state="verified", verified_at="2026-10-20T12:00:00Z",
                        verified_by="reviewer", sources=[source("publication", revision="second-edition")])
    del fields[omitted]
    assert_error(validate_document(note(fields=fields)), "E_VERIFICATION")


def test_verified_document_with_utc_string_and_explicit_evidence_is_valid():
    doc = parsed(validate_document(note(verification_state="verified", verified_at="2026-10-20T12:00:00Z",
        verified_by="reviewer", sources=[source("publication", revision="second-edition")])))
    assert doc["metadata"]["verified_at"] == "2026-10-20T12:00:00Z"


@pytest.mark.parametrize("headings", ["## Different\n", "## Claim\n\n## Claim\n", "## *Claim*\n"])
def test_source_section_requires_unique_exact_plain_heading(headings):
    assert_error(validate_document(note(headings, sources=[source(section="Claim")])), "E_SOURCE")


def test_source_section_and_setext_plain_heading_resolve_without_body_graph_edges():
    body = "Claim\n=====\n\nObservation.\n"
    doc = parsed(validate_document(note(body, sources=[source(section="Claim")])))
    assert any(h["text"] == "Claim" and h["level"] == 1 for h in doc["headings"])
    assert doc["links"] == []


def test_rich_blocks_preserve_exact_utf8_source_and_lexical_boundaries():
    table = "| Name | Reference |\n|:---|---:|\n| café | [[Elsewhere\\|display]] |\n"
    mermaid = "```mermaid custom-info\nflowchart LR\n  A[[NotALink]] --> B\n```\n"
    code = "~~~python\n# Not a heading\n[[NotCodeLink]]\n~~~\n"
    body = "Intro é.\n\n# Example\n\n## Details\n\n" + table + "\nExplanation.\n\n" + mermaid + "\n" + code
    result = validate_document(note(body))
    doc = parsed(result)
    assert doc["body"] == body
    assert [l["target_text"] for l in doc["links"]] == ["Elsewhere"]
    assert doc["links"][0]["raw_link"] == "[[Elsewhere\\|display]]"
    assert [h["text"] for h in doc["headings"]] == ["Example", "Details"]
    raw = doc["canonical_markdown"].encode()
    for block in doc["blocks"]:
        start, end = block["start_byte"], block["end_byte"]
        assert 0 <= start < end <= len(raw)
        raw[start:end].decode("utf-8")
        assert isinstance(block["heading_path"], list)
    for kind, original in [("table", table), ("mermaid", mermaid), ("code", code)]:
        spans = [raw[b["start_byte"]:b["end_byte"]].decode() for b in doc["blocks"] if b["kind"] == kind]
        assert any(original.rstrip("\n") in span for span in spans), (kind, spans)
    assert "W_MERMAID_UNCHECKED" in codes(result)


@pytest.mark.parametrize("body", ["```python\nprint(1)\n", "~~~unknown\ncode\n", "````text\n```\n"])
def test_code_fences_must_close_explicitly(body):
    assert_error(validate_document(note(body)), "E_UNCLOSED_FENCE")


@pytest.mark.parametrize("info", ["Mermaid", "mermaidish", "unknown-language"])
def test_mermaid_detection_requires_exact_first_info_word(info):
    doc = parsed(validate_document(note(f"```{info}\n[[Literal]]\n```\n")))
    assert any(b["kind"] == "code" for b in doc["blocks"])
    assert not any(b["kind"] == "mermaid" for b in doc["blocks"])
    assert doc["links"] == []


@pytest.mark.parametrize("body", [
    "`[[Hidden]]`\n", "`` literal ` [[Hidden]] ``\n", "    [[Hidden]]\n",
    "<!-- [[Hidden]] -->\n", "%% [[Hidden]] %%\n", "$$\n[[Hidden]]\n$$\n",
    "<script>\n[[Hidden]]\n</script>\n", "![[Hidden]]\n", "![image [[Hidden]]](Elsewhere.md)\n",
])
def test_literal_and_opaque_regions_are_preserved_without_speculative_edges(body):
    doc = parsed(validate_document(note(body)))
    assert doc["body"] == body
    assert doc["links"] == []


@pytest.mark.parametrize(("inline", "targets", "warning"), [
    ("[[Target]]", ["Target"], None),
    ("[[Target]](https://example.com)", ["Target"], None),
    ("[Outer [[Target]]](https://example.com)", [], None),
    (r"\[[Target]]", [], None), (r"\\[[Target]]", ["Target"], None),
    (r"\\\[[Target]]", [], None),
    ("[[ Target ]]", [], "W_WIKILINK_SYNTAX"),
    ("[[Target|one|two]]", [], "W_WIKILINK_SYNTAX"),
    ("[[Target", [], "W_WIKILINK_SYNTAX"),
    ("[[outer [[Nested]]", [], "W_WIKILINK_SYNTAX"),
    ("[[Target|]]", [], "W_WIKILINK_SYNTAX"),
    ("[[Target#]]", [], "W_WIKILINK_SYNTAX"),
    ("[[]]", [], "W_WIKILINK_SYNTAX"),
    (r"[[Target\name]]", [], "W_WIKILINK_SYNTAX"),
    ("![[Target]]", [], None),
    ("[[Percent%20literal]]", ["Percent%20literal"], None),
    ("[[*literal*]]", ["*literal*"], None),
])
def test_wikilink_normative_lexical_precedence(inline, targets, warning):
    result = validate_document(note(inline + "\n"))
    doc = parsed(result)
    assert [l["target_text"] for l in doc["links"]] == targets
    assert [l["ordinal"] for l in doc["links"]] == list(range(len(targets)))
    if warning:
        assert warning in codes(result)
    if targets:
        assert doc["links"][0]["raw_link"] == "[[" + inline.split("[[", 1)[1].split("]]", 1)[0] + "]]"


def test_table_escaped_alias_resolves_and_keeps_raw_original_syntax():
    raw_link = "[[folder/Target\\|Useful display]]"
    result = validate_vault({"source.md": note(f"| A | B |\n|---|---|\n| x | {raw_link} |\n"),
                             "folder/Target.md": note()})
    assert result["valid"] is True, result["diagnostics"]
    link = result["documents"]["source.md"]["document"]["links"][0]
    assert link["raw_link"] == raw_link and link["target_text"] == "folder/Target"
    assert link["resolution"] == "resolved"
    assert link["target_document_id"] == result["documents"]["folder/Target.md"]["document"]["metadata"]["id"]


def test_baseline_vault_matches_every_manifest_link_binding():
    documents = {p.relative_to(FIXTURES / "baseline").as_posix(): p.read_text(encoding="utf-8")
                 for p in (FIXTURES / "baseline").rglob("*.md")}
    result = validate_vault(documents, knowledge_base=MANIFEST["knowledge_base"], domains=MANIFEST["domains"])
    assert result["valid"] is True, result["diagnostics"]
    assert result["summary"]["files"] == 6
    assert result["summary"]["errors"] == 0
    for expected in MANIFEST["baseline_links"]:
        links = result["documents"][expected["source_path"]]["document"]["links"]
        assert len(links) == 6
        link = links[expected["ordinal"]]
        for field in ("ordinal", "raw_link", "target_document_id", "target_anchor"):
            assert link[field] == expected[field]
        assert link["resolution"] == ("ambiguous" if expected["diagnostic"] == "W_LINK_AMBIGUOUS" else "resolved")
    assert "W_LINK_AMBIGUOUS" in codes(result)


def test_standard_reference_links_percent_decoding_and_relative_paths():
    body = ("[first][target]\n[second][target]\n[target][]\n\n"
            "[target]: ../Target%20Note.md#Plain%20heading\n\n"
            "[direct](.././sub/../Target%20Note.md#Plain%20heading)\n"
            "[escaped-root](../../Target%20Note.md)\n"
            "[literal-percent](../A%2520B.md)\n"
            "[web](https://example.test/Target.md) ![image](../Target%20Note.md)\n"
            "[code](../module.py)\n")
    result = validate_vault({"sub/Source.md": note(body),
                             "Target Note.md": note("## Plain heading\n\nText.\n"),
                             "A%20B.md": note()})
    assert result["valid"] is True, result["diagnostics"]
    links = result["documents"]["sub/Source.md"]["document"]["links"]
    assert len(links) == 6
    assert [l["ordinal"] for l in links] == list(range(6))
    assert all(l["kind"] == "markdown" for l in links)
    assert [l["resolution"] for l in links] == ["resolved"] * 4 + ["unresolved", "resolved"]
    assert all(l["target_anchor"] == "Plain heading" for l in links[:4])
    assert links[0]["raw_link"] == "[first][target]"
    assert links[1]["raw_link"] == "[second][target]"
    assert links[2]["raw_link"] == "[target][]"


def test_targets_require_exact_paths_not_titles_aliases_or_casefold():
    body = "[[Target]] [[target]] [[Descriptive title]] [[Other name]] [[folder/Target.md]]\n"
    result = validate_vault({"Source.md": note(body),
                             "folder/Target.md": note(title="Descriptive title", aliases=["Other name"])})
    assert result["valid"] is True, result["diagnostics"]
    links = result["documents"]["Source.md"]["document"]["links"]
    assert [l["resolution"] for l in links] == ["resolved", "unresolved", "unresolved", "unresolved", "resolved"]
    assert all(l["target_document_id"] is None for l in links[1:4])


@pytest.mark.parametrize(("headings", "anchor", "resolution", "warning"), [
    ("## Plain heading\n", "Plain heading", "resolved", None),
    ("## Plain heading\n", "plain heading", "unresolved", "W_LINK_UNRESOLVED"),
    ("## Plain heading\n", "plain-heading", "unresolved", "W_LINK_UNRESOLVED"),
    ("## Claim\n\n## Claim\n", "Claim", "ambiguous", "W_LINK_AMBIGUOUS"),
    ("## *Claim*\n", "Claim", "unresolved", "W_LINK_UNRESOLVED"),
    ("## Claim\n", "Absent", "unresolved", "W_LINK_UNRESOLVED"),
])
def test_exact_unique_plain_heading_links(headings, anchor, resolution, warning):
    body = headings + f"\n[[#{anchor}]]\n"
    result = validate_document(note(body))
    link = parsed(result)["links"][0]
    assert link["target_anchor"] == anchor
    assert link["resolution"] == resolution
    if warning:
        assert warning in codes(result)


@pytest.mark.parametrize("anchor", ["Parent#Child", "^block-id"])
def test_unsupported_nested_and_block_anchors_warn_without_binding(anchor):
    result = validate_document(note(f"## {anchor}\n\n[[#{anchor}]]\n"))
    links = parsed(result)["links"]
    assert len(links) == 1 and links[0]["resolution"] != "resolved"
    assert "W_EXTENSION_UNSUPPORTED" in codes(result)


def test_standalone_self_and_unavailable_external_links_keep_order():
    content = note("## Plain heading\n\n[[#Plain heading]] [same](#Plain%20heading) [[Missing]]\n")
    result = validate_document(content, path="folder/Current.md")
    links = parsed(result)["links"]
    assert [l["kind"] for l in links] == ["wiki", "markdown", "wiki"]
    assert [l["resolution"] for l in links] == ["resolved", "resolved", "unresolved"]
    assert [l["ordinal"] for l in links] == [0, 1, 2]
    assert "W_LINK_UNRESOLVED" in codes(result)


@pytest.mark.parametrize("path", ["/absolute.md", "x.MD", "x.txt", "a//b.md", "a/./b.md",
    "a/../b.md", "a\\b.md", "a/#b.md", "a/pipe|name.md", "a/[x].md", "a/ b.md",
    "a /b.md", "a/b.md ", ".tribal-staging/new.md", "a\x00b.md"])
def test_invalid_paths(path):
    assert_error(validate_document(note(), path=path), "E_PATH")


def test_overlong_path_uses_storage_limit_error():
    # Spec 2.1 requires E_LIMIT for projected values beyond acceptance limits.
    assert_error(validate_document(note(), path="x" * 510 + ".md"), "E_LIMIT")


def test_path_codepoint_limit_accepts_512_and_preserves_unicode_spelling():
    path = "界" * 509 + ".md"
    result = validate_document(note(), path=path)
    parsed(result)
    assert result["path"] == path


@pytest.mark.parametrize("pair", [("One.md", "one.md"), ("Å.md", "A\u030a.md"),
                                     ("Straße.md", "STRASSE.md"), ("Σ.md", "ς.md")])
def test_portable_path_collisions_use_normalization_and_full_casefold(pair):
    result = validate_vault({pair[0]: note(), pair[1]: note()})
    assert_error(result, "E_PATH")
    assert result["summary"]["files"] == 2


def test_duplicate_uuid_is_rejected_independently_of_path_and_content():
    identity = str(uuid.uuid4())
    result = validate_vault({"a.md": note(id=identity), "b.md": note("Different body.\n", id=identity)})
    assert_error(result, "E_IDENTITY_COLLISION")


def test_mixed_knowledge_bases_are_rejected_even_without_explicit_registry():
    result = validate_vault({"a.md": note(), "b.md": note(knowledge_base="another-kb")})
    assert_error(result, "E_ASSIGNMENT")


def test_invalid_batch_files_do_not_stop_validation_of_other_files_or_links():
    docs = {"yaml.md": "---\na: [\n---\nBody.\n", "utf8.md": b"\xff",
            "metadata.md": note(title=" ", kind="invalid"),
            "good.md": note("[[Absent]]\n"), "other.md": note()}
    result = validate_vault(docs)
    assert_error(result, "E_FRONTMATTER")
    assert set(result["documents"]) == set(docs)
    assert {"E_FRONTMATTER", "E_ENCODING", "E_REQUIRED_FIELD", "E_FIELD_TYPE", "W_LINK_UNRESOLVED"} <= codes(result)
    assert result["documents"]["good.md"]["valid"] is True
    assert result["documents"]["other.md"]["valid"] is True
    assert result["summary"]["files"] == len(docs)
    for severity, key in [("error", "errors"), ("warning", "warnings")]:
        assert result["summary"][key] == sum(d["severity"] == severity for d in result["diagnostics"])
    assert all(d["path"] in docs for d in result["diagnostics"])


@pytest.mark.parametrize(("count", "valid"), [(2048, True), (2049, False)])
def test_summary_byte_boundary_not_character_count(count, valid):
    summary = "😀" * count
    result = validate_document(note(summary=summary))
    if valid:
        assert parsed(result)["metadata"]["summary"] == summary
    else:
        assert_error(result, "E_LIMIT")


@pytest.mark.parametrize(("field", "count", "valid"), [("target", 1024, True), ("target", 1025, False),
    ("anchor", 255, True), ("anchor", 256, False), ("heading", 255, True), ("heading", 256, False),
    ("raw", 16384, True), ("raw", 16385, False)])
def test_link_and_heading_projection_boundaries(field, count, valid):
    if field == "target":
        body = "[[" + "界" * count + "]]\n"
    elif field == "anchor":
        body = "[[Missing#" + "界" * count + "]]\n"
    elif field == "heading":
        body = "# " + "界" * count + "\n"
    else:
        body = "[[x|" + "a" * (count - 6) + "]]\n"
    result = validate_document(note(body))
    if valid:
        doc = parsed(result)
        assert doc["body"] == body
        if field != "heading":
            assert len(doc["links"]) == 1
    else:
        assert_error(result, "E_LIMIT")


@pytest.mark.parametrize("where", ["contexts", "sources"])
@pytest.mark.parametrize(("count", "valid"), [(8192, True), (8193, False)])
def test_context_and_source_locator_decoded_byte_limits(where, count, valid):
    item = context(locator="x" * count) if where == "contexts" else source(locator="x" * count)
    result = validate_document(note(**{where: [item]}))
    if valid:
        assert parsed(result)["metadata"][where][0]["locator"] == "x" * count
    else:
        assert_error(result, "E_LIMIT")


def test_canonical_file_cap_includes_final_newline_but_excludes_transport():
    empty = note("```text\n\n```\n")
    exact = empty.replace("```text\n\n", "```text\n" + "x" * (CAP - len(empty.encode())) + "\n")
    assert len(exact.encode()) == CAP
    transported = exact.replace("---\n", f"---\ntribal_base_revision: {TOKEN}\n", 1)
    doc = parsed(validate_document(transported))
    assert len(doc["canonical_markdown"].encode()) == CAP
    assert doc["content_hash"] == hashlib.sha256(exact.encode()).hexdigest()
    # Missing final newline is appended before the cap is evaluated.
    oversized = exact[:-1] + "x"
    assert_error(validate_document(oversized), "E_LIMIT")


def test_independent_metadata_errors_have_actionable_structured_diagnostics():
    result = validate_document(note(title="  ", kind="bad-kind", status="deleted", tags="one"), path="bad.md")
    assert result["valid"] is False
    errors = [d for d in result["diagnostics"] if d["severity"] == "error"]
    fields = {d["field"] for d in errors}
    assert {"title", "kind", "status", "tags"} <= fields
    required = {"code", "severity", "message", "path", "line", "column", "field",
                "expected", "actual", "hint", "excerpt"}
    for item in errors:
        assert required <= item.keys()
        assert item["path"] == "bad.md"
        assert isinstance(item["line"], int) and item["line"] > 0
        assert isinstance(item["column"], int) and item["column"] > 0
        assert item["message"] and item["hint"] and item["expected"] is not None
        assert item["excerpt"]
    json.dumps(result, allow_nan=False)


def test_locations_reference_normalized_input_before_transport_removal():
    submitted = note("## Example\n\n[[Absent]]\n", kind="bad-kind",
                     extra=f"tribal_base_revision: {TOKEN}\n")
    submitted = submitted.replace("---\n", "---\n# preserve this comment\n", 1)
    normalized = submitted
    result = validate_document(submitted.replace("\n", "\r\n"), path="positions.md")
    error = next(d for d in result["diagnostics"] if d["field"] == "kind" and d["severity"] == "error")
    lines = normalized.splitlines()
    assert error["line"] == next(i for i, s in enumerate(lines, 1) if s.startswith("kind:"))
    assert "bad-kind" in error["excerpt"]
    # Recoverable field errors may retain a document, but positions should also
    # be checked using an otherwise-valid file to avoid requiring partial output.
    good = normalized.replace('kind: "bad-kind"', 'kind: "finding"')
    doc = parsed(validate_document(good.replace("\n", "\r\n")))
    heading = next(h for h in doc["headings"] if h["text"] == "Example")
    link = doc["links"][0]
    assert heading["line"] == lines.index("## Example") + 1
    assert link["line"] == lines.index("[[Absent]]") + 1
    assert heading["column"] == link["column"] == 1


def test_nested_context_error_has_field_location_and_bounded_long_value_preview():
    submitted = note(extra="contexts:\n  - key: work\n    type: git_repository\n    locator: https://example.test/repo.git\n    details:\n      commit: deadbee\n")
    result = validate_document(submitted, path="nested.md")
    item = next(d for d in result["diagnostics"] if d["code"] == "E_CONTEXT" and d["field"] == "contexts[0].details.commit")
    assert item["line"] == submitted.splitlines().index("      commit: deadbee") + 1
    assert "deadbee" in item["excerpt"] and item["hint"]
    result = validate_document(note(summary="z" * 8193))
    item = next(d for d in result["diagnostics"] if d["code"] == "E_LIMIT")
    assert "z" * 8193 not in json.dumps(item)
    assert len(json.dumps(item)) < 8193


def test_cli_file_json_matches_library_payload_and_warnings_exit_zero(tmp_path):
    path = tmp_path / "warning.md"
    content = note("[[Unavailable]]\n")
    path.write_text(content, encoding="utf-8")
    completed = cli(path, "--json")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    doc = parsed(result)
    assert "W_LINK_UNRESOLVED" in codes(result)
    library = validate_document(content, path="warning.md")
    assert doc == library["document"]
    assert {"code", "message", "line", "column", "hint", "excerpt"} <= result["diagnostics"][0].keys()


def test_cli_text_errors_include_verbose_location_and_metadata_guidance(tmp_path):
    path = tmp_path / "bad.md"
    path.write_text(note(kind="bad-kind"), encoding="utf-8")
    completed = cli(path)
    assert completed.returncode == 1
    text = completed.stdout + completed.stderr
    assert "E_FIELD_TYPE" in text and "bad.md" in text and "bad-kind" in text
    assert "kind" in text
    # Output need not use literal field labels, but it must actually show the
    # structured explanation, correction, offending value, and source line.
    errors = validate_document(path.read_text(encoding="utf-8"), path="bad.md")["diagnostics"]
    item = next(d for d in errors if d["code"] == "E_FIELD_TYPE")
    assert item["message"] in text and item["hint"] in text
    assert 'kind: "bad-kind"' in text and "finding" in text
    assert str(item["line"]) in text


def test_cli_json_invalid_input_keeps_all_structured_errors(tmp_path):
    path = tmp_path / "bad.md"
    path.write_text(note(kind="bad-kind", tags="single"), encoding="utf-8")
    completed = cli(path, "--json")
    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert_error(result, "E_FIELD_TYPE")
    assert {"kind", "tags"} <= {d["field"] for d in result["diagnostics"]}


def test_cli_assignment_options_are_enforced(tmp_path):
    path = tmp_path / "note.md"
    path.write_text(note(), encoding="utf-8")
    good = cli(path, "--json", "--knowledge-base", "fixture-kb", "--domain", "research", "botany")
    assert good.returncode == 0, good.stdout + good.stderr
    bad = cli(path, "--json", "--knowledge-base", "other", "--domain", "botany")
    assert bad.returncode == 1
    assert "E_ASSIGNMENT" in codes(json.loads(bad.stdout))


def test_cli_directory_recurses_lowercase_md_and_ignores_tool_directories_without_git(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "One.md").write_text(note(), encoding="utf-8")
    (vault / "nested").mkdir()
    (vault / "nested" / "Two.md").write_text(note(), encoding="utf-8")
    for ignored in ("README.txt", "UPPER.MD"):
        (vault / ignored).write_text("not a knowledge file\n", encoding="utf-8")
    for name in (".git", ".obsidian", ".venv", "venv", ".tribal-staging"):
        (vault / name).mkdir()
        (vault / name / "ignored.md").write_text("ordinary non-Tribal content\n", encoding="utf-8")
    # An executable trap makes CLI Git probing observable without changing code.
    binaries = tmp_path / "bin"
    binaries.mkdir()
    marker = tmp_path / "git-was-run"
    git = binaries / "git"
    git.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 97\n", encoding="utf-8")
    git.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(binaries) + os.pathsep + env.get("PATH", "")
    completed = cli(vault, "--json", env=env)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not marker.exists(), "validation must not probe or initialize Git"
    result = json.loads(completed.stdout)
    assert result["valid"] is True
    assert result["summary"]["files"] == 2
    assert set(result["documents"]) == {"One.md", "nested/Two.md"}


def test_cli_directory_diagnoses_selected_ordinary_markdown_instead_of_silently_converting(tmp_path):
    (tmp_path / "valid.md").write_text(note(), encoding="utf-8")
    (tmp_path / "ordinary.md").write_text("# Ordinary project docs\n", encoding="utf-8")
    completed = cli(tmp_path, "--json")
    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["summary"]["files"] == 2
    assert_error(result["documents"]["ordinary.md"], "E_FRONTMATTER")
    assert result["documents"]["valid.md"]["valid"] is True


def test_cli_usage_and_filesystem_errors_exit_two(tmp_path):
    absent = cli(tmp_path / "absent.md", "--json")
    assert absent.returncode == 2
    usage = subprocess.run([sys.executable, "-m", "tribal", "validate"], cwd=PROJECT,
                           capture_output=True, text=True, timeout=30)
    assert usage.returncode == 2
