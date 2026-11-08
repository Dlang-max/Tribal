"""Validate all public note contracts with complete, linked on-disk documents."""
import json

import pytest

from conftest import (
    NOTE_PATHS, REQUIRED_SECTIONS, assert_rejected, note_path,
    remove_field, replace_section, set_raw_field,
)


# Verify all eleven published examples form a valid linked vault.
def test_all_eleven_published_examples_form_a_valid_linked_vault(validate, valid_vault):
    assert len(list(valid_vault.rglob("*.md"))) == 11
    assert validate(valid_vault, expected_project_id="checkout-demo") == []


# Verify each required section is enforced.
@pytest.mark.parametrize("note_type,section", [
    (kind, section) for kind, sections in REQUIRED_SECTIONS.items() for section in sections
])
def test_each_required_section_is_enforced(validate, valid_vault, note_type, section):
    path = note_path(valid_vault, note_type)
    path.write_text(path.read_text().replace(f"## {section}\n", f"## Other {section}\n", 1))
    assert_rejected(validate, valid_vault, path)


# Verify every type rejects undocumented metadata.
@pytest.mark.parametrize("note_type", NOTE_PATHS)
def test_every_type_rejects_undocumented_metadata(validate, valid_vault, note_type):
    path = note_path(valid_vault, note_type)
    set_raw_field(path, "undocumented_field", '"unexpected"')
    assert_rejected(validate, valid_vault, path)


# Verify common required fields cannot be omitted.
@pytest.mark.parametrize("field", ["spec_version", "id", "type", "title", "project_id", "created_at", "updated_at", "status"])
def test_common_required_fields_cannot_be_omitted(validate, valid_vault, field):
    path = note_path(valid_vault)
    remove_field(path, field)
    assert_rejected(validate, valid_vault, path)


# Verify type specific required fields cannot be omitted.
@pytest.mark.parametrize("note_type,field", [
    ("repository", "repository_key"),
    ("branch", "repository"), ("branch", "branch_name"), ("branch", "work_status"),
    ("commit", "repository"), ("commit", "commit_hash"),
    *[("merge", field) for field in ("repository", "source_event_id", "observed_at", "source_ref", "source_commit", "target_branch", "target_before", "target_after", "merge_kind")],
    *[("push", field) for field in ("repository", "source_event_id", "observed_at", "remote_name")],
    ("decision", "decision_state"),
])
def test_type_specific_required_fields_cannot_be_omitted(validate, valid_vault, note_type, field):
    path = note_path(valid_vault, note_type)
    remove_field(path, field)
    assert_rejected(validate, valid_vault, path)


# Verify common metadata types values and closed fields.
@pytest.mark.parametrize("field,value", [
    ("spec_version", "true"), ("spec_version", '"1"'), ("spec_version", "2"),
    ("id", "false"), ("id", '"   "'), ("title", "42"),
    ("title", '"Line one\\nLine two"'), ("project_id", "[]"),
    ("status", "complete"), ("type", "issue"),
    ("tags", '"single"'), ("tags", '["#bad"]'), ("tags", '["ok", "ok"]'),
    ("tags", '["ok", 12]'), ("tags", '[" "]'),
    ("aliases", '["Alternate", "Alternate"]'), ("aliases", '[""]'),
    ("session_id", "null"), ("repository", "null"), ("source_event_id", '" "'),
    ("observed_at", '"2026-11-07T12:00:00"'),
    ("embedding", "[0.1, 0.2]"), ("model", '"embedding-model"'),
    ("content_hash", '"abc123"'), ("revision", "2"),
])
def test_common_metadata_types_values_and_closed_fields(validate, valid_vault, field, value):
    path = note_path(valid_vault)
    set_raw_field(path, field, value)
    assert_rejected(validate, valid_vault, path)


