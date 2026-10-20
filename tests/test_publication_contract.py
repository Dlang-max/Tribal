"""Atomic revision and namespace acceptance on a real MySQL database."""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from acceptance_helpers import based, diagnostic_codes, execute

pytestmark = pytest.mark.mysql


def ingest(db, kb, documents):
    from tribal.publication import ingest_vault
    return ingest_vault(db, documents, knowledge_base=kb["key"])


def generation(db, kb):
    from tribal.storage import get_knowledge_base
    row = get_knowledge_base(db, knowledge_base=kb["key"])["knowledge_base"]
    return row["knowledge_generation"], row["indexing_generation"]


def test_ingest_publishes_chunks_jobs_and_one_generation_per_batch(mysql_db, active_kb, make_note):
    before = generation(mysql_db, active_kb)
    result = ingest(mysql_db, active_kb, {"one.md": make_note(), "two.md": make_note("## Method\n\nObserve.\n")})
    assert result["ok"] is True
    assert result["summary"]["created"] == 2
    assert result["summary"]["updated"] == result["summary"]["unchanged"] == 0
    assert result["summary"]["chunks"] == result["summary"]["jobs"] == 2
    assert generation(mysql_db, active_kb) == (before[0] + 1, before[1] + 1)
    for path, outcome in result["documents"].items():
        assert outcome["path"] == path
        assert outcome["action"] == "created"
        assert outcome["previous_revision_id"] is None
        assert outcome["chunk_ids"]
        revision = uuid.UUID(outcome["revision_id"]).bytes
        assert execute(mysql_db, "SELECT COUNT(*) AS n FROM document_chunks WHERE revision_id=%s", (revision,))[0]["n"] == 1
        assert execute(mysql_db, "SELECT COUNT(*) AS n FROM embedding_jobs WHERE revision_id=%s", (revision,))[0]["n"] == 1


def test_new_foreign_base_is_ignored_and_unchanged_stale_base_is_noop(mysql_db, active_kb, make_note):
    foreign = str(uuid.uuid4())
    content = make_note()
    initial = ingest(mysql_db, active_kb, {"one.md": based(content, foreign)})
    assert initial["ok"] is True
    head = initial["documents"]["one.md"]
    before = generation(mysql_db, active_kb)
    for submitted in (content, based(content, foreign), based(content, head["revision_id"])):
        result = ingest(mysql_db, active_kb, {"one.md": submitted})
        assert result["ok"] is True
        assert result["summary"] == dict(created=0, updated=0, unchanged=1, chunks=0, jobs=0)
        assert result["documents"]["one.md"]["revision_id"] == head["revision_id"]
        assert result["documents"]["one.md"]["chunk_ids"] == head["chunk_ids"]
        assert generation(mysql_db, active_kb) == before


def test_unchanged_ingest_does_not_repair_missing_jobs(mysql_db, active_kb, make_note):
    content = make_note()
    first = ingest(mysql_db, active_kb, {"one.md": content})["documents"]["one.md"]
    execute(mysql_db, "DELETE FROM embedding_jobs WHERE revision_id=%s", (uuid.UUID(first["revision_id"]).bytes,))
    before = generation(mysql_db, active_kb)
    result = ingest(mysql_db, active_kb, {"one.md": content})
    assert result["summary"]["jobs"] == 0
    assert execute(mysql_db, "SELECT COUNT(*) AS n FROM embedding_jobs WHERE revision_id=%s", (uuid.UUID(first["revision_id"]).bytes,))[0]["n"] == 0
    assert generation(mysql_db, active_kb) == before


@pytest.mark.parametrize("base, code", [(None, "E_BASE_REVISION_REQUIRED"), ("foreign", "E_REVISION_CONFLICT")])
def test_changed_existing_note_requires_current_base(mysql_db, active_kb, make_note, base, code):
    from tribal.errors import TribalError
    content = make_note()
    head = ingest(mysql_db, active_kb, {"one.md": content})["documents"]["one.md"]
    changed = content.replace("A useful observation.", "A changed observation.")
    if base:
        changed = based(changed, str(uuid.uuid4()))
    before = generation(mysql_db, active_kb)
    with pytest.raises(TribalError) as failure:
        ingest(mysql_db, active_kb, {"one.md": changed})
    assert failure.value.code == code
    assert generation(mysql_db, active_kb) == before
    row = execute(mysql_db, "SELECT current_revision_id FROM documents WHERE id=%s", (uuid.UUID(head["document_id"]).bytes,))[0]
    assert bytes(row["current_revision_id"]) == uuid.UUID(head["revision_id"]).bytes


