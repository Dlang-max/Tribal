"""Adversarial file, YAML, date, and Markdown inputs at the public boundary."""
import pytest

from conftest import assert_rejected, note_path, replace_section, set_raw_field


# Verify invalid file encoding and delimiters return issues.
@pytest.mark.parametrize("transform", [
    lambda data: b"\xef\xbb\xbf" + data,
    lambda data: data.replace(b"\n", b"\r\n"),
    lambda data: data.rstrip(b"\n"),
    lambda data: data.replace(b"Observation", b"Observ\xffation", 1),
    lambda data: b"\n" + data,
    lambda data: data.replace(b"---\n#", b"#", 1),
])
def test_invalid_file_encoding_and_delimiters_return_issues(validate, valid_vault, transform):
    path = note_path(valid_vault)
    path.write_bytes(transform(path.read_bytes()))
    assert_rejected(validate, valid_vault, path)


# Verify strict yaml rejects unsupported constructs without crashing.
@pytest.mark.parametrize("frontmatter", [
    'id: "duplicate-identity"\n',
    'session_id: !Custom "unsafe"\n',
    'session_id: !!python/object/apply:os.system ["echo unsafe"]\n',
    'tags: &shared ["first"]\naliases: *shared\n',
    '? [complex, key]\n: value\n',
    'tags: [unterminated\n',
    '---\nsecond_document: true\n',
])
def test_strict_yaml_rejects_unsupported_constructs_without_crashing(validate, valid_vault, frontmatter):
    path = note_path(valid_vault)
    path.write_text(path.read_text().replace("\n---\n", "\n" + frontmatter + "---\n", 1))
    assert_rejected(validate, valid_vault, path)


# Verify frontmatter must be one mapping.
@pytest.mark.parametrize("yaml_value", ['- list\n- rather than mapping', '"scalar"', '', 'null'])
def test_frontmatter_must_be_one_mapping(validate, valid_vault, yaml_value):
    path = note_path(valid_vault)
    body = path.read_text().split("\n---\n", 1)[1]
    path.write_text("---\n" + yaml_value + "\n---\n" + body)
    assert_rejected(validate, valid_vault, path)


# Verify timestamps hashes and git refs require yaml quotes.
@pytest.mark.parametrize("note_type,field,raw", [
    ("finding", "created_at", "2026-11-07T15:10:00Z"),
    ("finding", "observed_at", "2026-11-07T15:10:00Z"),
    ("guide", "verified_at", "2026-11-07T16:01:00Z"),
    ("commit", "commit_hash", "abcdefabcdef"),
    ("branch", "branch_name", "feature/discount-validation"),
    ("merge", "source_ref", "feature/discount-validation"),
    ("merge", "target_branch", "main"),
])
def test_timestamps_hashes_and_git_refs_require_yaml_quotes(validate, valid_vault, note_type, field, raw):
    path = note_path(valid_vault, note_type)
    set_raw_field(path, field, raw)
    assert_rejected(validate, valid_vault, path)


# Verify invalid created timestamps are rejected.
@pytest.mark.parametrize("raw", [
    '"2026-11-07T15:10:00"', '"2026-02-30T15:10:00Z"',
    '"2026-11-07"', '"not-a-date"', '"2026-11-07T25:00:00Z"',
    '"2026-11-07T15:10:00+02:99"', '"2026-11-07T15:10:00-05:60"',
])
def test_invalid_created_timestamps_are_rejected(validate, valid_vault, raw):
    path = note_path(valid_vault)
    set_raw_field(path, "created_at", raw)
    assert_rejected(validate, valid_vault, path)


# Verify updated time must not precede created time.
def test_updated_time_must_not_precede_created_time(validate, valid_vault):
    path = note_path(valid_vault)
    set_raw_field(path, "updated_at", '"2026-11-07T14:00:00Z"')
    assert_rejected(validate, valid_vault, path)


# Verify timestamp order uses timezone offsets.
def test_timestamp_order_uses_timezone_offsets(validate, valid_vault):
    path = note_path(valid_vault)
    set_raw_field(path, "created_at", '"2026-11-07T17:10:00+02:00"')
    set_raw_field(path, "updated_at", '"2026-11-07T10:11:00-05:00"')
    assert validate(valid_vault) == []


# Verify first body line is the matching h1.
@pytest.mark.parametrize("replacement", ["# Wrong title", "First comes prose\n# Expired Code Accepted", "## Expired Code Accepted"])
def test_first_body_line_is_the_matching_h1(validate, valid_vault, replacement):
    path = note_path(valid_vault)
    path.write_text(path.read_text().replace("# Expired Code Accepted", replacement, 1))
    assert_rejected(validate, valid_vault, path)


