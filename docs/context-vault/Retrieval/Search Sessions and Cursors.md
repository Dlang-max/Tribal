---
schema_version: 1
id: 5f643fd0-43bd-4bac-b0c3-6bfc641bc773
title: Search Sessions and Cursors
knowledge_base: tribal
domain: retrieval
kind: reference
summary: A successful search stores its complete ordered ranking in an expiring session, so later pages continue the same snapshot. Cursors bind to the original request, knowledge base, and indexing generations and fail clearly when those identities change.
status: active
tags:
  - tribal
  - retrieval
  - pagination
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
    locator: src/tribal/retrieval.py
    context: tribal-source
    details:
      symbols: [_cursor, _decode_cursor, _page, _session, search]
  - type: code
    locator: tests/test_retrieval_contract.py
    context: tribal-source
    details:
      symbols: [test_continuation_reuses_materialized_ranking_and_query_vector_without_provider, test_cursor_rejects_changed_search_identity, test_cursor_expires_after_each_material_change, test_cursor_cannot_continue_in_a_different_knowledge_base]
      outcome: not-run-code-inspection
---

# Search Sessions and Cursors

## Session behavior

The first call to `tribal.retrieval.search` scans and ranks the full eligible candidate set, then stores the request and every ranked result in `search_sessions` and `search_session_results`. Result rows are inserted in batches of 1,000; this is a write to Tribal's search-session tables, not to authored documents. The first response includes a page of up to 100 hits, generation values, the active profile, indexing status, `expires_at`, and `next_cursor` when more results remain. Later pages read these stored results, so they neither rerun ranking nor call the embedding provider again.

A cursor is URL-safe base64 encoding of the session UUID and next rank. It is an opaque continuation token for callers. It expires 15 minutes after session creation; paging does not extend the expiry. Malformed tokens or absent sessions produce `E_CURSOR_INVALID`. A valid session that has expired or whose snapshot changed produces `E_CURSOR_EXPIRED`, and the caller should start a fresh search.

## Request identity and invalidation

Continuation must use the same knowledge base and original query, mode, requested lexical mode, normalized domain and status filters, and `include_deleted` value. Filter order and duplicates are normalized, so `domains=["research", "research"]` matches `domains=["research"]`. A changed identity raises `E_CURSOR_INVALID`. The page `limit` may change between calls; it controls how many already-ranked rows are returned, rather than which search was run.

A cursor cannot cross knowledge bases. The stored request also captures the knowledge generation, indexing generation, and active profile. A document publication or lifecycle change, rechunking, embedding/readiness mutation, profile change, or TTL expiry invalidates continuation. Before publishing the initial session, search rechecks the captured generations under a knowledge-base lock; a concurrent mutation yields no session/page. This keeps each cursor tied to a complete, stable ranking snapshot.

```mermaid
sequenceDiagram
    participant Caller
    participant Search
    participant Store
    Caller->>Search: search(query, filters)
    Search->>Store: scan, rank, store full result order
    Search-->>Caller: first page + next_cursor
    Caller->>Search: same request + cursor
    Search->>Store: validate identity, generations, expiry; read stored ranks
    Search-->>Caller: next page + next_cursor or null
```

The stored ranking includes score components and pinned document/revision/chunk identities. Results still need a valid current generation at page time; historical source retrieval is a separate revision-pinned read described in [[Retrieval/Source Reads and Context]]. See [[Home]] for the vault map, [[Retrieval/Search and Ranking]] for score construction, [[Storage/Database and Migrations]] for persisted search-session storage, and [[CLI/Search and Read Knowledge]] for cursor flags.

## Practical call pattern

```python
from tribal.retrieval import search

page = search(db, "germination", knowledge_base="field-notes", mode="lexical", limit=20)
if page["next_cursor"]:
    next_page = search(
        db, "germination", knowledge_base="field-notes", mode="lexical",
        limit=50, cursor=page["next_cursor"],
    )
```

Reuse the original query and filters on continuation. Persisting a cursor for later user sessions is unreliable because it has a short server-side lifetime and can be invalidated by ordinary corpus or index changes.