def test_edit_preserves_historical_revision_chunks_and_evidence(mysql_db, active_kb, make_note):
    from tribal.retrieval import read_document
    content = make_note("## Method\n\nOld observation.\n", contexts=[dict(key="trial", type="experiment", locator="trial-12")],
                        sources=[dict(type="experiment", locator="notebook", context="trial", revision="edition-1")])
    first = ingest(mysql_db, active_kb, {"one.md": content})["documents"]["one.md"]
    changed = based(content.replace("Old observation", "New observation"), first["revision_id"])
    second = ingest(mysql_db, active_kb, {"one.md": changed})["documents"]["one.md"]
    assert second["previous_revision_id"] == first["revision_id"]
    assert second["revision_id"] != first["revision_id"]
    assert not set(second["chunk_ids"]).intersection(first["chunk_ids"])
    old = read_document(mysql_db, knowledge_base=active_kb["key"], document_id=first["document_id"], revision_id=first["revision_id"])
    assert old["content"] == content
    assert old["metadata"]["contexts"][0]["type"] == "experiment"
    for revision in (first["revision_id"], second["revision_id"]):
        assert execute(mysql_db, "SELECT COUNT(*) AS n FROM document_sources WHERE revision_id=%s", (uuid.UUID(revision).bytes,))[0]["n"] == 1
    assert execute(mysql_db, "SELECT COUNT(*) AS n FROM document_chunks WHERE revision_id=%s", (uuid.UUID(first["revision_id"]).bytes,))[0]["n"] == len(first["chunk_ids"])


def test_invalid_batch_rolls_back_valid_companion(mysql_db, active_kb, make_note):
    good = make_note()
    bad = make_note(kind="invalid")
    before = generation(mysql_db, active_kb)
    result = ingest(mysql_db, active_kb, {"good.md": good, "bad.md": bad})
    assert result["ok"] is False
    assert "E_FIELD_TYPE" in diagnostic_codes(result)
    assert generation(mysql_db, active_kb) == before
    assert execute(mysql_db, "SELECT COUNT(*) AS n FROM documents WHERE knowledge_base_id=%s", (uuid.UUID(active_kb["id"]).bytes,))[0]["n"] == 0


def test_database_failure_rolls_back_heads_revisions_links_chunks_and_jobs(mysql_db, active_kb, make_note):
    from tribal.errors import TribalError
    trigger = "test_fail_link_" + uuid.uuid4().hex
    execute(mysql_db, f"CREATE TRIGGER {trigger} BEFORE INSERT ON document_links FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='forced acceptance rollback'")
    before = generation(mysql_db, active_kb)
    try:
        with pytest.raises(TribalError) as failure:
            ingest(mysql_db, active_kb, {"one.md": make_note("[[Missing]]\n")})
        assert failure.value.code == "E_DATABASE"
        assert generation(mysql_db, active_kb) == before
        for table in ("documents", "document_revisions", "embedding_jobs"):
            assert execute(mysql_db, f"SELECT COUNT(*) AS n FROM {table} WHERE knowledge_base_id=%s", (uuid.UUID(active_kb["id"]).bytes,))[0]["n"] == 0
    finally:
        execute(mysql_db, f"DROP TRIGGER {trigger}")


@pytest.mark.parametrize("first_path, second_path", [("One.md", "one.md"), ("Å.md", "A\u030a.md"), ("Straße.md", "STRASSE.md")])
def test_unaffected_namespace_reservations_use_portable_unicode(mysql_db, active_kb, make_note, first_path, second_path):
    from tribal.errors import TribalError
    ingest(mysql_db, active_kb, {first_path: make_note()})
    before = generation(mysql_db, active_kb)
    try:
        result = ingest(mysql_db, active_kb, {second_path: make_note()})
    except TribalError as error:
        assert error.code == "E_PATH"
    else:
        assert result["ok"] is False and "E_PATH" in diagnostic_codes(result)
    assert generation(mysql_db, active_kb) == before


def test_missing_files_do_not_delete_and_deleted_paths_remain_reserved(mysql_db, active_kb, make_note):
    from tribal.errors import TribalError
    content = make_note()
    first = ingest(mysql_db, active_kb, {"reserved.md": content})["documents"]["reserved.md"]
    ingest(mysql_db, active_kb, {"unrelated.md": make_note()})
    identity = uuid.UUID(first["document_id"]).bytes
    assert execute(mysql_db, "SELECT deleted_at FROM documents WHERE id=%s", (identity,))[0]["deleted_at"] is None
    execute(mysql_db, "UPDATE documents SET deleted_at=CURRENT_TIMESTAMP(6) WHERE id=%s", (identity,))
    with pytest.raises(TribalError) as failure:
        ingest(mysql_db, active_kb, {"reserved.md": based(content.replace("useful", "changed"), first["revision_id"])})
    assert failure.value.code == "E_DELETED"
    try:
        result = ingest(mysql_db, active_kb, {"reserved.md": make_note()})
    except TribalError as error:
        assert error.code == "E_PATH"
    else:
        assert result["ok"] is False and "E_PATH" in diagnostic_codes(result)


