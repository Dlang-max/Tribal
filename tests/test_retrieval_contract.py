"""Exact ranking, stable sessions and revision-pinned source retrieval."""
from __future__ import annotations

import json
import math
import struct
import uuid

import pytest

from acceptance_helpers import based, execute

pytestmark = pytest.mark.mysql


class QueryProvider:
    def __init__(self, vector=(1.0, 0.0, 0.0)):
        self.vector = list(vector)
        self.calls = []

    def embed(self, text, *, model, dimensions):
        self.calls.append(text)
        assert dimensions == len(self.vector)
        return self.vector


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def normalized(values):
    norm = math.hypot(*values)
    return [f32(value / norm) for value in values]


def cosine(left, right):
    return math.fsum(a * b for a, b in zip(left, right)) / (math.hypot(*left) * math.hypot(*right))


def publish(db, kb, documents, vectors=None):
    from tribal.publication import ingest_vault
    from tribal.embeddings import format_document_input, input_hash
    result = ingest_vault(db, documents, knowledge_base=kb["key"])
    assert result["ok"] is True, result["diagnostics"]
    if vectors:
        for path, values in vectors.items():
            for chunk_id in result["documents"][path]["chunk_ids"]:
                row = execute(db, "SELECT c.content,c.heading_path,r.title FROM document_chunks c JOIN document_revisions r ON r.id=c.revision_id WHERE c.id=%s", (chunk_id,))[0]
                headings = json.loads(row["heading_path"]) if isinstance(row["heading_path"], str) else row["heading_path"]
                digest = input_hash(format_document_input(row["title"], headings, row["content"]))
                execute(db, "INSERT INTO chunk_embeddings(chunk_id,profile_id,dimensions,embedding,input_hash) VALUES (%s,%s,%s,STRING_TO_VECTOR(%s),%s)",
                        (chunk_id, uuid.UUID(kb["profile"]["id"]).bytes, 3, json.dumps(normalized(values)), bytes.fromhex(digest)))
    return result


def search(db, kb, query, **kwargs):
    from tribal.retrieval import search as operation
    return operation(db, query, knowledge_base=kb["key"], **kwargs)


def test_semantic_exact_scores_use_persisted_float32_and_float64_norms(mysql_db, active_kb, make_note):
    vectors = {"lower.md": [0.1, 0.8, -0.3], "higher.md": [0.123456789, 0.7777777, -0.4], "opposite.md": [-1, 0, 0]}
    docs = {path: make_note(path + "\n") for path in vectors}
    result = publish(mysql_db, active_kb, docs, vectors)
    query = [0.1, 0.9, -0.2]
    expected = sorted([(path, cosine(normalized(query), normalized(vector))) for path, vector in vectors.items()], key=lambda item: -item[1])
    provider = QueryProvider(query)
    response = search(mysql_db, active_kb, "  original query\n", provider=provider)
    assert provider.calls == ["  original query\n"]
    assert [hit["path"] for hit in response["hits"]] == [item[0] for item in expected]
    for hit, (_, score) in zip(response["hits"], expected):
        assert hit["score"] == pytest.approx(score, abs=1e-14)
        assert hit["semantic_score"] == hit["score"]
        assert hit["lexical_score"] is None
        assert hit["revision_id"] == result["documents"][hit["path"]]["revision_id"]
    assert response["indexing"]["embedded"] == 3
    assert response["indexing"]["pending"] == 0


def test_close_scores_are_not_rounded_before_tie_break(mysql_db, active_kb, make_note):
    low_id, high_id = "10000000-0000-4000-8000-000000000001", "f0000000-0000-4000-8000-000000000001"
    publish(mysql_db, active_kb, {"lower.md": make_note(id=low_id), "higher.md": make_note(id=high_id)},
            {"lower.md": [1, 0.0002, 0], "higher.md": [1, 0.0001, 0]})
    hits = search(mysql_db, active_kb, "q", provider=QueryProvider())["hits"]
    assert [hit["path"] for hit in hits] == ["higher.md", "lower.md"]
    assert 0 < hits[0]["score"] - hits[1]["score"] < 1e-6


