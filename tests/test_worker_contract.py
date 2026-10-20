"""Durable claims, stale-worker fencing and coverage on real MySQL."""
from __future__ import annotations

import json
import math
import struct
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from acceptance_helpers import execute

pytestmark = pytest.mark.mysql


class Provider:
    def __init__(self, vector=(1, 2, 3)):
        self.calls = []
        self.vector = list(vector)

    def embed(self, text, *, model, dimensions):
        self.calls.append(text)
        return self.vector


def ingest(db, kb, documents):
    from tribal.publication import ingest_vault
    result = ingest_vault(db, documents, knowledge_base=kb["key"])
    assert result["ok"] is True, result["diagnostics"]
    return result


def jobs(db, kb):
    return execute(db, "SELECT *, TIMESTAMPDIFF(MICROSECOND,CURRENT_TIMESTAMP(6),lease_expires_at)/1000000 AS remaining FROM embedding_jobs WHERE knowledge_base_id=%s ORDER BY id", (uuid.UUID(kb["id"]).bytes,))


def generation(db, kb):
    from tribal.storage import get_knowledge_base
    return get_knowledge_base(db, knowledge_base=kb["key"])["knowledge_base"]["indexing_generation"]


def worker(db, kb, provider):
    from tribal.embeddings import run_worker_once
    return run_worker_once(db, provider, knowledge_base=kb["key"])


def test_empty_corpus_is_ready_and_worker_is_idle(mysql_db, active_kb):
    from tribal.embeddings import indexing_status
    status = indexing_status(mysql_db, knowledge_base=active_kb["key"])
    assert {key: status[key] for key in ("total", "embedded", "pending", "oversized", "failed")} == dict(total=0, embedded=0, pending=0, oversized=0, failed=0)
    assert status["ready"] is True
    result = worker(mysql_db, active_kb, Provider())
    assert result["job_id"] is None and result["state"] == "idle" and result["attempts"] == 0


def test_backfill_is_idempotent_and_missing_jobs_are_repaired_explicitly(mysql_db, active_kb, make_note):
    from tribal.embeddings import backfill_embeddings
    head = ingest(mysql_db, active_kb, {"one.md": make_note()})["documents"]["one.md"]
    before = generation(mysql_db, active_kb)
    assert backfill_embeddings(mysql_db, knowledge_base=active_kb["key"])["enqueued"] == 0
    execute(mysql_db, "DELETE FROM embedding_jobs WHERE chunk_id=%s", (head["chunk_ids"][0],))
    assert backfill_embeddings(mysql_db, knowledge_base=active_kb["key"])["enqueued"] == 1
    assert backfill_embeddings(mysql_db, knowledge_base=active_kb["key"])["enqueued"] == 0
    assert len(jobs(mysql_db, active_kb)) == 1
    assert generation(mysql_db, active_kb) == before, "queue scheduling alone does not change indexing generation"


def test_provider_runs_after_committed_claim_and_outside_kb_lock(mysql_db, active_kb, make_note):
    from tribal.storage import lock_knowledge_base
    from tribal.embeddings import indexing_status
    ingest(mysql_db, active_kb, {"one.md": make_note()})
    before = generation(mysql_db, active_kb)
    class ObserveClaim(Provider):
        def embed(self, text, **kwargs):
            row = jobs(mysql_db, active_kb)[0]
            assert row["state"] == "running" and row["attempts"] == 1
            assert len(bytes(row["claim_token"])) == 16
            assert 110 < float(row["remaining"]) <= 120
            assert generation(mysql_db, active_kb) == before
            # This would deadlock or fail nested-transaction checks if the model
            # call held the worker's database transaction/KB lock.
            with mysql_db.transaction() as connection:
                lock_knowledge_base(connection, active_kb["key"])
            return super().embed(text, **kwargs)
    provider = ObserveClaim()
    result = worker(mysql_db, active_kb, provider)
    assert result["state"] == "succeeded" and result["attempts"] == 1
    assert len(provider.calls) == 1
    row = jobs(mysql_db, active_kb)[0]
    assert row["state"] == "succeeded" and row["claim_token"] is row["lease_expires_at"] is None
    status = indexing_status(mysql_db, knowledge_base=active_kb["key"])
    assert status["embedded"] == status["total"] == 1 and status["ready"] is True
    assert generation(mysql_db, active_kb) == before + 1