def test_path_only_revision_and_occupied_swap_preserve_canonical_content(mysql_db, active_kb, make_note):
    from tribal.retrieval import read_document
    first_content, second_content = make_note("first\n"), make_note("second\n")
    first = ingest(mysql_db, active_kb, {"a.md": first_content, "b.md": second_content})["documents"]
    result = ingest(mysql_db, active_kb, {"b.md": based(first_content, first["a.md"]["revision_id"]),
                                       "a.md": based(second_content, first["b.md"]["revision_id"])})
    assert result["summary"]["updated"] == 2
    assert result["documents"]["b.md"]["document_id"] == first["a.md"]["document_id"]
    assert result["documents"]["a.md"]["document_id"] == first["b.md"]["document_id"]
    for path, content in (("b.md", first_content), ("a.md", second_content)):
        outcome = result["documents"][path]
        assert outcome["action"] == "updated"
        read = read_document(mysql_db, knowledge_base=active_kb["key"], document_id=outcome["document_id"])
        assert read["content"] == content
        assert read["path"] == path
    for table in ("documents", "document_revisions"):
        assert execute(mysql_db, f"SELECT COUNT(*) AS n FROM {table} WHERE vault_path LIKE '.tribal-staging/%'")[0]["n"] == 0


def test_new_duplicate_refreshes_links_from_unchanged_sources(mysql_db, active_kb, make_note):
    target = make_note("## Connection\n\nSetup.\n")
    source = make_note("[[Setup]]\n")
    initial = ingest(mysql_db, active_kb, {"database/Setup.md": target, "Startup.md": source})["documents"]
    source_revision = uuid.UUID(initial["Startup.md"]["revision_id"]).bytes
    assert execute(mysql_db, "SELECT target_document_id FROM document_links WHERE source_revision_id=%s", (source_revision,))[0]["target_document_id"] == uuid.UUID(initial["database/Setup.md"]["document_id"]).bytes
    ingest(mysql_db, active_kb, {"another/Setup.md": make_note("Other setup.\n")})
    assert execute(mysql_db, "SELECT target_document_id FROM document_links WHERE source_revision_id=%s", (source_revision,))[0]["target_document_id"] is None
    assert execute(mysql_db, "SELECT current_revision_id FROM documents WHERE id=%s", (uuid.UUID(initial["Startup.md"]["document_id"]).bytes,))[0]["current_revision_id"] == source_revision


def test_concurrent_edits_with_same_base_have_one_winner(mysql_db, active_kb, make_note):
    from tribal.errors import TribalError
    content = make_note()
    first = ingest(mysql_db, active_kb, {"one.md": content})["documents"]["one.md"]
    barrier = threading.Barrier(2)
    def edit(text):
        barrier.wait(timeout=5)
        try:
            return ingest(mysql_db, active_kb, {"one.md": based(content.replace("useful", text), first["revision_id"])})
        except TribalError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(edit, text) for text in ("left", "right")]
        results = [future.result(timeout=20) for future in futures]
    assert sum(isinstance(result, dict) and result["ok"] for result in results) == 1
    assert results.count("E_REVISION_CONFLICT") == 1
    assert execute(mysql_db, "SELECT COUNT(*) AS n FROM document_revisions WHERE document_id=%s", (uuid.UUID(first["document_id"]).bytes,))[0]["n"] == 2


def test_concurrent_portable_collision_serializes_namespace(mysql_db, active_kb, make_note):
    from tribal.errors import TribalError
    barrier = threading.Barrier(2)
    def create(path):
        barrier.wait(timeout=5)
        try:
            return ingest(mysql_db, active_kb, {path: make_note()})
        except TribalError as error:
            return error.as_dict()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result(timeout=20) for future in [executor.submit(create, path) for path in ("One.md", "one.md")]]
    assert sum(result["ok"] for result in results) == 1
    loser = next(result for result in results if not result["ok"])
    assert "E_PATH" in diagnostic_codes(loser)
    assert execute(mysql_db, "SELECT COUNT(*) AS n FROM documents WHERE knowledge_base_id=%s", (uuid.UUID(active_kb["id"]).bytes,))[0]["n"] == 1


def test_rechunk_allocates_fresh_ids_without_authored_revision(mysql_db, active_kb, make_note):
    from tribal.errors import TribalError
    from tribal.publication import rechunk_revision
    first = ingest(mysql_db, active_kb, {"one.md": make_note("## First\n\ntext\n\n## Second\n\nmore\n")})["documents"]["one.md"]
    before = generation(mysql_db, active_kb)
    result = rechunk_revision(mysql_db, knowledge_base=active_kb["key"], document_id=first["document_id"], expected_chunk_ids=first["chunk_ids"])
    assert result["old_chunk_ids"] == first["chunk_ids"]
    assert not set(result["chunk_ids"]).intersection(first["chunk_ids"])
    assert result["revision_id"] == first["revision_id"]
    assert generation(mysql_db, active_kb) == (before[0], before[1] + 1)
    assert execute(mysql_db, "SELECT COUNT(*) AS n FROM document_revisions WHERE document_id=%s", (uuid.UUID(first["document_id"]).bytes,))[0]["n"] == 1
    with pytest.raises(TribalError) as failure:
        rechunk_revision(mysql_db, knowledge_base=active_kb["key"], document_id=first["document_id"], expected_chunk_ids=first["chunk_ids"])
    assert failure.value.code == "E_CONFLICT"
