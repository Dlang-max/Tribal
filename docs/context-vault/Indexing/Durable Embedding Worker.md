---
schema_version: 1
id: f2bb0742-67ed-4a2e-a94e-9d3377f49a66
title: Durable Embedding Worker
knowledge_base: tribal
domain: indexing
kind: overview
summary: Embedding jobs persist queue state and use leased random claim tokens to fence workers whose claims expire or whose source identity changes. Provider calls happen after the claim transaction commits; result publication rechecks the lease, profile, job identity, and reconstructed input.
status: active
tags:
  - tribal
  - indexing
  - workers
verification_state: unverified
contexts:
  - key: tribal-source
    type: git_repository
    locator: /home/daniel-lang/Desktop/Tribal
    details:
      branch: main
      commit: 245e7c3ccc19aaa8022c749d805a53f7560cf72e
scope:
  source_snapshot: 245e7c3ccc19aaa8022c749d805a53f7560cf72e
sources:
  - type: code
    locator: src/tribal/embeddings.py
    context: tribal-source
    details:
      symbols: [enqueue_chunks, indexing_status, backfill_embeddings, retry_embeddings, _claim_job, _publish_job, run_worker_once]
  - type: code
    locator: src/tribal/migrations/002_jobs_sessions.sql
    context: tribal-source
    details:
      symbols: [embedding_jobs]
  - type: code
    locator: src/tribal/publication.py
    context: tribal-source
    details:
      symbols: [ingest_vault]
  - type: test
    locator: tests/test_worker_contract.py
    context: tribal-source
    details:
      outcome: not-run-code-inspection
      symbols: [test_expired_worker_cannot_overwrite_or_reschedule_reclaimed_job, test_rechunk_during_provider_call_discards_stale_identity, test_transient_retries_are_durable_honor_retry_after_and_stop_at_three]
---

# Durable Embedding Worker

Publication inserts an idempotent job for each chunk and active profile, identified by chunk ID, revision ID, profile ID, and exact input hash. `backfill_embeddings` scans current chunks for a chosen profile, reuses only a compatible same-knowledge-base vector when available, and otherwise repairs/enqueues missing work. Repeated backfills do not duplicate the same job identity. Queue scheduling alone does not mean a vector is ready; [[Indexing/Embedding Inputs and Vectors]] defines the input and reuse boundary, while [[Storage/Publication and Revisions]] explains why replaced chunks keep distinct identities. [[Home]] and [[Architecture/System Map]] place this worker in the broader service flow.

`run_worker_once` claims at most one available job. It finds a candidate, then acquires the knowledge-base lock before locking and rechecking the job row. Claiming sets state to `running`, increments `attempts`, assigns a fresh 16-byte token, and gives it a 120-second lease. The transaction commits before token counting and provider work, so the call runs without holding the knowledge-base lock. The OpenAI adapter has a 30-second request timeout and SDK automatic retries disabled; durable job state owns retry scheduling. These timings and state fields are defined in [[Storage/Database and Migrations]].

On publication, the worker reacquires the knowledge-base lock and accepts the result only while the job is still running, the lease remains valid, and the token still matches. It also confirms the stored job identity and immutable profile match the claim and reconstructs the original wrapped input from the original chunk/revision to compare its hash and text. A late worker cannot clear or reschedule a reclaimed claim. If rechunking or another edit invalidates that identity, the result is discarded rather than attached to a replacement chunk with the same ordinal. Successful publication writes the vector and marks the job succeeded atomically; terminal success, oversized input, and failure advance the indexing generation.

Transient connection errors and HTTP 408, 409, 429, and 5xx responses are durably requeued while fewer than three attempts have been made. The scheduled delay honors valid provider `retry-after-ms`, numeric `retry-after`, or HTTP-date guidance; otherwise it uses bounded exponential delay `min(60, 2 ** attempts)`. Tribal records the next availability time instead of sleeping through that delay. A third transient failure becomes terminal `failed`. Invalid or negative provider guidance falls back to the bounded delay; provider error bodies are not copied into public diagnostics. Explicit `retry_embeddings` resets current failed jobs for the selected profile to queued with attempts zero. An expired claim already at three attempts is made failed without another provider call.

Oversized inputs become terminal `oversized`, with a warning that the complete input exceeded the configured limit. This is a preservation boundary: keep the authored content, choose a supported profile with an appropriate limit, or deliberately revise the source. `indexing_status` marks a chunk embedded only when it finds a valid vector with the selected profile's dimensions and a hash equal to the current wrapped input. It reports `pending`, `failed`, and `oversized` categories for gaps; `ready` is true only when every current chunk is embedded, including the empty-corpus case. Partial profile activation can expose a usable but incomplete index with an explicit warning; [[Indexing/Embedding Profiles]] covers that rollout, and [[Retrieval/Search and Ranking]] describes search behavior against the active profile.

Contract tests describe distinct concurrent claims, expired-lease fencing, stale rechunk discard, retry guidance, and readiness. They were inspected but not run; this note records source behavior at the declared snapshot rather than a live database or provider observation.