def test_simultaneous_workers_claim_distinct_jobs(mysql_db, active_kb, make_note):
    ingest(mysql_db, active_kb, {"a.md": make_note("alpha\n"), "b.md": make_note("beta\n")})
    barrier = threading.Barrier(3)
    release = threading.Event()
    class Blocking(Provider):
        def embed(self, text, **kwargs):
            barrier.wait(timeout=10)
            assert release.wait(10)
            return super().embed(text, **kwargs)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker, mysql_db, active_kb, Blocking()) for _ in range(2)]
        try:
            barrier.wait(timeout=10)
            running = jobs(mysql_db, active_kb)
            assert len(running) == 2 and all(row["state"] == "running" for row in running)
            assert len({bytes(row["claim_token"]) for row in running}) == 2
        finally:
            release.set()
        outcomes = [future.result(timeout=15) for future in futures]
    assert len({row["job_id"] for row in outcomes}) == 2
    assert all(row["state"] == "succeeded" for row in outcomes)


@pytest.mark.parametrize("old_failure", [False, True])
def test_expired_worker_cannot_overwrite_or_reschedule_reclaimed_job(mysql_db, active_kb, make_note, old_failure):
    ingest(mysql_db, active_kb, {"one.md": make_note()})
    started, release = threading.Event(), threading.Event()
    tokens = []
    class Old(Provider):
        def embed(self, text, **kwargs):
            tokens.append(bytes(jobs(mysql_db, active_kb)[0]["claim_token"]))
            started.set()
            assert release.wait(10)
            if old_failure:
                raise TimeoutError("old provider finished late")
            return [1, 0, 0]
    class New(Provider):
        def embed(self, text, **kwargs):
            tokens.append(bytes(jobs(mysql_db, active_kb)[0]["claim_token"]))
            return [0, 1, 0]
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(worker, mysql_db, active_kb, Old())
        try:
            assert started.wait(5)
            job = jobs(mysql_db, active_kb)[0]
            execute(mysql_db, "UPDATE embedding_jobs SET lease_expires_at=DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 1 SECOND) WHERE id=%s", (job["id"],))
            newer = worker(mysql_db, active_kb, New())
            assert newer["state"] == "succeeded" and newer["attempts"] == 2
        finally:
            release.set()
        older = future.result(timeout=15)
    assert older["state"] == "discarded"
    assert len(tokens) == 2 and tokens[0] != tokens[1]
    row = jobs(mysql_db, active_kb)[0]
    assert row["state"] == "succeeded" and row["attempts"] == 2
    vector = execute(mysql_db, "SELECT CAST(embedding AS BINARY) AS vector FROM chunk_embeddings WHERE chunk_id=%s AND profile_id=%s", (row["chunk_id"], uuid.UUID(active_kb["profile"]["id"]).bytes))[0]["vector"]
    assert bytes(vector) == struct.pack("<fff", 0, 1, 0)


