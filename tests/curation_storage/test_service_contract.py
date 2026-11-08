"""Exercise project knowledge publication through the documented public service."""
import importlib


# Require the five tool operations and receipt/graph API before storage is wired in.
def test_service_exposes_documented_async_operations():
    service = importlib.import_module("tribal_kb.service").KnowledgeBaseService
    required = (
        "search_notes", "read_note", "follow_link", "get_note_spec", "apply_changes",
        "graph", "get_request_result", "remember_request_result",
    )
    assert all(inspect.iscoroutinefunction(getattr(service, name)) for name in required)

import asyncio
import copy
import hashlib
import inspect

import pytest

from conftest import NOTE_PATHS


# Change real note content while retaining its structural identity and links.
def updated_change(documents, kind="finding", revision=1, suffix="Additional verified observation."):
    path = NOTE_PATHS[kind]
    text = documents[path].replace("\n## Related notes", f"\n{suffix}\n\n## Related notes")
    return {"action": "update", "path": path, "markdown": text, "expected_revision": revision}


# Publish every type and verify exact object bytes, manifest metadata, and graph links.
@pytest.mark.asyncio
async def test_full_eleven_note_batch_rehydrates_and_has_deterministic_graph(make_service, changes, documents):
    service, objects, catalog = make_service()
    result = await service.apply_changes(changes)
    assert result["status"] == "updated", result
    assert {tuple(sorted(note.items())) for note in result["notes"]} == {
        tuple(sorted({"path": path, "action": "created"}.items())) for path in documents
    }
    manifest = catalog.list_notes("checkout-demo")
    assert len(manifest) == 11
    assert len(objects.objects) == 11
    for note in manifest:
        loaded = await service.read_note(note["id"])
        assert loaded["markdown"] == documents[note["path"]]
        assert loaded["revision"] == 1
        assert loaded["path"] == note["path"]
        assert note["content_hash"] == hashlib.sha256(loaded["markdown"].encode()).hexdigest()
        assert objects.objects[note["object_key"]] == loaded["markdown"].encode()
        assert not note["object_key"].startswith("/")
        assert "markdown" not in note
    graph = await service.graph()
    assert graph["project_id"] == "checkout-demo"
    assert {n["id"] for n in graph["nodes"]} == {n["id"] for n in manifest}
    assert len({e["id"] for e in graph["edges"]}) == len(graph["edges"])
    expected_targets = {
        "project": {"repository", "guide"},
        "repository": {"project", "guide", "branch"},
        "branch": {"repository", "commit", "handoff"},
        "commit": {"repository", "branch", "finding"},
        "merge": {"repository", "branch", "commit"},
        "push": {"repository", "merge"},
        "finding": {"repository", "commit", "insight"},
        "insight": {"repository", "finding", "decision"},
        "decision": {"repository", "finding", "insight"},
        "handoff": {"repository", "commit", "guide", "branch"},
        "guide": {"repository", "project", "finding"},
    }
    assert {(edge["source"], edge["target"]) for edge in graph["edges"]} == {
        (f"{source}-note-demo", f"{target}-note-demo")
        for source, targets in expected_targets.items() for target in targets
    }
    assert {"source": "project-note-demo", "target": "repository-note-demo"} in [
        {"source": e["source"], "target": e["target"]} for e in graph["edges"]
    ]
    recreated, _, _ = make_service(objects=objects, catalog=catalog)
    assert await recreated.graph() == graph
    assert objects.reads, "Reads must rehydrate from immutable Markdown objects"
    assert (await recreated.read_note("finding-note-demo"))["markdown"] == documents[NOTE_PATHS["finding"]]