# Verify type metadata values are checked.
@pytest.mark.parametrize("note_type,field,value", [
    ("repository", "repository_key", '" "'), ("repository", "remote_url", "[]"),
    ("branch", "work_status", "running"), ("branch", "branch_name", "[]"),
    ("commit", "commit_hash", '"ABCDEF"'), ("commit", "commit_hash", '"not-a-hash"'),
    ("merge", "merge_kind", "rebase"), ("merge", "target_branch", '" "'),
    ("push", "remote_name", '" "'), ("push", "remote_url", "false"),
    ("decision", "decision_state", "approved"),
    ("handoff", "branch_name", "false"), ("guide", "verified_commit", '"zzz"'),
    ("guide", "verified_at", '"yesterday"'),
])
def test_type_metadata_values_are_checked(validate, valid_vault, note_type, field, value):
    path = note_path(valid_vault, note_type)
    set_raw_field(path, field, value)
    assert_rejected(validate, valid_vault, path)


# Verify entrypoint overviews omit repository metadata.
@pytest.mark.parametrize("note_type", ["project", "repository"])
def test_entrypoint_overviews_omit_repository_metadata(validate, valid_vault, note_type):
    path = note_path(valid_vault, note_type)
    set_raw_field(path, "repository", '"[[Repositories/Checkout Service]]"')
    assert_rejected(validate, valid_vault, path)


# Verify source context metadata requires repository.
@pytest.mark.parametrize("note_type,field", [("handoff", "branch_name"), ("handoff", "head_commit"), ("guide", "verified_commit")])
def test_source_context_metadata_requires_repository(validate, valid_vault, note_type, field):
    path = note_path(valid_vault, note_type)
    remove_field(path, "repository")
    if note_type == "handoff":
        remove_field(path, "head_commit" if field == "branch_name" else "branch_name")
    assert_rejected(validate, valid_vault, path)


# Verify project wide knowledge can omit repository.
@pytest.mark.parametrize("note_type", ["finding", "insight", "decision", "handoff", "guide"])
def test_project_wide_knowledge_can_omit_repository(validate, valid_vault, note_type):
    path = note_path(valid_vault, note_type)
    remove_field(path, "repository")
    for field in ("branch_name", "head_commit", "verified_commit"):
        remove_field(path, field)
    text = path.read_text()
    if "[[Projects/Checkout Platform]]" not in text:
        path.write_text(text.replace("## Related notes\n", "## Related notes\n- [[Projects/Checkout Platform]]\n", 1))
    assert validate(valid_vault) == []


# Verify lowercase hex hashes are not constrained to sha1 length.
@pytest.mark.parametrize("length", [12, 40, 64])
def test_lowercase_hex_hashes_are_not_constrained_to_sha1_length(validate, valid_vault, length):
    path = note_path(valid_vault, "commit")
    set_raw_field(path, "commit_hash", json.dumps("a" * length))
    assert validate(valid_vault) == []


# Verify fast forward result must equal source tip.
def test_fast_forward_result_must_equal_source_tip(validate, valid_vault):
    path = note_path(valid_vault, "merge")
    set_raw_field(path, "target_after", '"cccccccccccccccccccccccccccccccccccccccc"')
    assert_rejected(validate, valid_vault, path)


# Verify merge cannot record unchanged target as completed integration.
def test_merge_cannot_record_unchanged_target_as_completed_integration(validate, valid_vault):
    path = note_path(valid_vault, "merge")
    set_raw_field(path, "merge_kind", "merge_commit")
    set_raw_field(path, "target_after", '"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"')
    assert_rejected(validate, valid_vault, path)


# Verify ordinary prose about embedding models is allowed.
def test_ordinary_prose_about_embedding_models_is_allowed(validate, valid_vault):
    path = note_path(valid_vault, "insight")
    with path.open("a") as file:
        file.write("\n## Future search\nCompare embedding models after the storage adapter exists.\n")
    assert validate(valid_vault) == []


# Verify squash result is not required to differ from source hash.
def test_squash_result_is_not_required_to_differ_from_source_hash(validate, valid_vault):
    path = note_path(valid_vault, "merge")
    set_raw_field(path, "merge_kind", "squash")
    replace_section(path, "Summary", "The collector reports completed squash integration of discount validation into main. Git ancestry was not verified by this offline validator.")
    assert validate(valid_vault) == []
