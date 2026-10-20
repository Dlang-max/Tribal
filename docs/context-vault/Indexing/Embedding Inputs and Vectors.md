---
schema_version: 1
id: 812e7758-50a1-4c13-a5da-1c0862cd0bf4
title: Embedding Inputs and Vectors
knowledge_base: tribal
domain: indexing
kind: reference
summary: Tribal derives a deterministic complete embedding string from a document title, heading ancestry, and preserved chunk content, then hashes its exact UTF-8 bytes. Provider vectors are validated, normalized, rounded to float32, and stored separately from authored Markdown.
status: active
tags:
  - tribal
  - indexing
  - vectors
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
      symbols: [format_document_input, input_hash, count_tokens, normalize_vector, DeterministicProvider, OpenAIProvider]
  - type: code
    locator: src/tribal/chunking.py
    context: tribal-source
    details:
      symbols: [chunk_document, CHUNKER_VERSION, TARGET_BYTES]
  - type: code
    locator: src/tribal/storage.py
    context: tribal-source
    details:
      symbols: [DEFAULT_PROFILE_CONFIGURATION, ensure_profile]
  - type: code
    locator: src/tribal/migrations/001_content.sql
    context: tribal-source
    details:
      symbols: [chunk_embeddings]
  - type: test
    locator: tests/test_embeddings_contract.py
    context: tribal-source
    details:
      outcome: not-run-code-inspection
      symbols: [test_document_wrapper_and_sha256_are_exact_utf8, test_normalization_uses_float64_then_exact_float32_round_trip, test_openai_adapter_configures_timeout_retry_policy_and_exact_request]
---

# Embedding Inputs and Vectors

The chunker preserves a contiguous source slice as each chunk's `content`; its `heading_path` is separate metadata. `format_document_input(title, heading_path, content)` creates the exact provider string. The overview in [[Home]] locates this derivation within Tribal's storage and retrieval flow:

```text
Title: <title>
Headings: <compact JSON array of headings>

<complete chunk content>
```

The headings array uses compact JSON separators and retains Unicode rather than escaping it. The source passage is appended as-is: no trimming, truncation, or inserted chunk delimiter occurs. `input_hash` is SHA-256 over the UTF-8 bytes of the complete formatted string, including all newlines. Thus a title, heading path, content byte, or trailing newline change produces a different identity. This wrapper is separate from the source-preserving chunks described in [[Authoring/Source Preserving Chunks]] and from the authors' Markdown format in [[Authoring/Markdown Contract]].

Before calling a provider, the worker counts tokens for this complete wrapped input using the profile's configured `tiktoken` encoding (`cl100k_base` by default); literal special-token-looking text is counted as ordinary input. If the count exceeds the profile limit, the job becomes `oversized` with `W_EMBEDDING_INPUT_TOO_LARGE`. Tribal preserves the source and does not silently truncate the embedding input. The default OpenAI profile limit is 8,192, which `ensure_profile` also enforces as the maximum supported limit for the two configured `text-embedding-3-*` model identifiers. Chunking has a separate 4,096-byte soft target and can preserve an indivisible oversized block, so a valid chunk can still exceed a model token limit.

`OpenAIProvider` sends one complete string with the selected model and dimensions, requests float output, and configures a 30-second timeout with SDK retries disabled. `DeterministicProvider` derives repeatable vectors from the model identity, dimensions, and exact input using SHAKE-256. It supports offline pipeline behavior but explicitly makes no semantic-quality claim. Neither adapter establishes live provider availability or retrieval quality.

`normalize_vector` requires the expected dimension count and finite, nonzero values. It scales and L2-normalizes in Python float precision, then packs and unpacks little-endian IEEE float32 values; storage writes those exact rounded components to the native vector column and checks the round trip. This matches the profile's `l2-float32-v1` normalization identifier. The profile's cosine distance and compatible query path are covered in [[Indexing/Embedding Profiles]] and [[Retrieval/Search and Ranking]].

Vectors are derived database data. They are keyed by chunk and profile and store the input hash; they do not belong in authored notes or vault exports. Reuse is permitted only when the candidate belongs to the same knowledge base and has the same profile, hash, and dimensions. An equal vector width without the same profile and exact input is not sufficient. See [[Storage/Publication and Revisions]] for how content revisions replace source chunks while jobs retain their original chunk identity.

The cited contract tests describe exact formatting, hashing, vector conversion, and SDK configuration. They were read as source evidence, not run for this documentation snapshot.
