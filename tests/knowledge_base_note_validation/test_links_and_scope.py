"""Cross-note rules use complete vaults and real filesystem boundaries."""
import json

import pytest

from conftest import assert_rejected, note_path, replace_section, set_raw_field


# Add a real body wikilink outside the existing required sections.
def append_body_link(path, target):
    with path.open("a") as file:
        file.write(f"\n## Further context\nSee [[{target}]].\n")


# Copy an example note with an independently chosen publication identity.
def duplicate_note(vault, note_type, relative_path, identity):
    source = note_path(vault, note_type)
    destination = vault / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    set_raw_field(destination, "id", json.dumps(identity))
    return destination


# Verify invalid internal links are rejected.
@pytest.mark.parametrize("target", [
    "Missing/Unpublished Note", "repositories/Checkout Service", "Repositories/checkout service",
    "Repositories/Checkout Service.md", "/Repositories/Checkout Service",
    "../Repositories/Checkout Service", "Repositories/./Checkout Service",
    "Repositories/../Repositories/Checkout Service", "Repositories\\Checkout Service",
    "Repositories//Checkout Service", "Findings/Expired Code Accepted",
    "Repositories/Checkout Service#Missing section",
])
def test_invalid_internal_links_are_rejected(validate, valid_vault, target):
    path = note_path(valid_vault)
    append_body_link(path, target)
    assert_rejected(validate, valid_vault, path)


# Verify body links support display aliases and real heading fragments.
@pytest.mark.parametrize("target", [
    "Repositories/Checkout Service|Repository entry point",
    "Repositories/Checkout Service#Working instructions",
    "Repositories/Checkout Service#Working instructions|Setup guidance",
])
def test_body_links_support_display_aliases_and_real_heading_fragments(validate, valid_vault, target):
    append_body_link(note_path(valid_vault), target)
    assert validate(valid_vault) == []


# Verify repository metadata is an unaliased repository note link.
@pytest.mark.parametrize("raw", [
    '"[[Repositories/Checkout Service|Alias]]"',
    '"[[Repositories/Checkout Service#Purpose]]"',
    '"Repositories/Checkout Service"',
    '"[[Findings/Expired Code Accepted]]"',
    '"[[Projects/Checkout Platform]]"',
    '"[[Missing/Repository]]"',
])
def test_repository_metadata_is_an_unaliased_repository_note_link(validate, valid_vault, raw):
    path = note_path(valid_vault, "branch")
    set_raw_field(path, "repository", raw)
    assert_rejected(validate, valid_vault, path)


# Verify related notes section needs a real internal link.
@pytest.mark.parametrize("content", [
    "No related notes are known.",
    "`[[Repositories/Checkout Service]]` is just example syntax.",
    "```markdown\n[[Repositories/Checkout Service]]\n```",
    "[Repository](https://example.com/repository)",
])
def test_related_notes_section_needs_a_real_internal_link(validate, valid_vault, content):
    path = note_path(valid_vault)
    replace_section(path, "Related notes", content)
    assert_rejected(validate, valid_vault, path)


# Verify project repositories section links to repository type.
def test_project_repositories_section_links_to_repository_type(validate, valid_vault):
    path = note_path(valid_vault, "project")
    replace_section(path, "Repositories", "[[Guides/Run Checkout Checks]] describes our checks.")
    assert_rejected(validate, valid_vault, path)


# Verify repository related notes link back to project type.
def test_repository_related_notes_link_back_to_project_type(validate, valid_vault):
    path = note_path(valid_vault, "repository")
    replace_section(path, "Related notes", "- [[Guides/Run Checkout Checks]]\n- [[Branches/Checkout Discount Validation]]")
    assert_rejected(validate, valid_vault, path)


# Verify expected project identity is enforced.
def test_expected_project_identity_is_enforced(validate, valid_vault):
    assert_rejected(lambda root: validate(root, expected_project_id="different-project"), valid_vault)


# Verify mixed project ids are rejected without explicit expected id.
def test_mixed_project_ids_are_rejected_without_explicit_expected_id(validate, valid_vault):
    path = note_path(valid_vault)
    set_raw_field(path, "project_id", '"other-project"')
    assert_rejected(validate, valid_vault, path)


# Verify note ids are unique across types.
def test_note_ids_are_unique_across_types(validate, valid_vault):
    path = note_path(valid_vault)
    set_raw_field(path, "id", '"commit-note-demo"')
    assert_rejected(validate, valid_vault)


# Verify only one active project overview exists.
def test_only_one_active_project_overview_exists(validate, valid_vault):
    path = duplicate_note(valid_vault, "project", "Projects/Extra Overview.md", "extra-project-note")
    assert_rejected(validate, valid_vault)


