---
schema_version: 1
id: fccf087c-e849-4ad3-b74b-a36fc0899b97
title: Embedding Profiles
knowledge_base: tribal
domain: indexing
kind: reference
summary: Embedding profiles bind a stable profile key to provider, model, dimensions, and supported input configuration. A knowledge base activates one profile, and profile changes are handled by registering and indexing a new profile before switching over.
status: active
tags:
  - tribal
  - indexing
  - embeddings
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
    locator: src/tribal/storage.py
    context: tribal-source
    details:
      symbols: [DEFAULT_PROFILE_CONFIGURATION, ensure_profile, get_profile]
  - type: code
    locator: src/tribal/embeddings.py
    context: tribal-source
    details:
      symbols: [activate_profile, indexing_status, backfill_embeddings]
  - type: code
    locator: src/tribal/migrations/001_content.sql
    context: tribal-source
    details:
      symbols: [embedding_profiles, knowledge_bases.active_profile_id, chunk_embeddings]
  - type: test
    locator: tests/test_worker_contract.py
    context: tribal-source
    details:
      outcome: not-run-code-inspection
      symbols: [test_profile_activation_requires_coverage_and_partial_override_is_disclosed, test_inactive_profile_can_be_backfilled_and_completed_before_activation]
---

# Embedding Profiles

An embedding profile is the compatibility identity for vectors. `ensure_profile` registers a unique `profile_key` with a provider, model, optional model version, dimensions, and configuration. Calling it again with the same key and a different setting raises `E_CONFLICT`; the recovery path is to register a new key. The database stores profiles separately from the knowledge base's `active_profile_id`, so profile registration does not itself switch search to that profile. See [[Home]], [[Architecture/System Map]], and [[Retrieval/Search and Ranking]] for how indexing configuration connects to the wider system.

The current default configuration is wrapper `tribal-title-headings-v1`, encoding `cl100k_base`, maximum input 8,192 tokens, cosine distance, and `l2-float32-v1` normalization. `ensure_profile` checks that wrapper, distance, and normalization match the supported identifiers, that the tokenizer encoding is registered, and that the token limit is a positive integer. For the OpenAI `text-embedding-3-small` and `text-embedding-3-large` model names, it also rejects limits above 8,192. Dimensions must be an integer from 1 through 16,383. The configured model version is retained as profile identity metadata; the code does not discover or certify a provider's live model revision.

Profile rollout is explicit. `indexing_status` evaluates a chosen profile against every current chunk in non-deleted documents. `backfill_embeddings` can enqueue a profile whether or not it is active. This allows an inactive replacement to be filled and checked first. `activate_profile` refuses incomplete coverage with `E_PROFILE_INCOMPLETE` unless the caller sets `allow_partial=True`; that override switches the profile while returning `W_INDEXING_PARTIAL`. Changing the active profile advances the indexing generation. Activating the already-active profile does not advance it. New document chunks are queued against the active profile by publication code, while an inactive profile requires explicit backfill.

Vector reuse is scoped to the same knowledge base and exact profile ID, input hash, and dimensions. Matching dimensionality alone does not make profiles compatible. Therefore, a newly registered profile does not inherit vectors under another profile even when its other settings happen to match. The compatible reuse rule and the exact input identity are described in [[Indexing/Embedding Inputs and Vectors]]; the database rows and active-profile relationship are part of [[Storage/Database and Migrations]].

`ready` means every current chunk has a valid stored embedding for the selected profile and its current exact input. It does not mean provider quality was measured or that a live provider was consulted. A zero-chunk corpus is ready by vacuous coverage. If an operator explicitly activates a partial profile, search can use it while status still reports gaps; see [[Indexing/Durable Embedding Worker]] for the queue and terminal states. These statements describe code at the declared snapshot; the contract tests were inspected but not run.