# Reject broken proposed graphs without publishing the individually valid subset.
@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["broken_link", "wrong_project", "duplicate_id", "unsafe_path", "invalid_yaml", "partial_graph"])
async def test_invalid_batch_never_partially_publishes(make_service, changes, damage):
    service, _, catalog = make_service()
    proposed = copy.deepcopy(changes)
    if damage == "broken_link":
        proposed[-1]["markdown"] += "\n[[Missing/Unknown Note]]\n"
    elif damage == "wrong_project":
        proposed[-1]["markdown"] = proposed[-1]["markdown"].replace('project_id: "checkout-demo"', 'project_id: "other-project"')
    elif damage == "duplicate_id":
        proposed[-1]["markdown"] = proposed[-1]["markdown"].replace('id: "guide-note-demo"', 'id: "finding-note-demo"')
    elif damage == "unsafe_path":
        proposed[-1]["path"] = "../Escaped Note.md"
    elif damage == "invalid_yaml":
        proposed[-1]["markdown"] = proposed[-1]["markdown"].replace("spec_version: 1", "spec_version: 1\nspec_version: 1")
    else:
        proposed = proposed[:1]
    result = await service.apply_changes(proposed)
    assert result["status"] == "invalid", result
    assert result["notes"] == []
    assert result["issues"]
    assert catalog.list_notes("checkout-demo") == []
    assert (await service.graph())["nodes"] == []


# Preserve current content when an update breaks another note's heading link.
@pytest.mark.asyncio
async def test_validation_includes_previously_published_graph(make_service, changes, documents):
    service, _, catalog = make_service()
    assert (await service.apply_changes(changes))["status"] == "updated"
    update = updated_change(documents)
    update["markdown"] += "\n[[Guides/Run Checkout Checks#Missing heading]]\n"
    result = await service.apply_changes([update])
    assert result["status"] == "invalid"
    assert (await service.read_note("finding-note-demo"))["revision"] == 1
    assert len(catalog.history) == 11


# Verify directional links before returning the target and reject unlinked notes.
@pytest.mark.asyncio
async def test_follow_link_checks_real_directed_graph_edge(make_service, changes):
    service, _, _ = make_service()
    await service.apply_changes(changes)
    target = await service.follow_link("project-note-demo", "repository-note-demo")
    assert target["id"] == "repository-note-demo"
    with pytest.raises(KeyError):
        await service.follow_link("project-note-demo", "push-note-demo")
    with pytest.raises(KeyError):
        await service.read_note("missing-note")


# Keep archived history readable and linked while excluding it from current search.
@pytest.mark.asyncio
async def test_archive_retains_identity_path_objects_and_graph(make_service, changes, documents):
    service, objects, catalog = make_service()
    await service.apply_changes(changes)
    before = await service.graph()
    result = await service.apply_changes([{
        "action": "archive", "path": NOTE_PATHS["finding"], "expected_revision": 1,
    }])
    assert result["status"] == "updated"
    assert result["notes"] == [{"path": NOTE_PATHS["finding"], "action": "archived"}]
    note = await service.read_note("finding-note-demo")
    assert note["id"] == "finding-note-demo"
    assert note["path"] == NOTE_PATHS["finding"]
    assert note["revision"] == 2
    assert "status: archived" in note["markdown"]
    assert documents[NOTE_PATHS["finding"]].encode() in objects.objects.values()
    after = await service.graph()
    assert after["edges"] == before["edges"]
    assert len(after["nodes"]) == 11
    assert "finding-note-demo" not in {n["id"] for n in await service.search_notes("Expired Code Accepted")}
    assert len(catalog.history) == 12


# Return explicit conflict for both stale writers and create collisions.
@pytest.mark.asyncio
async def test_stale_concurrent_writers_cannot_overwrite_each_other(make_service, changes, documents):
    service, objects, catalog = make_service()
    other, _, _ = make_service(objects=objects, catalog=catalog)
    await service.apply_changes(changes)
    results = await asyncio.gather(
        service.apply_changes([updated_change(documents, suffix="Writer A observed this.")]),
        other.apply_changes([updated_change(documents, suffix="Writer B observed this.")]),
    )
    assert sorted(r["status"] for r in results) == ["conflict", "updated"]
    stored = await service.read_note("finding-note-demo")
    assert stored["revision"] == 2
    assert ("Writer A observed this." in stored["markdown"]) != ("Writer B observed this." in stored["markdown"])
    assert len(catalog.history) == 12
    result = await service.apply_changes(changes)
    assert result["status"] == "conflict"
    assert result["notes"] == []