# Verify archived project overview remains linkable.
def test_archived_project_overview_remains_linkable(validate, valid_vault):
    path = duplicate_note(valid_vault, "project", "Projects/Previous Overview.md", "previous-project-note")
    set_raw_field(path, "status", "archived")
    append_body_link(note_path(valid_vault), "Projects/Previous Overview")
    assert validate(valid_vault) == []


# Verify active repository identity cannot have two overviews.
def test_active_repository_identity_cannot_have_two_overviews(validate, valid_vault):
    duplicate_note(valid_vault, "repository", "Repositories/Duplicate Checkout.md", "duplicate-repository-note")
    assert_rejected(validate, valid_vault)


# Verify distinct repository keys allow same remote url.
def test_distinct_repository_keys_allow_same_remote_url(validate, valid_vault):
    path = duplicate_note(valid_vault, "repository", "Repositories/Separate Checkout.md", "separate-repository-note")
    set_raw_field(path, "repository_key", '"separate-checkout"')
    assert validate(valid_vault) == []


# Verify active branch identity is repository and exact ref.
def test_active_branch_identity_is_repository_and_exact_ref(validate, valid_vault):
    duplicate_note(valid_vault, "branch", "Branches/Duplicate Discount Work.md", "duplicate-branch-note")
    assert_rejected(validate, valid_vault)


# Verify same commit hash cannot produce two notes in one repository.
def test_same_commit_hash_cannot_produce_two_notes_in_one_repository(validate, valid_vault):
    duplicate_note(valid_vault, "commit", "Commits/Duplicate Discount Commit.md", "duplicate-commit-note")
    assert_rejected(validate, valid_vault)


# Verify occurrence replay identity is unique.
def test_occurrence_replay_identity_is_unique(validate, valid_vault):
    path = note_path(valid_vault, "push")
    set_raw_field(path, "source_event_id", '"merge-operation-demo"')
    assert_rejected(validate, valid_vault)


# Verify superseded status requires replacement link.
def test_superseded_status_requires_replacement_link(validate, valid_vault):
    path = note_path(valid_vault)
    set_raw_field(path, "status", "superseded")
    assert_rejected(validate, valid_vault, path)


# Verify supersession target is resolved unaliased and not self.
@pytest.mark.parametrize("target", [
    "[[Missing/Replacement]]", "[[Findings/Expired Code Accepted]]",
    "[[Insights/Validate Discounts Before Totals|Replacement]]",
    "[[Insights/Validate Discounts Before Totals#Basis]]",
])
def test_supersession_target_is_resolved_unaliased_and_not_self(validate, valid_vault, target):
    path = note_path(valid_vault)
    set_raw_field(path, "status", "superseded")
    set_raw_field(path, "superseded_by", json.dumps(target))
    assert_rejected(validate, valid_vault, path)


# Verify archived and superseded notes remain valid link targets.
def test_archived_and_superseded_notes_remain_valid_link_targets(validate, valid_vault):
    path = note_path(valid_vault)
    set_raw_field(path, "status", "superseded")
    set_raw_field(path, "superseded_by", '"[[Insights/Validate Discounts Before Totals]]"')
    set_raw_field(note_path(valid_vault, "decision"), "status", "archived")
    assert validate(valid_vault) == []


# Verify obsidian configuration tree is ignored.
def test_obsidian_configuration_tree_is_ignored(validate, valid_vault):
    hidden = valid_vault / ".obsidian/plugins/Fake Documentation.md"
    hidden.parent.mkdir(parents=True)
    hidden.write_text("Not a published note.\n")
    assert validate(valid_vault) == []


# Verify symlinked notes and directories are rejected.
@pytest.mark.parametrize("symlink_kind", ["file", "directory"])
def test_symlinked_notes_and_directories_are_rejected(validate, valid_vault, tmp_path, symlink_kind):
    external = tmp_path / "External context"
    external.mkdir()
    source = external / "External Note.md"
    source.write_bytes(note_path(valid_vault).read_bytes())
    link = valid_vault / ("External Note.md" if symlink_kind == "file" else "External context")
    link.symlink_to(source if symlink_kind == "file" else external, target_is_directory=symlink_kind == "directory")
    assert_rejected(validate, valid_vault)


# Verify symlinked vault root is rejected.
def test_symlinked_vault_root_is_rejected(validate, valid_vault, tmp_path):
    alias = tmp_path / "Vault alias"
    alias.symlink_to(valid_vault, target_is_directory=True)
    assert_rejected(validate, alias)