def test_exact_ties_order_by_document_uuid_bytes_then_ordinal(mysql_db, active_kb, make_note):
    low_id, high_id = "10000000-0000-4000-8000-000000000001", "f0000000-0000-4000-8000-000000000001"
    publish(mysql_db, active_kb, {"z.md": make_note("## A\n\none\n\n## B\n\ntwo\n", id=low_id),
                                 "a.md": make_note(id=high_id)}, {"z.md": [1, 0, 0], "a.md": [1, 0, 0]})
    hits = search(mysql_db, active_kb, "q", provider=QueryProvider())["hits"]
    assert [(h["document_id"], h["ordinal"]) for h in hits] == [(low_id, 0), (low_id, 1), (high_id, 0)]


@pytest.mark.parametrize("query, expected", [("%", ["literal.md"]), ("_", ["literal.md"]),
    ("Go", ["literal.md"]), ("go", ["other.md"]), ("检索", ["literal.md"])])
def test_literal_queries_are_case_sensitive_whole_substrings_without_sql_wildcards(mysql_db, active_kb, make_note, query, expected):
    publish(mysql_db, active_kb, {"literal.md": make_note("Go CI 检索 % _\n"), "other.md": make_note("go arbitrary wildcard text\n")})
    response = search(mysql_db, active_kb, query, mode="lexical", lexical_mode="literal")
    assert [hit["path"] for hit in response["hits"]] == expected
    assert response["lexical_mode"] == "literal"


def test_literal_score_counts_matching_fields_instead_of_occurrences(mysql_db, active_kb, make_note):
    publish(mysql_db, active_kb, {"three.md": make_note("needle\n", title="needle title", summary="needle summary"),
                                 "one.md": make_note("needle needle needle needle\n")})
    hits = search(mysql_db, active_kb, "needle", mode="lexical", lexical_mode="literal")["hits"]
    assert [(hit["path"], hit["score"]) for hit in hits] == [("three.md", 3.0), ("one.md", 1.0)]


def test_fulltext_empty_eligible_ranking_falls_back_to_literal(mysql_db, active_kb, make_note):
    publish(mysql_db, active_kb, {"one.md": make_note("Go CI 检索\n")})
    response = search(mysql_db, active_kb, "Go", mode="lexical")
    assert response["lexical_mode"] == "literal"
    assert [hit["path"] for hit in response["hits"]] == ["one.md"]


def test_fulltext_document_relevance_contributes_to_each_owning_chunk(mysql_db, active_kb, make_note):
    publish(mysql_db, active_kb, {"one.md": make_note("## First\n\nAlpha.\n\n## Second\n\nBeta.\n", title="photosynthesis")})
    response = search(mysql_db, active_kb, "photosynthesis", mode="lexical")
    assert response["lexical_mode"] == "fulltext"
    assert len(response["hits"]) == 2
    assert all(hit["score"] > 0 for hit in response["hits"])
    assert response["hits"][0]["score"] == response["hits"][1]["score"]


def test_hybrid_uses_complete_rankings_before_applying_page_limit(mysql_db, active_kb, make_note):
    documents, vectors = {}, {}
    for semantic_rank in range(1, 26):
        numeric_id = 26 - semantic_rank
        identity = f"20000000-0000-4000-8000-{numeric_id:012x}"
        path = f"{numeric_id:02}.md"
        documents[path] = make_note("needle\n", id=identity)
        vectors[path] = [1, semantic_rank / 20, 0]
    publish(mysql_db, active_kb, documents, vectors)
    expected = sorted([(f"{i:02}.md", 1 / (60 + i) + 1 / (60 + 26 - i)) for i in range(1, 26)],
                      key=lambda item: (-item[1], item[0]))
    response = search(mysql_db, active_kb, "needle", mode="hybrid", lexical_mode="literal", provider=QueryProvider(), limit=3)
    assert [hit["path"] for hit in response["hits"]] == [path for path, _ in expected[:3]]
    assert [hit["score"] for hit in response["hits"]] == pytest.approx([score for _, score in expected[:3]], abs=1e-15)
    assert response["next_cursor"]