# Keep stable IDs and paths when callers try to repurpose an existing note.
@pytest.mark.asyncio
async def test_update_cannot_replace_stable_identity(make_service, changes, documents):
    service, _, _ = make_service()
    await service.apply_changes(changes)
    update = updated_change(documents)
    update["markdown"] = update["markdown"].replace('id: "finding-note-demo"', 'id: "replacement-id"')
    result = await service.apply_changes([update])
    assert result["status"] in {"invalid", "conflict"}
    assert (await service.read_note("finding-note-demo"))["revision"] == 1
    with pytest.raises(KeyError):
        await service.read_note("replacement-id")


# Save actual publication outcome atomically so retries after restart cannot duplicate writes.
@pytest.mark.asyncio
async def test_request_receipt_replays_actual_outcome_and_rejects_changed_hash(make_service, changes):
    service, objects, catalog = make_service()
    result = await service.apply_changes(changes, request_id="request-1", request_hash="payload-1")
    assert result["status"] == "updated"
    reloaded, _, _ = make_service(objects=objects, catalog=catalog)
    assert await reloaded.get_request_result("request-1", "payload-1") == result
    assert await reloaded.apply_changes(changes, request_id="request-1", request_hash="payload-1") == result
    assert len(catalog.history) == 11
    with pytest.raises(ValueError):
        await reloaded.get_request_result("request-1", "changed-payload")
    with pytest.raises(ValueError):
        await reloaded.apply_changes(changes, request_id="request-1", request_hash="changed-payload")
    assert await reloaded.get_request_result("unknown", "payload") is None


# Keep explicit replay receipts scoped to one project and detect conflicting reuse.
@pytest.mark.asyncio
async def test_explicit_receipts_are_durable_and_project_scoped(make_service):
    service, objects, catalog = make_service()
    result = {"status": "unchanged", "message": "Reviewed, no change needed.", "notes": []}
    await service.remember_request_result("same-id", "same-hash", result)
    reloaded, _, _ = make_service(objects=objects, catalog=catalog)
    other, _, _ = make_service("other-project", objects=objects, catalog=catalog)
    assert await reloaded.get_request_result("same-id", "same-hash") == result
    assert await other.get_request_result("same-id", "same-hash") is None
    with pytest.raises(ValueError):
        await reloaded.remember_request_result("same-id", "changed", result)


# Upload failures and manifest failures leave no partial notes or success receipt.
@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["object", "catalog"])
async def test_dependency_failure_never_publishes_partial_batch_or_receipt(make_service, changes, failure):
    service, objects, catalog = make_service()
    if failure == "object":
        objects.fail_put_at = 3
    else:
        catalog.fail_commit = True
    with pytest.raises(OSError):
        await service.apply_changes(changes, request_id="recoverable", request_hash="payload")
    assert catalog.list_notes("checkout-demo") == []
    assert await service.get_request_result("recoverable", "payload") is None
    objects.fail_put_at = None
    catalog.fail_commit = False
    assert (await service.apply_changes(changes, request_id="recoverable", request_hash="payload"))["status"] == "updated"


# Scope read, search, graph, publication, and object prefixes to the configured project.
@pytest.mark.asyncio
async def test_shared_backing_adapters_keep_projects_isolated(make_service, changes):
    first, objects, catalog = make_service()
    second, _, _ = make_service("other-project", objects=objects, catalog=catalog)
    await first.apply_changes(changes)
    assert (await second.graph()) == {"project_id": "other-project", "nodes": [], "edges": []}
    assert await second.search_notes("discount") == []
    with pytest.raises(KeyError):
        await second.read_note("finding-note-demo")
    other_changes = copy.deepcopy(changes)
    for change in other_changes:
        change["markdown"] = change["markdown"].replace('project_id: "checkout-demo"', 'project_id: "other-project"')
    assert (await second.apply_changes(other_changes))["status"] == "updated"
    assert len(objects.objects) == 22
    first_keys = {note["object_key"].rsplit("/", 1)[0] for note in catalog.list_notes("checkout-demo")}
    second_keys = {note["object_key"].rsplit("/", 1)[0] for note in catalog.list_notes("other-project")}
    assert first_keys.isdisjoint(second_keys), "Object namespaces must be project-scoped"


