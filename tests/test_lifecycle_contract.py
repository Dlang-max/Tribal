"""Explicit lifecycle transitions preserve history and refresh current links."""
from __future__ import annotations

import uuid

import pytest

from acceptance_helpers import diagnostic_codes, execute

pytestmark = pytest.mark.mysql


def head_generations(db, kb):
    from tribal.storage import get_knowledge_base
    row = get_knowledge_base(db, knowledge_base=kb["key"])["knowledge_base"]
    return row["knowledge_generation"], row["indexing_generation"]


def test_delete_restore_are_explicit_atomic_and_preserve_revision_and_vectors(mysql_db, active_kb, make_note):
    from tribal.publication import ingest_vault, set_document_deleted
    from tribal.embeddings import DeterministicProvider, run_worker_once
    from tribal.errors import TribalError
    from tribal.retrieval import search
    target = make_note("needle target\n")
    initial = ingest_vault(mysql_db, {"Target.md": target, "Source.md": make_note("[[Target]] needle source\n")}, knowledge_base=active_kb["key"])["documents"]
    for _ in range(2):
        assert run_worker_once(mysql_db, DeterministicProvider(), knowledge_base=active_kb["key"])["state"] == "succeeded"
    head = initial["Target.md"]
    target_id = uuid.UUID(head["document_id"]).bytes
    source_revision = uuid.UUID(initial["Source.md"]["revision_id"]).bytes
    vectors = execute(mysql_db, "SELECT chunk_id,CAST(embedding AS BINARY) AS vector FROM chunk_embeddings WHERE chunk_id=%s", (head["chunk_ids"][0],))
    before = head_generations(mysql_db, active_kb)
    deleted = set_document_deleted(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], expected_revision=head["revision_id"])
    assert deleted["ok"] is True and deleted["deleted"] is True and deleted["changed"] is True
    assert deleted["revision_id"] == head["revision_id"]
    assert head_generations(mysql_db, active_kb) == (before[0] + 1, before[1])
    assert execute(mysql_db, "SELECT target_document_id FROM document_links WHERE source_revision_id=%s", (source_revision,))[0]["target_document_id"] is None
    assert [hit["path"] for hit in search(mysql_db, "needle", knowledge_base=active_kb["key"], mode="lexical", lexical_mode="literal")["hits"]] == ["Source.md"]
    after_delete = head_generations(mysql_db, active_kb)
    noop = set_document_deleted(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], expected_revision=head["revision_id"])
    assert noop["deleted"] is True and noop["changed"] is False
    assert head_generations(mysql_db, active_kb) == after_delete
    with pytest.raises(TribalError) as failure:
        set_document_deleted(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], expected_revision=str(uuid.uuid4()))
    assert failure.value.code == "E_REVISION_CONFLICT"
    # An unchanged ordinary import may report a no-op or E_DELETED; either way
    # it cannot restore the lifecycle or advance generations.
    try:
        result = ingest_vault(mysql_db, {"Target.md": target}, knowledge_base=active_kb["key"])
    except TribalError as error:
        assert error.code == "E_DELETED"
    else:
        assert result["ok"] is True or "E_DELETED" in diagnostic_codes(result)
    assert execute(mysql_db, "SELECT deleted_at FROM documents WHERE id=%s", (target_id,))[0]["deleted_at"] is not None
    assert head_generations(mysql_db, active_kb) == after_delete
    restored = set_document_deleted(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], expected_revision=head["revision_id"], deleted=False)
    assert restored["deleted"] is False and restored["changed"] is True
    assert head_generations(mysql_db, active_kb) == (before[0] + 2, before[1])
    assert execute(mysql_db, "SELECT target_document_id FROM document_links WHERE source_revision_id=%s", (source_revision,))[0]["target_document_id"] == target_id
    assert execute(mysql_db, "SELECT COUNT(*) AS n FROM document_revisions WHERE document_id=%s", (target_id,))[0]["n"] == 1
    assert execute(mysql_db, "SELECT chunk_id,CAST(embedding AS BINARY) AS vector FROM chunk_embeddings WHERE chunk_id=%s", (head["chunk_ids"][0],)) == vectors


def test_lifecycle_transition_invalidates_search_continuation(mysql_db, active_kb, make_note):
    from tribal.errors import TribalError
    from tribal.publication import ingest_vault, set_document_deleted
    from tribal.retrieval import search
    docs = {f"{i}.md": make_note("needle\n") for i in range(3)}
    outcomes = ingest_vault(mysql_db, docs, knowledge_base=active_kb["key"])["documents"]
    page = search(mysql_db, "needle", knowledge_base=active_kb["key"], mode="lexical", lexical_mode="literal", limit=1)
    head = outcomes["0.md"]
    set_document_deleted(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], expected_revision=head["revision_id"])
    with pytest.raises(TribalError) as failure:
        search(mysql_db, "needle", knowledge_base=active_kb["key"], mode="lexical", lexical_mode="literal", cursor=page["next_cursor"])
    assert failure.value.code == "E_CURSOR_EXPIRED"