def test_filters_exclude_wrong_domain_lifecycle_deleted_and_old_revisions_before_ranking(mysql_db, active_kb, make_note):
    from tribal.storage import ensure_domain
    ensure_domain(mysql_db, knowledge_base=active_kb["key"], key="other", name="Other")
    docs = {"active.md": make_note("needle active\n"), "archived.md": make_note("needle archived\n", status="archived"),
            "other.md": make_note("needle other\n", domain="other"), "deleted.md": make_note("needle deleted\n")}
    first = publish(mysql_db, active_kb, docs, {path: [1, 0, 0] for path in docs})
    execute(mysql_db, "UPDATE documents SET deleted_at=CURRENT_TIMESTAMP(6) WHERE id=%s", (uuid.UUID(first["documents"]["deleted.md"]["document_id"]).bytes,))
    publish(mysql_db, active_kb, {"active.md": based(docs["active.md"].replace("needle active", "current observation"), first["documents"]["active.md"]["revision_id"])})
    assert search(mysql_db, active_kb, "needle", mode="lexical", lexical_mode="literal", domains=["research"])["hits"] == []
    archived = search(mysql_db, active_kb, "needle", mode="lexical", lexical_mode="literal", domains=["research"], statuses=["archived"])
    assert [hit["path"] for hit in archived["hits"]] == ["archived.md"]
    assert search(mysql_db, active_kb, "q", provider=QueryProvider(), domains=["research"])["hits"] == []
    assert search(mysql_db, active_kb, "q", provider=QueryProvider(), domains=[])["hits"] == []


def test_provenance_preserves_declared_context_scope_and_unknown_applicability(mysql_db, active_kb, make_note):
    context = dict(key="trial", type="experiment", locator="trial-12")
    source = dict(type="experiment", locator="notebook", context="trial", revision="edition-1")
    publish(mysql_db, active_kb, {"botany.md": make_note("needle\n", contexts=[context], sources=[source], scope={"soil": "loam"})})
    hit = search(mysql_db, active_kb, "needle", mode="lexical", lexical_mode="literal")["hits"][0]
    assert hit["contexts"] == [context]
    assert hit["scope"] == {"soil": "loam"}
    assert hit["applicability"] == "unknown"
    assert hit["verification_state"] == "unverified"
    assert hit["verified_at"] is None
    assert len(hit["sources"]) == 1
    assert hit["sources"][0]["locator"] == "notebook"


def first_page(db, kb, make_note):
    docs = {f"{i}.md": make_note(f"needle {i}\n") for i in range(3)}
    publish(db, kb, docs, {path: [1, 0, 0] for path in docs})
    provider = QueryProvider()
    response = search(db, kb, "needle", provider=provider, limit=1)
    assert response["next_cursor"]
    return response, provider


def test_continuation_reuses_materialized_ranking_and_query_vector_without_provider(mysql_db, active_kb, make_note):
    first, provider = first_page(mysql_db, active_kb, make_note)
    second = search(mysql_db, active_kb, "needle", limit=2, cursor=first["next_cursor"])
    assert len(provider.calls) == 1
    assert len(second["hits"]) == 2
    assert [h["rank"] for h in second["hits"]] == [2, 3]
    assert first["hits"][0]["chunk_id"] not in [h["chunk_id"] for h in second["hits"]]
    assert second["next_cursor"] is None
    assert second["expires_at"] == first["expires_at"]


@pytest.mark.parametrize("changes", [{"query": "changed"}, {"domains": ["research"]}, {"statuses": []}, {"mode": "lexical"}, {"include_deleted": True}])
def test_cursor_rejects_changed_search_identity(mysql_db, active_kb, make_note, changes):
    from tribal.errors import TribalError
    first, _ = first_page(mysql_db, active_kb, make_note)
    query = changes.get("query", "needle")
    kwargs = {key: value for key, value in changes.items() if key != "query"}
    with pytest.raises(TribalError) as failure:
        search(mysql_db, active_kb, query, cursor=first["next_cursor"], **kwargs)
    assert failure.value.code == "E_CURSOR_INVALID"