# Return useful bounded lexical results without any embedding credentials.
@pytest.mark.asyncio
async def test_lexical_search_and_closed_spec_lookup(make_service, changes):
    service, _, _ = make_service()
    await service.apply_changes(changes)
    results = await service.search_notes("discount", limit=3)
    assert 0 < len(results) <= 3
    assert all({"id", "title", "path", "excerpt"} <= set(note) for note in results)
    assert len({note["id"] for note in results}) == len(results)
    assert any("discount" in note["excerpt"].lower() or "discount" in note["title"].lower() for note in results)
    for kind in NOTE_PATHS:
        spec = await service.get_note_spec(kind)
        assert "Required frontmatter" in spec
        assert f"type: {kind}" in spec
    with pytest.raises(ValueError):
        await service.get_note_spec("../../etc/passwd")


# Treat delimiter text inside a valid scalar as content rather than a YAML boundary.
@pytest.mark.asyncio
async def test_frontmatter_scalar_can_contain_three_hyphens(make_service, changes):
    service, _, _ = make_service()
    proposed = copy.deepcopy(changes)
    note = next(change for change in proposed if change["path"] == NOTE_PATHS["finding"])
    note["markdown"] = note["markdown"].replace("title: Expired Code Accepted", "title: Expired --- Code Accepted")
    note["markdown"] = note["markdown"].replace("# Expired Code Accepted", "# Expired --- Code Accepted")
    result = await service.apply_changes(proposed)
    assert result["status"] == "updated", result
    loaded = await service.read_note("finding-note-demo")
    assert loaded["title"] == "Expired --- Code Accepted"
    assert loaded["markdown"] == note["markdown"]


# Diagnose malformed action shapes without raising an unhashable-type exception.
@pytest.mark.asyncio
@pytest.mark.parametrize("action", [[], {"action": "create"}])
async def test_malformed_action_values_return_invalid_issues(make_service, changes, action):
    service, _, catalog = make_service()
    proposed = copy.deepcopy(changes[:1])
    proposed[0]["action"] = action
    result = await service.apply_changes(proposed)
    assert result["status"] == "invalid"
    assert result["issues"]
    assert result["notes"] == []
    assert catalog.list_notes("checkout-demo") == []


# Ignore wikilink-shaped text in metadata fields that the native format does not treat as links.
@pytest.mark.asyncio
async def test_graph_ignores_wikilink_shaped_alias_scalar(make_service, changes):
    service, _, _ = make_service()
    proposed = copy.deepcopy(changes)
    project = next(change for change in proposed if change["path"] == NOTE_PATHS["project"])
    project["markdown"] = project["markdown"].replace("status: active", 'status: active\naliases: ["[[Pushes/Publish Discount Validation]]"]')
    assert (await service.apply_changes(proposed))["status"] == "updated"
    graph = await service.graph()
    assert not any(edge["source"] == "project-note-demo" and edge["target"] == "push-note-demo" for edge in graph["edges"])
    with pytest.raises(KeyError):
        await service.follow_link("project-note-demo", "push-note-demo")


# Archive all structurally valid YAML spellings rather than only bare one-line keys.
@pytest.mark.asyncio
@pytest.mark.parametrize("status_line", ['"status": active', "status: >-\n  active"])
async def test_archive_handles_quoted_keys_and_block_scalar_status(make_service, changes, status_line):
    import yaml
    service, _, _ = make_service()
    proposed = copy.deepcopy(changes)
    finding = next(change for change in proposed if change["path"] == NOTE_PATHS["finding"])
    finding["markdown"] = finding["markdown"].replace("status: active", status_line)
    assert (await service.apply_changes(proposed))["status"] == "updated"
    result = await service.apply_changes([{"action": "archive", "path": NOTE_PATHS["finding"], "expected_revision": 1}])
    assert result["status"] == "updated", result
    loaded = await service.read_note("finding-note-demo")
    assert yaml.safe_load(loaded["markdown"].split("\n---\n", 1)[0][4:])["status"] == "archived"
    assert "finding-note-demo" not in {result["id"] for result in await service.search_notes("Expired Code Accepted")}


