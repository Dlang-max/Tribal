---
schema_version: 1
id: e29588be-d09f-46c7-9624-7c6cdf4720c7
title: Edit and Repair Knowledge
knowledge_base: tribal
domain: cli
kind: procedure
summary: This procedure safely authors an existing document against the revision currently stored by Tribal and describes explicit lifecycle, chunk, job, and profile repairs. It distinguishes authored revision changes from derived indexing operations.
status: active
tags:
  - tribal
  - cli
  - revisions
  - repair
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
    locator: src/tribal/publication.py
    context: tribal-source
    details:
      symbols: [ingest_vault, set_document_deleted, rechunk_revision]
  - type: code
    locator: src/tribal/embeddings.py
    context: tribal-source
    details:
      symbols: [backfill_embeddings, retry_embeddings, activate_profile]
  - type: code
    locator: src/tribal/cli.py
    context: tribal-source
    details:
      symbols: [_run_operation, _parser]
---

# Edit and Repair Knowledge

Tribal protects edits with an authored revision token and makes deletion, rechunking, and indexing repairs explicit operations. Read [[Storage/Publication and Revisions]] for revision semantics, [[Storage/Document Lifecycle]] for lifecycle behavior, and [[Home]] for the surrounding system map.

## Edit an existing note against its current revision

First read the current canonical source and record the returned `revision_id`. Add that UUID as top-level `tribal_base_revision` in the edited note's frontmatter, then ingest the vault root so its path stays stable:

```bash
tribal read "$DOCUMENT_ID" --knowledge-base research --json
# Copy revision_id from the JSON response into the edited note:
# tribal_base_revision: "<current revision UUID>"
tribal ingest /path/to/research-vault --knowledge-base research --json
```

For any changed existing document, `ingest_vault` requires the token to equal its current head. A missing token produces `E_BASE_REVISION_REQUIRED`; an older token produces `E_REVISION_CONFLICT`. Re-read the current version, reconcile the authored changes, replace the token, and resubmit. An unchanged document at the same path is a no-op even with an absent or stale token. The transport property is removed from canonical storage. Ordinary ingest does not undelete a note; use `restore`. See [[Operations/Vault Import Workflow]] for directory selection and [[Authoring/Markdown Contract]] for the document envelope.

## Delete and restore with an expected revision

Both lifecycle commands require the current authored revision UUID. Read the document first, then pass its `revision_id` as `--expected-revision`:

```bash
tribal delete "$DOCUMENT_ID" --knowledge-base research \
  --expected-revision "$REVISION_ID" --json
tribal restore "$DOCUMENT_ID" --knowledge-base research \
  --expected-revision "$REVISION_ID" --json
```

They retain revisions, chunks, and vectors. Restoration rechecks the reserved path namespace, but does not perform indexing repair. A stale expected ID returns `E_REVISION_CONFLICT`; re-read before retrying. Lifecycle changes affect current search eligibility and invalidate search continuations.

## Repair chunk sets and embedding jobs

Use rechunk only when derived chunk boundaries need explicit replacement. It defaults to the current revision; `--revision-id` targets a specific historical revision:

```bash
tribal rechunk "$DOCUMENT_ID" --knowledge-base research --revision-id "$REVISION_ID" --json
```

Rechunk creates fresh chunk IDs without creating an authored revision and queues work for the active profile. To fill missing embeddings or retry terminal failures:

```bash
tribal index backfill --knowledge-base research --json
tribal index retry --knowledge-base research --json
tribal index status --knowledge-base research --json
```

Backfill queues missing work for current nondeleted chunks, reusing a compatible stored vector when possible. Retry resets eligible `failed` jobs only; it does not reset `oversized`, `discarded`, or succeeded work. Run `tribal index worker --knowledge-base research` in a separate terminal, then poll status until `ready` or inspect `failed`/`oversized`. Worker calls require `OPENAI_API_KEY`; the other commands do not. See [[Indexing/Durable Embedding Worker]] and [[Operations/Diagnostics and Recovery]].

## Migrate an embedding profile

Profiles are immutable. Ensure the replacement profile under a new key, capture `profile.id`, backfill and inspect its coverage, then activate it:

```bash
tribal profile ensure --key replacement-profile --model "$MODEL" --dimensions "$DIMENSIONS" \
  --configuration "$PROFILE_CONFIGURATION" --json
NEW_PROFILE_ID='paste-profile.id-from-response'
tribal index backfill --knowledge-base research --profile-id "$NEW_PROFILE_ID" --json
tribal index status --knowledge-base research --profile-id "$NEW_PROFILE_ID" --json
tribal profile activate "$NEW_PROFILE_ID" --knowledge-base research --json
```

Activation requires complete coverage unless `--allow-partial` is explicitly supplied. Partial activation emits `W_INDEXING_PARTIAL`; semantic and hybrid searches use the active profile, so confirm the status output before activation. See [[Indexing/Embedding Profiles]] for the configuration fields and [[CLI/Search and Read Knowledge]] for search behavior after a profile change.