@pytest.mark.parametrize("mutation", ["document", "rechunk", "embedding", "readiness", "profile", "ttl"])
def test_cursor_expires_after_each_material_change(mysql_db, active_kb, make_note, mutation):
    from tribal.embeddings import activate_profile, run_worker_once
    from tribal.publication import rechunk_revision
    from tribal.storage import ensure_profile
    from tribal.errors import TribalError
    first, _ = first_page(mysql_db, active_kb, make_note)
    if mutation == "document":
        publish(mysql_db, active_kb, {"new.md": make_note()})
    elif mutation == "rechunk":
        rechunk_revision(mysql_db, knowledge_base=active_kb["key"], document_id=first["hits"][0]["document_id"])
    elif mutation in {"embedding", "readiness"}:
        # Existing fixture embeddings are removed for one exact chunk, then a
        # real worker transitions its already durable job to success/failure.
        job = execute(mysql_db, "SELECT chunk_id FROM embedding_jobs WHERE knowledge_base_id=%s ORDER BY id LIMIT 1", (uuid.UUID(active_kb["id"]).bytes,))[0]
        execute(mysql_db, "DELETE FROM chunk_embeddings WHERE chunk_id=%s", (job["chunk_id"],))
        if mutation == "embedding":
            run_worker_once(mysql_db, QueryProvider(), knowledge_base=active_kb["key"])
        else:
            run_worker_once(mysql_db, QueryProvider([0, 0, 0]), knowledge_base=active_kb["key"])
    elif mutation == "profile":
        profile = ensure_profile(mysql_db, key="profile-" + uuid.uuid4().hex, dimensions=3,
                                  configuration=active_kb["profile"]["configuration"])["profile"]
        activate_profile(mysql_db, knowledge_base=active_kb["key"], profile_id=profile["id"], allow_partial=True)
    else:
        execute(mysql_db, "UPDATE search_sessions SET expires_at=CURRENT_TIMESTAMP(6) WHERE knowledge_base_id=%s", (uuid.UUID(active_kb["id"]).bytes,))
    with pytest.raises(TribalError) as failure:
        search(mysql_db, active_kb, "needle", cursor=first["next_cursor"])
    assert failure.value.code == "E_CURSOR_EXPIRED"


def test_capacity_guard_rejects_incomplete_scan_without_partial_hits(mysql_db, active_kb, make_note):
    from tribal.errors import TribalError
    docs = {f"{i}.md": make_note() for i in range(3)}
    publish(mysql_db, active_kb, docs, {path: [1, 0, 0] for path in docs})
    with pytest.raises(TribalError) as failure:
        search(mysql_db, active_kb, "q", provider=QueryProvider(), max_candidates=2)
    assert failure.value.code == "E_SEARCH_CAPACITY"


def test_semantic_provider_failure_is_explicit_and_does_not_fall_back(mysql_db, active_kb, make_note):
    from tribal.errors import TribalError
    publish(mysql_db, active_kb, {"one.md": make_note("needle\n")}, {"one.md": [1, 0, 0]})
    class Unavailable:
        def embed(self, *args, **kwargs):
            raise TimeoutError("test outage")
    with pytest.raises(TribalError) as failure:
        search(mysql_db, active_kb, "needle", provider=Unavailable())
    assert failure.value.code == "E_EMBEDDING_PROVIDER"


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 101}, {"max_candidates": 0}, {"mode": "unknown"}])
def test_invalid_search_parameters_have_actionable_errors(mysql_db, active_kb, kwargs):
    from tribal.errors import TribalError
    with pytest.raises(TribalError) as failure:
        search(mysql_db, active_kb, "q", provider=QueryProvider(), **kwargs)
    assert failure.value.code == "E_ARGUMENT"


def context_fixture(db, kb, make_note):
    diagram = "```mermaid\nflowchart TD\n" + "A-->B\n" * 700 + "```\n\n"
    body = "## Architecture\n\nMATCH " + "m" * 2900 + "\n\n" + "near " + "n" * 2900 + "\n\n" + diagram + "tail " + "t" * 2900 + "\n\n"
    body += "## Architecture\n\nOther section.\n\n```mermaid\nflowchart TD\nX-->Y\n```\n"
    authored = make_note(body)
    result = publish(db, kb, {"architecture.md": authored})["documents"]["architecture.md"]
    chunks = execute(db, "SELECT * FROM document_chunks WHERE revision_id=%s ORDER BY ordinal", (uuid.UUID(result["revision_id"]).bytes,))
    return authored, result, chunks, diagram


