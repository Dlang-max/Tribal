---
schema_version: 1
id: 8a6b5b30-3535-4eac-a731-38721f277702
title: Vault Import Workflow
knowledge_base: tribal
domain: operations
kind: procedure
summary: This procedure takes a Markdown vault from local validation through publication and indexing readiness. It explains which commands are read-only previews, when a provider worker is needed, and how directory imports preserve note paths.
status: active
tags:
  - tribal
  - cli
  - import
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
      symbols: [_collect_documents, _validate, _chunk, _run_operation, _worker]
  - type: code
    locator: src/tribal/publication.py
    context: tribal-source
    details:
      symbols: [ingest_vault]
---

# Vault Import Workflow

This is a future operator procedure for publishing a vault into a Tribal knowledge base; this context vault has not been imported. Installation and database environment setup are covered in [[Operations/Installation and Configuration]]; this note starts once the CLI is available and configured. See [[Home]] for the vault map and [[Authoring/Markdown Contract]] for the required note envelope.

## Prepare the destination

Use a stable knowledge-base key and register every domain used by the vault. Run the migration once for a fresh installation or after an approved schema upgrade. Registry `ensure` commands are repeatable only when the existing name and description match.

```bash
tribal db migrate --json
tribal kb ensure research --name 'Research notes' --json
tribal domain ensure botany --knowledge-base research --name Botany --json
tribal profile ensure --json
```

`profile ensure` returns a profile object. Capture its `profile.id` from JSON and activate it for the knowledge base before ingest, so new chunks receive jobs for the selected profile:

```bash
PROFILE_ID='paste-profile-uuid-from-profile.id'
tribal profile activate "$PROFILE_ID" --knowledge-base research --json
```

The default profile is OpenAI `text-embedding-3-small` with 1,536 dimensions. Activation is allowed on an empty knowledge base. A populated knowledge base generally needs full profile coverage first; see [[Indexing/Embedding Profiles]] and [[Operations/Diagnostics and Recovery]] for profile changes and recovery.

## Select, validate, and preview

Point `VAULT` at the root folder containing only the Tribal notes intended for publication. The directory walker recursively selects lowercase `.md` files, skips Git, Obsidian, staging, and virtual-environment directories, does not follow directory symlinks, and does not invoke Git. A file-only selection is valid, but its stored path is just its basename. Passing the vault root preserves paths such as `botany/seed-trial.md`.

```bash
VAULT=/path/to/research-vault
tribal validate "$VAULT" --knowledge-base research --domain botany --json
tribal chunk "$VAULT/botany/seed-trial.md" --knowledge-base research --domain botany --json
```

`validate` checks the selected notes, metadata assignments, and links across the directory selection. `chunk` previews source-preserving chunks locally; it neither creates database rows nor allocates persistent chunk IDs. Add `--revision-id UUID` only when you want that label included in preview output. The CLI emits structured diagnostics in JSON; exit `0` means accepted (warnings may be present), `1` means content validation failed, and `2` means command, configuration, or I/O trouble. See [[Authoring/Parser and Link Resolution]] and [[Authoring/Source Preserving Chunks]] for what those checks and previews represent.

## Publish the selected vault

Ingest the root folder in one command. The publication API validates the whole selected batch against the complete namespace, writes accepted revisions and chunks atomically, and queues embedding jobs for the active profile. It does not call the embedding provider.

```bash
tribal ingest "$VAULT" --knowledge-base research --author-id researcher --change-summary 'Initial vault import' --json
```

The JSON response includes `summary.created`, `summary.updated`, `summary.unchanged`, `summary.chunks`, and `summary.jobs`. The `documents` mapping is keyed by relative vault path; each outcome includes `document_id`, `revision_id`, `action`, `path`, and `chunk_ids`. Save the document and revision UUIDs for future reads and edits. Re-importing the same content at the same path reports it unchanged. Missing files never imply deletion. A changed existing note must carry its current `tribal_base_revision`; see [[CLI/Edit and Repair Knowledge]] and [[Storage/Publication and Revisions]].

## Run indexing and wait for readiness

Run the provider worker in one terminal. It requires `OPENAI_API_KEY`; the ingest command itself does not. A separate terminal can poll status without a provider call:

```bash
# Terminal 1: keep running until readiness is true, then press Ctrl-C.
tribal index worker --knowledge-base research

# Terminal 2:
tribal index status --knowledge-base research --json
```

Status reports `total`, `embedded`, `pending`, `oversized`, `failed`, and `ready`. Stop the continuous worker when `ready` is true. For a single claim attempt, including an idle result, use `tribal index worker --knowledge-base research --once --json`. Continuous JSON mode writes one compact JSON object per line. See [[Indexing/Durable Embedding Worker]] for durable job behavior and [[CLI/Search and Read Knowledge]] for retrieval after import.