def test_rechunk_during_provider_call_discards_stale_identity(mysql_db, active_kb, make_note):
    from tribal.publication import rechunk_revision
    head = ingest(mysql_db, active_kb, {"one.md": make_note()})["documents"]["one.md"]
    started, release = threading.Event(), threading.Event()
    class Blocking(Provider):
        def embed(self, text, **kwargs):
            started.set()
            assert release.wait(10)
            return super().embed(text, **kwargs)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(worker, mysql_db, active_kb, Blocking())
        try:
            assert started.wait(5)
            replacement = rechunk_revision(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"])
            assert not set(replacement["chunk_ids"]).intersection(head["chunk_ids"])
        finally:
            release.set()
        assert future.result(timeout=15)["state"] == "discarded"
    assert execute(mysql_db, "SELECT COUNT(*) AS n FROM chunk_embeddings WHERE chunk_id=%s", (replacement["chunk_ids"][0],))[0]["n"] == 0
    assert jobs(mysql_db, active_kb)[0]["chunk_id"] == head["chunk_ids"][0]
    assert jobs(mysql_db, active_kb)[0]["state"] == "discarded"


def test_transient_retries_are_durable_honor_retry_after_and_stop_at_three(mysql_db, active_kb, make_note):
    import httpx2 as httpx
    import openai
    ingest(mysql_db, active_kb, {"one.md": make_note()})
    before = generation(mysql_db, active_kb)
    class RateLimited(Provider):
        def embed(self, text, **kwargs):
            self.calls.append(text)
            response = httpx.Response(429, headers={"retry-after": "7"}, request=httpx.Request("POST", "https://example.invalid"))
            raise openai.RateLimitError("synthetic rate limit", response=response, body={"unsafe": "provider-secret-sentinel"})
    provider = RateLimited()
    for attempt in range(1, 4):
        started = time.monotonic()
        result = worker(mysql_db, active_kb, provider)
        assert time.monotonic() - started < 5, "retry scheduling must not sleep through Retry-After"
        row = jobs(mysql_db, active_kb)[0]
        assert row["attempts"] == attempt
        assert row["claim_token"] is row["lease_expires_at"] is None
        assert "provider-secret-sentinel" not in json.dumps(result)
        if attempt < 3:
            assert result["state"] == row["state"] == "queued"
            delay = execute(mysql_db, "SELECT TIMESTAMPDIFF(MICROSECOND,CURRENT_TIMESTAMP(6),available_at)/1000000 AS delay FROM embedding_jobs WHERE id=%s", (row["id"],))[0]["delay"]
            assert 5 < float(delay) <= 7
            assert worker(mysql_db, active_kb, provider)["state"] == "idle"
            assert generation(mysql_db, active_kb) == before
            execute(mysql_db, "UPDATE embedding_jobs SET available_at=CURRENT_TIMESTAMP(6) WHERE id=%s", (row["id"],))
        else:
            assert result["state"] == row["state"] == "failed"
    assert len(provider.calls) == 3
    assert worker(mysql_db, active_kb, provider)["state"] == "idle"
    assert generation(mysql_db, active_kb) == before + 1


def test_exhausted_expired_claim_becomes_terminal_without_provider_call(mysql_db, active_kb, make_note):
    ingest(mysql_db, active_kb, {"one.md": make_note()})
    row = jobs(mysql_db, active_kb)[0]
    execute(mysql_db, "UPDATE embedding_jobs SET state='running',attempts=3,claim_token=%s,lease_expires_at=DATE_SUB(CURRENT_TIMESTAMP(6),INTERVAL 1 SECOND) WHERE id=%s", (uuid.uuid4().bytes, row["id"]))
    before = generation(mysql_db, active_kb)
    provider = Provider()
    worker(mysql_db, active_kb, provider)
    assert provider.calls == []
    assert jobs(mysql_db, active_kb)[0]["state"] == "failed"
    assert generation(mysql_db, active_kb) == before + 1


@pytest.mark.parametrize("vector", [[0, 0, 0], [math.nan, 1, 0], [1, 2]])
def test_malformed_provider_vector_is_terminal_and_content_remains_accepted(mysql_db, active_kb, make_note, vector):
    from tribal.embeddings import indexing_status
    from tribal.retrieval import read_document
    head = ingest(mysql_db, active_kb, {"one.md": make_note()})["documents"]["one.md"]
    provider = Provider(vector)
    assert worker(mysql_db, active_kb, provider)["state"] == "failed"
    assert worker(mysql_db, active_kb, provider)["state"] == "idle"
    assert len(provider.calls) == 1
    status = indexing_status(mysql_db, knowledge_base=active_kb["key"])
    assert status["failed"] == 1 and status["embedded"] == status["pending"] == 0
    assert status["ready"] is False
    assert read_document(mysql_db, knowledge_base=active_kb["key"], document_id=head["document_id"])["revision_id"] == head["revision_id"]


def test_oversized_complete_wrapper_is_not_truncated_or_repeated(mysql_db, active_kb, make_note):
    from tribal.embeddings import activate_profile, indexing_status
    from tribal.storage import ensure_profile
    profile = ensure_profile(mysql_db, key="small-" + uuid.uuid4().hex, dimensions=3,
                             configuration={**active_kb["profile"]["configuration"], "max_input_tokens": 5})["profile"]
    activate_profile(mysql_db, knowledge_base=active_kb["key"], profile_id=profile["id"])
    ingest(mysql_db, active_kb, {"one.md": make_note("short\n", title="Long metadata title included in full embedding input")})
    provider = Provider()
    result = worker(mysql_db, active_kb, provider)
    assert result["state"] == "oversized"
    assert "W_EMBEDDING_INPUT_TOO_LARGE" in {d["code"] for d in result["diagnostics"]}
    assert provider.calls == []
    assert worker(mysql_db, active_kb, provider)["state"] == "idle"
    status = indexing_status(mysql_db, knowledge_base=active_kb["key"])
    assert status["oversized"] == 1 and status["pending"] == 0 and not status["ready"]


def test_retry_resets_only_failed_jobs_and_changes_readiness_generation(mysql_db, active_kb, make_note):
    from tribal.embeddings import retry_embeddings
    ingest(mysql_db, active_kb, {"a.md": make_note("first\n"), "b.md": make_note("second\n")})
    assert worker(mysql_db, active_kb, Provider([0, 0, 0]))["state"] == "failed"
    assert worker(mysql_db, active_kb, Provider())["state"] == "succeeded"
    before = generation(mysql_db, active_kb)
    result = retry_embeddings(mysql_db, knowledge_base=active_kb["key"])
    assert result["retried"] == 1
    rows = jobs(mysql_db, active_kb)
    assert rows[0]["state"] == "queued" and rows[0]["attempts"] == 0
    assert rows[1]["state"] == "succeeded" and rows[1]["attempts"] == 1
    assert generation(mysql_db, active_kb) == before + 1
    assert retry_embeddings(mysql_db, knowledge_base=active_kb["key"])["retried"] == 0


def test_profile_activation_requires_coverage_and_partial_override_is_disclosed(mysql_db, active_kb, make_note):
    from tribal.embeddings import activate_profile, backfill_embeddings, indexing_status
    from tribal.errors import TribalError
    from tribal.storage import ensure_profile, get_knowledge_base
    ingest(mysql_db, active_kb, {"one.md": make_note()})
    worker(mysql_db, active_kb, Provider())
    profile = ensure_profile(mysql_db, key="migration-" + uuid.uuid4().hex, dimensions=3,
                             configuration=active_kb["profile"]["configuration"])["profile"]
    with pytest.raises(TribalError) as failure:
        activate_profile(mysql_db, knowledge_base=active_kb["key"], profile_id=profile["id"])
    assert failure.value.code == "E_PROFILE_INCOMPLETE"
    assert get_knowledge_base(mysql_db, knowledge_base=active_kb["key"])["knowledge_base"]["active_profile_id"] == active_kb["profile"]["id"]
    partial = activate_profile(mysql_db, knowledge_base=active_kb["key"], profile_id=profile["id"], allow_partial=True)
    assert "W_INDEXING_PARTIAL" in {d["code"] for d in partial["diagnostics"]}
    assert indexing_status(mysql_db, knowledge_base=active_kb["key"])["pending"] == 1
    assert backfill_embeddings(mysql_db, knowledge_base=active_kb["key"])["enqueued"] == 1
    migration_provider = Provider()
    assert worker(mysql_db, active_kb, migration_provider)["state"] == "succeeded"
    assert len(migration_provider.calls) == 1, "a distinct profile cannot reuse the old profile vector"
    assert indexing_status(mysql_db, knowledge_base=active_kb["key"])["ready"] is True
    before = generation(mysql_db, active_kb)
    activate_profile(mysql_db, knowledge_base=active_kb["key"], profile_id=profile["id"])
    assert generation(mysql_db, active_kb) == before


def test_embedding_reuse_stays_within_exact_kb_profile_and_input(mysql_db, active_kb, make_note):
    from tribal.storage import ensure_domain, ensure_knowledge_base
    from tribal.embeddings import activate_profile
    first = make_note("same exact source\n")
    ingest(mysql_db, active_kb, {"first.md": first})
    provider = Provider()
    worker(mysql_db, active_kb, provider)
    ingest(mysql_db, active_kb, {"second.md": make_note("same exact source\n")})
    reused = Provider()
    assert worker(mysql_db, active_kb, reused)["state"] == "succeeded"
    assert reused.calls == [], "an exact compatible same-KB input should reuse its stored vector"
    other_key = "separate-" + uuid.uuid4().hex
    other = ensure_knowledge_base(mysql_db, key=other_key, name="Separate")["knowledge_base"]
    ensure_domain(mysql_db, knowledge_base=other_key, key="research", name="Research")
    activate_profile(mysql_db, knowledge_base=other_key, profile_id=active_kb["profile"]["id"])
    other_kb = dict(key=other_key, id=other["id"], profile=active_kb["profile"])
    ingest(mysql_db, other_kb, {"same.md": make_note("same exact source\n", knowledge_base=other_key)})
    separate = Provider()
    assert worker(mysql_db, other_kb, separate)["state"] == "succeeded"
    assert len(separate.calls) == 1, "a different KB must not reuse the first KB's embeddings"


def test_lease_expiry_without_reclaim_cannot_be_revived_by_late_success(mysql_db, active_kb, make_note):
    ingest(mysql_db, active_kb, {"one.md": make_note()})
    class Expiring(Provider):
        def embed(self, text, **kwargs):
            row = jobs(mysql_db, active_kb)[0]
            execute(mysql_db, "UPDATE embedding_jobs SET lease_expires_at=DATE_SUB(CURRENT_TIMESTAMP(6),INTERVAL 1 SECOND) WHERE id=%s", (row["id"],))
            return super().embed(text, **kwargs)
    assert worker(mysql_db, active_kb, Expiring())["state"] == "discarded"
    row = jobs(mysql_db, active_kb)[0]
    assert execute(mysql_db, "SELECT COUNT(*) AS n FROM chunk_embeddings WHERE chunk_id=%s", (row["chunk_id"],))[0]["n"] == 0
    assert row["state"] != "succeeded"


def test_database_enforces_duplicate_job_identity_and_running_claim_invariant(mysql_db, active_kb, make_note):
    from tribal.errors import TribalError
    ingest(mysql_db, active_kb, {"one.md": make_note()})
    row = jobs(mysql_db, active_kb)[0]
    with pytest.raises(TribalError) as failure:
        execute(mysql_db, "INSERT INTO embedding_jobs(knowledge_base_id,chunk_id,revision_id,profile_id,input_hash) VALUES (%s,%s,%s,%s,%s)",
                tuple(row[key] for key in ("knowledge_base_id", "chunk_id", "revision_id", "profile_id", "input_hash")))
    assert failure.value.code == "E_DATABASE"
    with pytest.raises(TribalError) as failure:
        execute(mysql_db, "UPDATE embedding_jobs SET state='running' WHERE id=%s", (row["id"],))
    assert failure.value.code == "E_DATABASE"
    assert len(jobs(mysql_db, active_kb)) == 1
    assert jobs(mysql_db, active_kb)[0]["state"] == "queued"


@pytest.mark.parametrize("status_code, expected_state", [(408, "queued"), (409, "queued"),
    (500, "queued"), (503, "queued"), (400, "failed"), (401, "failed"), (403, "failed"), (422, "failed")])
def test_provider_http_failures_have_durable_transient_or_terminal_classification(mysql_db, active_kb, make_note, status_code, expected_state):
    import httpx2 as httpx
    import openai
    ingest(mysql_db, active_kb, {"one.md": make_note()})
    before = generation(mysql_db, active_kb)
    class HttpFailure(Provider):
        def embed(self, text, **kwargs):
            self.calls.append(text)
            response = httpx.Response(status_code, request=httpx.Request("POST", "https://example.invalid"))
            raise openai.APIStatusError("synthetic provider failure", response=response, body={"detail": "unsafe-response-sentinel"})
    provider = HttpFailure()
    result = worker(mysql_db, active_kb, provider)
    assert result["state"] == expected_state and result["attempts"] == 1
    row = jobs(mysql_db, active_kb)[0]
    assert row["state"] == expected_state
    assert row["claim_token"] is row["lease_expires_at"] is None
    assert "unsafe-response-sentinel" not in json.dumps(result)
    assert "unsafe-response-sentinel" not in (row["last_error_message"] or "")
    assert generation(mysql_db, active_kb) == before + (expected_state == "failed")
    assert len(provider.calls) == 1


@pytest.mark.parametrize("timeout", [False, True])
def test_sdk_connection_and_timeout_failures_release_claim_for_retry(mysql_db, active_kb, make_note, timeout):
    import httpx2 as httpx
    import openai
    ingest(mysql_db, active_kb, {"one.md": make_note()})
    class ConnectionFailure(Provider):
        def embed(self, text, **kwargs):
            self.calls.append(text)
            request = httpx.Request("POST", "https://example.invalid")
            if timeout:
                raise openai.APITimeoutError(request=request)
            raise openai.APIConnectionError(request=request)
    provider = ConnectionFailure()
    assert worker(mysql_db, active_kb, provider)["state"] == "queued"
    row = jobs(mysql_db, active_kb)[0]
    assert row["state"] == "queued" and row["attempts"] == 1
    assert row["claim_token"] is row["lease_expires_at"] is None
    assert len(provider.calls) == 1


def test_reconstructed_input_hash_mismatch_is_discarded_without_vector_publication(mysql_db, active_kb, make_note):
    ingest(mysql_db, active_kb, {"one.md": make_note()})
    row = jobs(mysql_db, active_kb)[0]
    execute(mysql_db, "UPDATE embedding_jobs SET input_hash=%s WHERE id=%s", (b"x" * 32, row["id"]))
    result = worker(mysql_db, active_kb, Provider())
    assert result["state"] == "discarded"
    assert jobs(mysql_db, active_kb)[0]["state"] == "discarded"
    assert execute(mysql_db, "SELECT COUNT(*) AS n FROM chunk_embeddings WHERE chunk_id=%s", (row["chunk_id"],))[0]["n"] == 0


def test_global_worker_claims_by_database_availability_then_job_id(mysql_db, active_kb, make_note):
    from tribal.embeddings import run_worker_once
    ingest(mysql_db, active_kb, {"a.md": make_note("first global candidate\n"),
                                "b.md": make_note("second global candidate\n"),
                                "c.md": make_note("third global candidate\n")})
    rows = jobs(mysql_db, active_kb)
    # Give this isolated test's jobs priority over prior retained fixture jobs;
    # database time still controls lease/attempt deadlines.
    execute(mysql_db, "UPDATE embedding_jobs SET available_at=%s WHERE id=%s", ("2001-01-01 00:00:00", rows[0]["id"]))
    execute(mysql_db, "UPDATE embedding_jobs SET available_at=%s WHERE id=%s", ("2000-01-01 00:00:00", rows[1]["id"]))
    execute(mysql_db, "UPDATE embedding_jobs SET available_at=%s WHERE id=%s", ("2001-01-01 00:00:00", rows[2]["id"]))
    provider = Provider()
    results = [run_worker_once(mysql_db, provider, knowledge_base=None) for _ in range(3)]
    assert [result["job_id"] for result in results] == [rows[1]["id"], rows[0]["id"], rows[2]["id"]]
    assert all(result["state"] == "succeeded" for result in results)
    assert len(provider.calls) == 3


def test_inactive_profile_can_be_backfilled_and_completed_before_activation(mysql_db, active_kb, make_note):
    from tribal.embeddings import activate_profile, backfill_embeddings, indexing_status
    from tribal.storage import ensure_profile, get_knowledge_base
    ingest(mysql_db, active_kb, {"one.md": make_note()})
    assert worker(mysql_db, active_kb, Provider())["state"] == "succeeded"
    profile = ensure_profile(mysql_db, key="inactive-" + uuid.uuid4().hex, dimensions=3,
                             configuration=active_kb["profile"]["configuration"])["profile"]
    queued = backfill_embeddings(mysql_db, knowledge_base=active_kb["key"], profile_id=profile["id"])
    assert queued["enqueued"] == 1
    assert indexing_status(mysql_db, knowledge_base=active_kb["key"], profile_id=profile["id"])["pending"] == 1
    assert get_knowledge_base(mysql_db, knowledge_base=active_kb["key"])["knowledge_base"]["active_profile_id"] == active_kb["profile"]["id"]
    provider = Provider()
    assert worker(mysql_db, active_kb, provider)["state"] == "succeeded"
    assert len(provider.calls) == 1
    assert indexing_status(mysql_db, knowledge_base=active_kb["key"], profile_id=profile["id"])["ready"] is True
    activated = activate_profile(mysql_db, knowledge_base=active_kb["key"], profile_id=profile["id"])
    assert activated["ok"] is True
    assert get_knowledge_base(mysql_db, knowledge_base=active_kb["key"])["knowledge_base"]["active_profile_id"] == profile["id"]