def test_context_prioritizes_complete_unembedded_same_section_diagram_over_nearer_prose(mysql_db, active_kb, make_note):
    from tribal.retrieval import read_context
    _, head, chunks, diagram = context_fixture(mysql_db, active_kb, make_note)
    matched, mermaid = chunks[0], next(c for c in chunks if c["content"] == diagram)
    budget = len(matched["content"].encode()) + len(diagram.encode())
    response = read_context(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], revision_id=head["revision_id"], chunk_id=matched["id"], budget_bytes=budget)
    assert [c["id"] for c in response["chunks"]] == [matched["id"], mermaid["id"]]
    assert response["used_bytes"] == budget
    assert response["complete"] is False
    assert all(c["end_byte"] <= response["section_end_byte"] for c in response["chunks"])
    assert response["section_end_byte"] == chunks[-1]["start_byte"]
    assert response["omitted_chunk_ids"] == [chunks[1]["id"], chunks[3]["id"]]
    assert response["omitted_bytes"] == sum(len(c["content"].encode()) for c in (chunks[1], chunks[3]))
    assert all(c["section_anchor"] is None for c in chunks), "duplicate headings deliberately have no section anchor"


def test_context_skips_nonfitting_candidate_and_considers_smaller_following_chunks(mysql_db, active_kb, make_note):
    from tribal.retrieval import read_context
    _, head, chunks, diagram = context_fixture(mysql_db, active_kb, make_note)
    budget = len(chunks[0]["content"].encode()) + len(chunks[1]["content"].encode())
    response = read_context(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], revision_id=head["revision_id"], chunk_id=chunks[0]["id"], budget_bytes=budget)
    assert [c["id"] for c in response["chunks"]] == [chunks[0]["id"], chunks[1]["id"]]
    assert diagram not in [c["content"] for c in response["chunks"]]


def test_context_uses_historical_revision_after_current_document_changes(mysql_db, active_kb, make_note):
    from tribal.retrieval import read_context
    authored, head, chunks, diagram = context_fixture(mysql_db, active_kb, make_note)
    publish(mysql_db, active_kb, {"architecture.md": based(authored.replace("A-->B", "NEW-->GRAPH"), head["revision_id"])})
    response = read_context(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], revision_id=head["revision_id"], chunk_id=chunks[0]["id"])
    assert response["revision_id"] == head["revision_id"]
    assert diagram in [c["content"] for c in response["chunks"]]
    assert not any("NEW-->GRAPH" in c["content"] or "X-->Y" in c["content"] for c in response["chunks"])
    assert response["complete"] is True


def test_context_cannot_truncate_matched_chunk_to_fit_budget(mysql_db, active_kb, make_note):
    from tribal.errors import TribalError
    from tribal.retrieval import read_context
    _, head, chunks, _ = context_fixture(mysql_db, active_kb, make_note)
    with pytest.raises(TribalError) as failure:
        read_context(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], revision_id=head["revision_id"], chunk_id=chunks[0]["id"], budget_bytes=len(chunks[0]["content"].encode()) - 1)
    assert failure.value.code == "E_CONTEXT_BUDGET_EXCEEDED"


def test_document_read_returns_exact_canonical_utf8_ranges_and_enforces_ownership(mysql_db, active_kb, make_note):
    from tribal.retrieval import read_document
    from tribal.errors import TribalError
    authored = make_note("前置き🌱\n")
    head = publish(mysql_db, active_kb, {"one.md": authored})["documents"]["one.md"]
    response = read_document(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"])
    assert response["content"] == authored
    start = authored.encode().index("🌱".encode())
    sliced = read_document(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], start_byte=start, end_byte=start + 4)
    assert sliced["content"] == "🌱"
    for kwargs in (dict(start_byte=start), dict(start_byte=start + 1, end_byte=start + 4), dict(start_byte=-1, end_byte=2)):
        with pytest.raises(TribalError) as failure:
            read_document(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], **kwargs)
        assert failure.value.code == "E_ARGUMENT"
    other = publish(mysql_db, active_kb, {"two.md": make_note()})["documents"]["two.md"]
    with pytest.raises(TribalError) as failure:
        read_document(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"], revision_id=other["revision_id"])
    assert failure.value.code == "E_NOT_FOUND"
