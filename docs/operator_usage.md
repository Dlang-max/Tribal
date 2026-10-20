# Publish and retrieve Tribal knowledge

Tribal validates Markdown locally, previews source chunks, publishes a selected batch to MySQL, and indexes it for search. The [implementation contracts](implementation_contracts.md) describe the Python APIs and result fields; [parser usage](parser_usage.md) covers standalone validation. Commands below describe the operator interface. Component and external-service verification must be reported separately from command availability.

## Install and configure

Use Python 3.12 or later. From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps -e .
```

The runtime lock targets CPython 3.12 on Linux. Test tools are separate: `python -m pip install -e '.[test]'`. `tiktoken` may need a network connection on its first use to populate its encoding cache.

MySQL 9.7 Community must be running with an existing empty database and a user allowed to apply the migrations and read/write its tables. Configure the CLI through environment variables:

| Variable | Meaning | Default |
|---|---|---|
| `TRIBAL_DB_HOST` | MySQL host | `127.0.0.1` |
| `TRIBAL_DB_PORT` | MySQL TCP port | `3306` |
| `TRIBAL_DB_USER` | MySQL user | Required |
| `TRIBAL_DB_PASSWORD` | MySQL password | Empty string |
| `TRIBAL_DB_NAME` | Existing database | `tribal` |
| `OPENAI_API_KEY` | OpenAI credential for workers and new semantic/hybrid searches | Required for those operations |

Use your shell or secret manager to set credentials. Keep them outside tracked files. Validation, chunk preview, lexical search, and revision/context reads do not need OpenAI credentials. Only database commands read the database configuration.

## Initialize a knowledge base

```bash
tribal db migrate --json
tribal kb ensure research --name 'Research notes'
tribal domain ensure botany --knowledge-base research --name Botany
tribal profile ensure --json
```

Record the returned `profile.id` UUID. Activate it on the empty knowledge base:

```bash
tribal profile activate "$PROFILE_ID" --knowledge-base research
```

Registry commands are idempotent for matching configuration. Profiles are immutable: changing model, dimensions, wrapper, tokenizer, normalization, or limits requires a distinct profile key. The default profile uses OpenAI `text-embedding-3-small`, 1,536 dimensions, cosine similarity, and the frozen title/headings wrapper.

`db migrate` applies executable versioned migrations and checks the stored checksums. Use it before other database operations when installing or upgrading. Do not edit an already applied migration: resolve checksum errors against the original installation and restore the matching migration files before retrying. This release targets fresh development databases; migration of an undocumented external deployment is outside its scope.

## Validate, preview, and ingest

```bash
tribal validate /path/to/vault --knowledge-base research --domain botany --json
tribal chunk /path/to/vault/Observation.md --json
tribal ingest /path/to/vault --knowledge-base research --author-id researcher --json
```

`validate`, `chunk`, and `ingest` accept one note or a vault directory. Directory selection recurses through lowercase `.md` files, excludes Git/Obsidian/staging and virtual environment directories, and does not follow directory symlinks. It never probes Git. Select the vault itself: project documentation is ordinary Markdown and generally lacks Tribal metadata.

A file preview returns the `chunk_document` result. A directory preview returns `valid`, `path`, collected `diagnostics`, path-keyed `documents` containing those results, and a `summary` with `files`, `chunks`, `errors`, and `warnings`. Preview does not allocate stored chunk IDs. `--revision-id` only labels the preview; it does not persist or prove a revision exists.

Ingestion is atomic for the selected batch. Missing files never imply deletion. The service validates knowledge-base/domain assignments, current heads, links, and the complete planned namespace before publishing. An accepted revision remains stored even if embedding generation later fails. An unchanged import preserves its authored revision and chunks; derived repairs are explicit commands.

When editing an existing note, use the current revision UUID as its `tribal_base_revision` transport metadata, following the [Markdown revision contract](tribal_markdown_spec.md). The token is removed from canonical stored Markdown. A stale authored edit returns `E_CONFLICT`; reload the current note, reconcile the edit, and retry. Ordinary ingestion does not restore a soft-deleted document.

## Run indexing and repair work

```bash
tribal index status --knowledge-base research --json
tribal index worker --knowledge-base research --once --json
tribal index worker --knowledge-base research
```

`--once` makes exactly one claim attempt and returns its job result; an empty queue reports `state: idle`. The continuous worker processes independent claims until interrupted. It sleeps between idle/delayed-retry polls outside database transactions. With `--json`, continuous mode emits one compact JSON object per line; once mode emits one normal JSON envelope. A worker result with `state: failed` describes a durable job outcome; inspect the queue/status even when the worker invocation itself succeeds.

The worker uses 30-second provider requests, a 120-second claim deadline, and at most three attempts. Transient retries are scheduled durably. Expired/replaced workers cannot publish into a newer claim or attach vectors to replacement chunks. Accepted content and lexical retrieval remain available while embeddings are pending.

Status reports `total`, `embedded`, `pending`, `oversized`, `failed`, and `ready`. To repair missing work or retry terminal provider failures:

```bash
tribal index backfill --knowledge-base research --json
tribal index retry --knowledge-base research --json
```

Backfill fills missing jobs for current nondeleted chunks, with compatible reuse restricted to the same knowledge base. Retry resets eligible `failed` jobs; it does not retry `oversized`, `discarded`, or successful jobs. Oversized input is preserved without truncation. Inspect source/model limits and deliberately select a different profile or authored structure if needed.

Explicit rechunking replaces the complete selected revision's chunk set with fresh IDs without creating an authored revision:

```bash
tribal rechunk "$DOCUMENT_ID" --knowledge-base research --revision-id "$REVISION_ID" --json
```

Ordinary edits retain historical revisions, chunks, and vectors. Rechunking explicitly replaces derived chunks of the selected revision, discards stale jobs, and invalidates affected search continuations. Historical pruning is deferred.

For a model migration, create a profile under a new key with a complete explicit JSON configuration, then backfill and inspect it before activation:

```bash
tribal profile ensure --key replacement-profile --model "$MODEL" --dimensions "$DIMENSIONS" \
  --configuration "$PROFILE_CONFIGURATION" --json