# Collapse racing identical requests into one publication with one durable shared outcome.
@pytest.mark.asyncio
async def test_concurrent_identical_request_retries_publish_once(make_service, changes):
    first, objects, catalog = make_service()
    second, _, _ = make_service(objects=objects, catalog=catalog)
    outcomes = await asyncio.gather(*[
        service.apply_changes(changes, request_id="racing-request", request_hash="identical-payload")
        for service in (first, second)
    ])
    assert outcomes[0] == outcomes[1]
    assert outcomes[0]["status"] == "updated"
    assert len(objects.objects) == 11
    assert len(catalog.history) == 11
    assert await first.get_request_result("racing-request", "identical-payload") == outcomes[0]


# Exclude links in fenced code, inline code, and comments from actual graph traversal.
@pytest.mark.asyncio
async def test_graph_ignores_links_in_code_and_comments(make_service, changes):
    service, _, _ = make_service()
    proposed = copy.deepcopy(changes)
    project = next(change for change in proposed if change["path"] == NOTE_PATHS["project"])
    project["markdown"] += (
        '\n```markdown\n[[Pushes/Publish Discount Validation]]\n```\n'
        '`[[Commits/Reject Expired Discounts]]`\n'
        '<!-- [[Findings/Expired Code Accepted]] -->\n'
    )
    assert (await service.apply_changes(proposed))["status"] == "updated"
    loaded = await service.read_note("project-note-demo")
    assert {link["target"] for link in loaded["links"]} == {"repository-note-demo", "guide-note-demo"}


# Avoid extra history and retain the terminal receipt when published bytes already match.
@pytest.mark.asyncio
async def test_identical_content_update_is_unchanged_without_new_objects(make_service, changes, documents):
    service, objects, catalog = make_service()
    await service.apply_changes(changes)
    result = await service.apply_changes([{
        "action": "update", "path": NOTE_PATHS["finding"], "expected_revision": 1,
        "markdown": documents[NOTE_PATHS["finding"]],
    }], request_id="already-matches", request_hash="same-content")
    assert result["status"] == "unchanged"
    assert result["notes"] == []
    assert len(objects.objects) == 11
    assert len(catalog.history) == 11
    assert await service.get_request_result("already-matches", "same-content") == result


# Report path ancestor collisions as invalid proposals instead of leaking filesystem errors.
@pytest.mark.asyncio
async def test_note_file_cannot_be_ancestor_directory_of_another_note(make_service, changes):
    service, objects, catalog = make_service()
    proposed = copy.deepcopy(changes)
    nested_path = "Projects/Checkout Platform.md/Run Checkout Checks.md"
    for change in proposed:
        change["markdown"] = change["markdown"].replace("[[Guides/Run Checkout Checks", "[[Projects/Checkout Platform.md/Run Checkout Checks")
        if change["path"] == NOTE_PATHS["guide"]:
            change["path"] = nested_path
    result = await service.apply_changes(proposed)
    assert result["status"] == "invalid", result
    assert result["issues"]
    assert result["notes"] == []
    assert catalog.list_notes("checkout-demo") == []
    assert objects.objects == {}


# Reject reused replay IDs with changed hashes even when the proposed changes are malformed.
@pytest.mark.asyncio
async def test_reused_receipt_hash_conflict_precedes_invalid_changes(make_service, changes):
    service, _, _ = make_service()
    assert (await service.apply_changes(changes, request_id="existing-request", request_hash="original"))["status"] == "updated"
    with pytest.raises(ValueError):
        await service.apply_changes([{"action": [], "path": "A.md"}], request_id="existing-request", request_hash="different")