# Verify validation does not change any note.
def test_validation_does_not_change_any_note(validate, valid_vault):
    before = {str(path.relative_to(valid_vault)): path.read_bytes() for path in valid_vault.rglob("*") if path.is_file()}
    assert validate(valid_vault) == []
    after = {str(path.relative_to(valid_vault)): path.read_bytes() for path in valid_vault.rglob("*") if path.is_file()}
    assert after == before


# Verify issues are deterministic across repeated validation.
def test_issues_are_deterministic_across_repeated_validation(validate, valid_vault):
    set_raw_field(note_path(valid_vault), "status", "invalid")
    append_body_link(note_path(valid_vault, "guide"), "Missing/Guide Source")
    first = [(issue.path, issue.code, issue.message) for issue in validate(valid_vault)]
    second = [(issue.path, issue.code, issue.message) for issue in validate(valid_vault)]
    assert first
    assert first == second


# Verify invalid or empty vault root returns issues.
@pytest.mark.parametrize("root_kind", ["missing", "empty", "file"])
def test_invalid_or_empty_vault_root_returns_issues(validate, tmp_path, root_kind):
    root = tmp_path / "Invalid vault"
    if root_kind == "empty":
        root.mkdir()
    elif root_kind == "file":
        root.write_text("Not a directory.\n")
    assert_rejected(validate, root)


# Verify same branch ref is allowed in distinct repositories.
def test_same_branch_ref_is_allowed_in_distinct_repositories(validate, valid_vault):
    repository = duplicate_note(valid_vault, "repository", "Repositories/Other Service.md", "other-repository-note")
    set_raw_field(repository, "repository_key", '"other-service"')
    branch = duplicate_note(valid_vault, "branch", "Branches/Other Discount Work.md", "other-branch-note")
    set_raw_field(branch, "repository", '"[[Repositories/Other Service]]"')
    branch.write_text(branch.read_text().replace("- [[Repositories/Checkout Service]]", "- [[Repositories/Other Service]]"))
    assert validate(valid_vault) == []


# Verify same hash is allowed in distinct repositories.
def test_same_hash_is_allowed_in_distinct_repositories(validate, valid_vault):
    repository = duplicate_note(valid_vault, "repository", "Repositories/Checkout Fork.md", "fork-repository-note")
    set_raw_field(repository, "repository_key", '"checkout-fork"')
    commit = duplicate_note(valid_vault, "commit", "Commits/Fork Discount Commit.md", "fork-commit-note")
    set_raw_field(commit, "repository", '"[[Repositories/Checkout Fork]]"')
    commit.write_text(commit.read_text().replace("- [[Repositories/Checkout Service]]", "- [[Repositories/Checkout Fork]]"))
    assert validate(valid_vault) == []


# Verify archived branch intentions do not conflict with current active ref.
def test_archived_branch_intentions_do_not_conflict_with_current_active_ref(validate, valid_vault):
    path = duplicate_note(valid_vault, "branch", "Branches/Previous Discount Work.md", "previous-branch-note")
    set_raw_field(path, "status", "archived")
    assert validate(valid_vault) == []


# Verify fenced heading is not a real link fragment target.
def test_fenced_heading_is_not_a_real_link_fragment_target(validate, valid_vault):
    repository = note_path(valid_vault, "repository")
    with repository.open("a") as file:
        file.write("\n```markdown\n## Hidden code heading\n```\n")
    path = note_path(valid_vault)
    append_body_link(path, "Repositories/Checkout Service#Hidden code heading")
    assert_rejected(validate, valid_vault, path)


# Verify note paths reject backslashes and control characters.
@pytest.mark.parametrize("filename", ["Invalid\\Name.md", "Invalid\tName.md"])
def test_note_paths_reject_backslashes_and_control_characters(validate, valid_vault, filename):
    path = duplicate_note(valid_vault, "finding", f"Findings/{filename}", "invalid-path-note")
    assert_rejected(validate, valid_vault, path)


# Verify external markdown source links do not require local targets.
def test_external_markdown_source_links_do_not_require_local_targets(validate, valid_vault):
    path = note_path(valid_vault)
    with path.open("a") as file:
        file.write("\n## External sources\n[Upstream context](https://example.invalid/context#observation) was not independently retrieved.\n")
    assert validate(valid_vault) == []


# Verify invalid validation is also read only.
def test_invalid_validation_is_also_read_only(validate, valid_vault):
    path = note_path(valid_vault)
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes().replace(b"\n", b"\r\n"))
    before = {str(item.relative_to(valid_vault)): item.read_bytes() for item in valid_vault.rglob("*.md")}
    assert_rejected(validate, valid_vault, path)
    after = {str(item.relative_to(valid_vault)): item.read_bytes() for item in valid_vault.rglob("*.md")}
    assert after == before