tribal index backfill --knowledge-base research --profile-id "$NEW_PROFILE_ID" --json
tribal index status --knowledge-base research --profile-id "$NEW_PROFILE_ID" --json
tribal profile activate "$NEW_PROFILE_ID" --knowledge-base research --json
```

Activation normally requires complete coverage. `--allow-partial` explicitly accepts gaps and returns `W_INDEXING_PARTIAL` with coverage information. Semantic search only uses the knowledge base's active profile.

## Search and read source

```bash
tribal search 'seed germination' --knowledge-base research --json
tribal search '芽' --knowledge-base research --mode lexical --lexical-mode literal --json
tribal search 'seed germination' --knowledge-base research --mode hybrid --domain botany --limit 20 --json
```

Semantic is the default. Lexical uses full-text ranking and falls back to a case-sensitive whole-query substring when no eligible full-text hits exist. Explicit literal mode treats `%` and `_` as ordinary characters. Hybrid combines the complete semantic and lexical rankings using equal-weight reciprocal-rank fusion. Semantic provider failures are reported rather than changing search mode.

Search defaults to current revisions of nondeleted documents with status `active`. Repeat `--domain` or `--status` to select filters; `--include-deleted` explicitly includes deleted documents. A page contains at most 100 hits (default 20). Results include revision/source identities, verification metadata, declared contexts/scope/evidence, indexing coverage, and `applicability: unknown`; these fields do not establish that a claim applies to a particular situation.

Continue by repeating the exact query, requested modes, and filters with the returned `next_cursor`:

```bash
tribal search 'seed germination' --knowledge-base research --cursor "$NEXT_CURSOR" --json
```

Page size may change. A continuation reuses the retained ranking/vector and does not need another provider request. Sessions expire after 15 minutes or after knowledge/indexing/profile changes. `E_CURSOR_EXPIRED` means start a fresh search; `E_CURSOR_INVALID` means correct the cursor or restore the original parameters.

Read a complete canonical document, an exact byte slice, or complete source chunks around a hit:

```bash
tribal read "$DOCUMENT_ID" --knowledge-base research --revision-id "$REVISION_ID" --json
tribal read "$DOCUMENT_ID" --knowledge-base research --revision-id "$REVISION_ID" \
  --start-byte "$START_BYTE" --end-byte "$END_BYTE" --json
tribal context "$DOCUMENT_ID" "$REVISION_ID" "$CHUNK_ID" --knowledge-base research --json
```

Byte ranges are half-open UTF-8 offsets in canonical Markdown, including frontmatter. Supply both endpoints at UTF-8 boundaries. Context uses the matched revision and precise containing section, prioritizes complete same-section Mermaid chunks, then neighbors, and returns selected ranges in source order. The default source budget is 65,536 bytes; `--budget-bytes` overrides it. Omitted chunks/bytes and completeness are disclosed. `E_CONTEXT_BUDGET_EXCEEDED` means the complete matched chunk cannot fit; raise the budget or read the document explicitly. A diagram in another section requires an explicit document read.

Exact semantic ranking scans eligible stored float32 vectors in the application. The API's default capacity guard is 100,000 eligible candidates; this is a configured rejection bound, not a measured performance guarantee. `E_SEARCH_CAPACITY` returns no partial page. Record corpus size, vector dimensions, host, and timings before choosing a deployment limit. Live OpenAI verification and Docker/MySQL acceptance results must be reported separately from deterministic-provider checks.

## Diagnostics and exit codes

Every leaf command accepts `--json`. JSON preserves the library envelope; operational failures contain `ok: false` and parser-shaped diagnostics. Text includes diagnostic codes, fields, expected/actual values, and recovery hints. Syntax errors from argument parsing use the normal command usage message.

| Exit | Meaning |
|---|---|
| `0` | Operation succeeded, including warnings and durable worker outcomes |
| `1` | Authored Markdown/namespace validation rejected the batch |
| `2` | Usage, filesystem, configuration, or operational failure |

For `E_DATABASE`, check connectivity, credentials, schema selection, and migrations; content transactions roll back. For `E_ASSIGNMENT`, register or correct the note's declared knowledge base/domain. For `E_PROFILE_INCOMPLETE`, finish indexing or deliberately activate with `--allow-partial`. Provider and database diagnostics omit credentials and raw provider response bodies. Full command syntax is available through `tribal --help` and each command's `--help`.
