# Markdown Chunking, Storage, and Retrieval Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` to execute this plan task by task, with the independent branches and review gates below. This document records the plan; it does not claim implementation is complete.

**Goal:** Implement validated Markdown ingestion, source-preserving chunks, revision-safe MySQL storage, OpenAI embeddings, and retrieval of complete passages and diagrams.

**Architecture:** Share the parser's structural interpretation across validation, chunking, and context retrieval. Publish authored and derived records atomically, generate embeddings through a durable worker, and expose the resulting capabilities through a Python library and operator CLI.

**Tech stack:** Python 3.12+, Docker MySQL 9.7 Community, MySQL Connector/Python, OpenAI `text-embedding-3-small` with 1,536 dimensions, and exact application-side cosine search.

**Specifications:** [Chunking strategy](../../tribal_chunking_strategy.md), [Markdown format](../../tribal_markdown_spec.md), [database schema](../../tribal_schema.md), and [existing parser API](../../parser_api.md).

**Review:** A GPT-6 Luna high subagent reviewed the preceding plan. This version incorporates the resulting clarifications to generations, worker fencing, lexical ranking, unchanged imports, and context selection.

## 1. Summary and scope

Implement the following pipeline:

**Validate Markdown → publish document revision and chunks → generate embeddings → search → retrieve revision-pinned passages and diagrams.**

Deliver a Python library and operator CLI using:

- Python 3.12 or later.
- Docker MySQL 9.7 Community.
- OpenAI `text-embedding-3-small`, 1,536 dimensions.
- Exact application-side cosine search for the pilot.
- The existing parser API and its 290 passing tests as the regression baseline.

MCP, authentication, automated admission review, rendering, external evidence connectors, and historical-data pruning remain outside this milestone.

The coordinator first freezes public interfaces, diagnostic codes, migration ownership, and representative result fixtures. Preserve the existing documentation/fixture reorganization as a separate baseline before creating implementation worktrees.

## 2. Implementation contracts

### Parser and pure chunker

- Extract a shared internal structural representation containing canonical body offsets, submitted-input location mapping, heading containment and plain-text eligibility, list-item ranges, definitions, and protected math/opaque regions.
- Keep existing validation responses compatible. Validation, chunking, and context retrieval must share structural interpretation.
- Add:

  ```python
  chunk_document(
      content,
      *,
      path="note.md",
      revision_id=None,
      knowledge_base=None,
      domains=None,
  ) -> dict
  ```

- Return validity, diagnostics, document/revision identity, content hash, policy version, and the chunk fields defined by the strategy. Preview results may omit revision identity; persisted chunks must reference an actual revision.
- Implement `tribal-structure-bytes-v1`: 4,096-byte soft target, root-heading sections, deterministic greedy packing, no overlap, intact protected blocks, and oversized-list splitting only between complete immediate items.
- Assert contiguous UTF-8 source ranges, exact source equality, and complete body reconstruction. Invalid input produces diagnostics and no chunks.

### Database and publication

Use MySQL Connector/Python, parameterized SQL, explicit transactions, and executable versioned migrations.

Implement the existing nine-table content model, adding:

- Migration tracking.
- Knowledge-base active-profile and generation fields.
- Durable embedding jobs.
- Search sessions and their ranked result records.

The storage agent owns all migrations; other agents consume the frozen repository interfaces.

Publication services provide registry/profile setup, atomic vault ingestion, revision-pinned reads, explicit rechunking, and indexing repair/backfill.

For ingestion:

- Validate the complete planned namespace, including unaffected documents and soft-deleted path reservations.
- Lock the knowledge base before document rows. Recheck expected revisions, assignments, and portable Unicode 15.1 path uniqueness using current reads.
- Commit revisions, evidence, links, chunks, current pointers, embedding jobs, and generation updates atomically.
- Refresh links from **all current sources**, including unchanged notes outside the submitted batch.
- Preserve path-only revisions and occupied-path swaps using `.tribal-staging`.
- Missing files never imply deletion; ordinary ingestion never restores a deleted note.

An unchanged canonical document and path create no authored revision and do not silently replace its chunks. Derived repair is explicit: backfill creates missing jobs; retry resets eligible failed work; rechunk replaces a complete chunk set with fresh IDs.

### Profiles, generations, and continuation sessions

Embedding profiles are global immutable configurations. Each knowledge base explicitly selects an active profile; embedding reuse is restricted to that knowledge base.

