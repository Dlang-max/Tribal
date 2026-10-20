---
schema_version: 1
id: 59142dfc-9ac8-4e5d-bace-db70cbdffb04
title: Search and Read Knowledge
knowledge_base: tribal
domain: cli
kind: procedure
summary: This procedure searches current Tribal knowledge using semantic, lexical, or hybrid ranking, then follows a hit to canonical source. It explains pagination replay, provider requirements, and the revision and byte identities needed for precise reads.
status: active
tags:
  - tribal
  - cli
  - search
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
    locator: src/tribal/cli.py
    context: tribal-source
    details:
      symbols: [_run_operation, _provider]
  - type: code
    locator: src/tribal/retrieval.py
    context: tribal-source
    details:
      symbols: [search, read_document, read_context]
---

# Search and Read Knowledge

Search yields ranked chunk hits; `read` returns exact canonical Markdown and `context` gathers whole nearby chunks from a selected section. Start with [[Home]] for the vault map. Ranking details are in [[Retrieval/Search and Ranking]], and [[Retrieval/Search Sessions and Cursors]] explains cursor lifecycle.

## Choose a search mode

```bash
tribal search 'seed germination' --knowledge-base research --json
tribal search '芽' --knowledge-base research --mode lexical --lexical-mode literal --json
tribal search 'seed germination' --knowledge-base research --mode hybrid --domain botany --limit 20 --json
```

The default is semantic search, which embeds the original query with the active profile and requires `OPENAI_API_KEY`. Lexical search uses database full-text ranking by default and does not require provider credentials. Literal mode searches the complete query as a case-sensitive substring, treating SQL `%` and `_` as ordinary characters. Hybrid combines complete semantic and lexical rankings. Filters default to current revisions, nondeleted documents, and `active` status. You can repeat `--domain` and `--status` to select multiple keys or statuses; `--include-deleted` expands eligibility. A page defaults to 20 hits and accepts 1–100.

Hits include `document_id`, `revision_id`, `chunk_id`, `start_byte`, `end_byte`, `path`, `title`, `content`, scores, and source metadata. The source metadata can include domain, verification, contexts, scope, and evidence; `applicability: unknown` is an explicit reminder that a result does not prove the claim applies to your situation.

## Continue a result set

If the first response has a non-null `next_cursor`, save it. Repeat the exact query and all search parameters; change only `--limit` if useful:

```bash
NEXT_CURSOR='paste-next_cursor-from-JSON'
tribal search 'seed germination' --knowledge-base research --mode hybrid \
  --domain botany --limit 50 --cursor "$NEXT_CURSOR" --json
```

The cursor belongs to a stored ranking session and normally avoids a second provider call. It expires after 15 minutes or when knowledge, indexing, or active-profile state changes. Changed query/filter/mode parameters produce `E_CURSOR_INVALID`; an expired or invalidated session produces `E_CURSOR_EXPIRED`. Start a fresh search when that happens. The session is bound to its knowledge base. See [[Indexing/Durable Embedding Worker]] for indexing changes that can invalidate a continuation.

## Read the source behind a hit

Use the hit's document and revision IDs to retrieve its pinned revision. Omitting `--revision-id` instead reads the current revision, which might have changed since the hit was produced.

```bash
DOCUMENT_ID='paste-document_id-from-hit'
REVISION_ID='paste-revision_id-from-hit'
CHUNK_ID='paste-chunk_id-from-hit'
tribal read "$DOCUMENT_ID" --knowledge-base research --revision-id "$REVISION_ID" --json
tribal context "$DOCUMENT_ID" "$REVISION_ID" "$CHUNK_ID" \
  --knowledge-base research --budget-bytes 65536 --json
```

The complete `read` result's `content` is exact canonical Markdown, including frontmatter. `--start-byte` and `--end-byte` request a half-open UTF-8 byte slice; supply both endpoints and use boundaries from a hit or returned chunk. A `context` response includes complete selected chunks, `used_bytes`, omitted chunk IDs/bytes, and `complete`. It starts with the matched chunk, favors Mermaid chunks in the same section, then nearby same-section chunks. It never crosses to another revision or section. If the matched chunk alone exceeds the budget, the command returns `E_CONTEXT_BUDGET_EXCEEDED`; increase `--budget-bytes` or use `read`.

For the source-range contract, see [[Retrieval/Source Reads and Context]]. To locate more content, search again with a focused phrase; for changes and base-revision capture, follow [[CLI/Edit and Repair Knowledge]].