# Verify second h1 is rejected.
def test_second_h1_is_rejected(validate, valid_vault):
    path = note_path(valid_vault)
    with path.open("a") as file:
        file.write("\n# Another title\nExtra narrative.\n")
    assert_rejected(validate, valid_vault, path)


# Verify duplicate required h2 is rejected.
def test_duplicate_required_h2_is_rejected(validate, valid_vault):
    path = note_path(valid_vault)
    with path.open("a") as file:
        file.write("\n## Observation\nA second observation section.\n")
    assert_rejected(validate, valid_vault, path)


# Verify required sections need meaningful content.
@pytest.mark.parametrize("placeholder", ["", "   ", "TODO", "TODO: fill this in", "- TODO\n- TBD", "<!-- TODO -->"])
def test_required_sections_need_meaningful_content(validate, valid_vault, placeholder):
    path = note_path(valid_vault)
    replace_section(path, "Evidence", placeholder)
    assert_rejected(validate, valid_vault, path)


# Verify an honest limitation satisfies meaningful section requirement.
def test_an_honest_limitation_satisfies_meaningful_section_requirement(validate, valid_vault):
    replace_section(note_path(valid_vault), "Evidence", "No further source evidence is available; the recorded reproduction is the only observation.")
    assert validate(valid_vault) == []


# Verify fenced headings and links are code not document structure.
@pytest.mark.parametrize("marker", ["```", "~~~~", "````"])
def test_fenced_headings_and_links_are_code_not_document_structure(validate, valid_vault, marker):
    path = note_path(valid_vault)
    with path.open("a") as file:
        file.write(f"\n{marker}markdown\n# False H1\n## Observation\n[[Missing/Fake Note]]\n{marker}\n")
    assert validate(valid_vault) == []


# Verify required heading inside fence does not satisfy section.
@pytest.mark.parametrize("marker", ["```", "~~~"])
def test_required_heading_inside_fence_does_not_satisfy_section(validate, valid_vault, marker):
    path = note_path(valid_vault)
    replace_section(path, "Evidence", f"{marker}markdown\n## Evidence\nSource illustration.\n{marker}")
    path.write_text(path.read_text().replace("## Evidence\n", "## Other evidence\n", 1))
    assert_rejected(validate, valid_vault, path)


# Verify inline code wikilinks are not resolved.
def test_inline_code_wikilinks_are_not_resolved(validate, valid_vault):
    path = note_path(valid_vault)
    with path.open("a") as file:
        file.write("\nUse `[[Missing/Code Example]]` and ``[[Missing/Long Code Example]]`` as literal syntax examples.\n")
    assert validate(valid_vault) == []


# Verify shorter fence inside longer fence does not expose headings or links.
def test_shorter_fence_inside_longer_fence_does_not_expose_headings_or_links(validate, valid_vault):
    path = note_path(valid_vault)
    with path.open("a") as file:
        file.write("\n````markdown\n```\n# This is still code\n## Observation\n[[Missing/Still Code]]\n```\n````\n")
    assert validate(valid_vault) == []


# Verify inline code span can cross a line boundary.
def test_inline_code_span_can_cross_a_line_boundary(validate, valid_vault):
    path = note_path(valid_vault)
    with path.open("a") as file:
        file.write("\nLiteral syntax: `an example\n[[Missing/Multiline Code]]` remains code.\n")
    assert validate(valid_vault) == []


# Verify single quoted timestamps and wikilinks are accepted.
def test_single_quoted_timestamps_and_wikilinks_are_accepted(validate, valid_vault):
    path = note_path(valid_vault)
    set_raw_field(path, "created_at", "'2026-11-07T15:10:00Z'")
    set_raw_field(path, "repository", "'[[Repositories/Checkout Service]]'")
    assert validate(valid_vault) == []


# Verify html comments do not create headings or wikilinks.
def test_html_comments_do_not_create_headings_or_wikilinks(validate, valid_vault):
    path = note_path(valid_vault)
    with path.open("a") as file:
        file.write("\n<!--\n# Fake H1\n## Observation\n[[Missing/Hidden]]\n-->\n")
    assert validate(valid_vault) == []


# Verify standard explicit yaml string tags are allowed.
@pytest.mark.parametrize("raw", [
    '!!str "finding-note-demo"',
    '!<tag:yaml.org,2002:str> "finding-note-demo"',
])
def test_standard_explicit_yaml_string_tag_is_allowed(validate, valid_vault, raw):
    path = note_path(valid_vault)
    set_raw_field(path, "id", raw)
    assert validate(valid_vault) == []