- Initial setup activates the configured profile on an empty knowledge base.
- Model migration creates a new profile and backfills current chunks.
- Activation requires complete embedding coverage by default. An explicit operator `allow_partial` option permits activation with disclosed coverage gaps.
- Profile activation runs under the knowledge-base lock.

Advance generations once per committed transaction:

| Generation | Advances when |
|---|---|
| `knowledge_generation` | Accepted document heads, authored paths, lifecycle, or domain assignments change. |
| `indexing_generation` | Chunk sets, published embeddings, active profile, or terminal indexing readiness change. |

Job claims and lease scheduling alone do not advance generations.

Search sessions retain the exact query vector, profile, mode, filters, generations, and ranked results. Cursors expire after 15 minutes or when either generation or active profile changes. Reject changed query/filter parameters rather than continuing a different search.

### Embeddings and worker fencing

Use a provider interface with a real OpenAI adapter and deterministic test adapter.

- Freeze the strategy's document-input wrapper and hash its exact UTF-8 bytes. Query input is the original query text.
- Configure the initial profile for cosine similarity and `cl100k_base` counting. Check the complete input against the documented model limit. See the [OpenAI embedding documentation](https://developers.openai.com/api/docs/guides/embeddings).
- Validate dimensions, finite values, and nonzero norm; normalize consistently and verify float32 storage round trips.
- Define job uniqueness as `(chunk_id, profile_id, input_hash)`. Retain knowledge-base identity and stale chunk identity so deleted/replaced chunks cannot redirect work.
- Use states `queued`, `running`, `succeeded`, `oversized`, `failed`, and `discarded`; delayed retries remain queued with a future `available_at`.
- Claim one job at a time with a fresh fencing token, a 120-second lease/deadline, and an incremented attempt count. Use database time.
- Set provider timeout to 30 seconds, disable nested SDK retries, and permit at most three attempts.
- Schedule transient retries durably, honoring provider retry guidance. Release claims rather than sleeping while holding locks.
- Make model calls outside transactions. Publication acquires the knowledge-base lock first, then checks claim token, state, lease/deadline, chunk existence, profile, and reconstructed input hash.
- Commit the vector and successful job state together. Expired or replaced workers cannot publish.
- Reuse compatible embeddings by exact profile/input hash; never attach results by ordinal.
- Mark permanently oversized inputs without truncation or repeated identical requests. Provider failures never roll back accepted content.

Expose pending, embedded, oversized, and failed counts, plus indexing readiness.

### Search and deterministic context retrieval

Provide semantic, lexical, and hybrid modes; semantic is the default.

Apply knowledge-base, domain, current-revision, deletion, and lifecycle filters before ranking. Return verification, declared scope, contexts, and provenance. Arbitrary scope JSON does not establish applicability: report applicability as unknown rather than inventing business-specific matching rules.

Ranking is fixed as follows:

- **Semantic:** exact cosine over eligible vectors in the active profile. Compute from persisted float32 values using float64 arithmetic.
- **Full-text lexical:** document title/summary relevance plus chunk-content relevance; document relevance contributes to each owning chunk.
- **Literal lexical:** when full-text produces no eligible hits, or literal mode is explicitly requested, match the entire query as a case-sensitive substring in title, summary, or chunk content. `%` and `_` are literal characters. Rank by the number of matching fields.
- **Hybrid:** use all eligible semantic candidates and all matching candidates from the selected lexical ranking. Apply equal-weight reciprocal-rank fusion with constant 60 and one-based ranks; absent candidates contribute zero. Do not truncate either ranking before fusion.
- Break equal scores by document UUID bytes, then chunk ordinal. Do not round scores before ranking.

Stream candidate scoring and materialize session results for stable pagination. Default to 20 hits, maximum 100. Return explicit capacity errors for incomplete scans. Semantic failures do not silently fall back to lexical search.

Use application-side cosine without requiring HeatWave's `DISTANCE()`. See [MySQL vector-function availability](https://dev.mysql.com/doc/refman/9.7/en/vector-functions.html).

For context retrieval:

- Pin document ID, revision ID, and canonical source range.
- Parse that stored revision to identify the precise containing section; duplicate headings and nullable anchors are not section identities.
- Include the complete matched chunk first.
- Then consider Mermaid-containing chunks from the same section, ordered by byte distance from the match and then source position.
- Fill remaining space with same-section neighboring chunks in that order; return selected ranges in source order.
- Default source-content budget: 64 KiB. Return whole chunks, deduplicate ranges, and disclose omissions.
- If the matched chunk cannot fit, return `E_CONTEXT_BUDGET_EXCEEDED`.
- Diagrams elsewhere in the document require an explicit document read; do not infer diagram relationships.
- Unembedded diagrams remain retrievable through document/source ranges.

Expose CLI commands for chunk preview, database setup/migrations, ingestion, rechunking, profile/backfill/retry operations, worker/status, search, document reads, and context reads. Support JSON and actionable text diagnostics.

## 3. Independent branches and review gates

Each implementation/test agent uses **GPT-6.1 Sol high** (`gpt-6.1-sol`, reasoning effort `high`), its own branch, and a separate Git worktree.

| Branch | Deliverable | Dependencies |
|---|---|---|
| `chunking/contracts` | Coordinator: baseline, interfaces, migrations contract, diagnostics, dependency lock, result fixtures. | First |
| `chunking/structure` | Shared parser structure and pure chunker. | Contracts |
| `chunking/storage` | Docker, migrations, repositories, registry/profile setup, generation primitives. | Contracts |
| `chunking/tests` | Independently authored black-box acceptance tests. | Contracts and fixtures only |
| `chunking/embeddings` | Wrapper, OpenAI adapter, durable worker, readiness, reuse and backfill. | Reviewed storage |
| `chunking/publication` | Atomic ingestion, link refresh, revision handling and rechunk publication. | Reviewed structure, storage and embedding contracts |
| `chunking/retrieval` | Ranking, sessions, revision-pinned reads and diagram context. | Reviewed structure, storage and embedding work |
| `chunking/integration` | Coordinator: CLI integration, end-to-end verification, documentation and fixes. | Reviewed components |

The requested concurrency ceiling is **10 subagents**, subject to the actual runtime-advertised limit and task dependencies. The session in which this plan was saved permits three active subagents alongside the coordinator; a higher local configuration does not override that running-session limit. Review work takes priority when a slot opens. Do not create artificial parallel tasks solely to fill available slots.

Every completed subagent task receives a fresh **GPT-6 Luna high** (`gpt-6-luna`, reasoning effort `high`) reviewer against its committed work. Blocking findings require correction and re-review before integration. Reviewers inspect committed branches without requiring additional implementation branches.

Independent test authors do not read implementation branches or receive implementation conversations. The coordinator integrates frozen tests and resolves disagreements against the contracts. Finish with a fresh whole-integration review.

## 4. Verification and acceptance

Each component follows failing tests → implementation → passing tests → review.

Required coverage includes:

- All 290 existing parser tests remain passing.
- Exact chunk reconstruction, deterministic boundaries, Unicode, transport mapping, whitespace, and the 4,096-byte boundary.
- Intact code, Mermaid, tables, math, definitions, quotes and nested list items.
- Real MySQL migrations, constraints, vector round trips, rollback, concurrent edits, stale bases, path swaps and full link refresh.
- Unchanged import leaves revisions/chunks unchanged; explicit repair safely restores missing indexing work.
- Duplicate enqueue, simultaneous claims, expired worker finishing after reclaim, retry scheduling, exhausted attempts and rechunk during a provider call.
- Profile backfill/activation and page-two rejection after document, embedding, readiness or profile changes.
- Float32-round-trip cosine ordering, exact ties, full-text fallback, literal case/`%`/`_`/CJK behavior, and complete hybrid fusion.
- Architecture retrieval returns the complete same-revision diagram; repeat with an unembedded diagram, duplicate headings, a diagram in another section, and a matched chunk exceeding the context budget.
- Non-software notes work without Git probing or inferred contexts.

Acceptance requires at least 90% statement and 85% branch coverage, passing Docker integration tests, an exact-search benchmark, and a separately reported credentialed OpenAI smoke test.

## 5. Rollout and operating defaults

- Start with a fresh development database; migration from an undocumented external deployment is excluded.
- Pin the official MySQL 9.7 Community image by resolved digest. Do not substitute MariaDB.
- Keep credentials outside committed source. Automated tests use the deterministic provider; distinguish mocked verification from live API verification.
- Preserve historical document revisions, chunks and embeddings during ordinary edits. Rechunk only the explicitly selected revision; pruning remains deferred.
- Report indexing coverage, queue failures, stale-result discards, cursor expiry and search capacity failures with safe structured diagnostics.
- Document installation, recovery, measured search limits, CLI/API contracts and migration procedures under `docs/`.
