---
schema_version: 1
id: d71df296-4702-4fef-a5ff-30477748ede6
title: Command Reference
knowledge_base: tribal
domain: cli
kind: reference
summary: This note maps the Tribal CLI command families to their actual parser syntax, defaults, and operator purpose. It gives the common output and exit-code contract while linking to focused procedures for import, retrieval, and repair.
status: active
tags:
  - tribal
  - cli
  - reference
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
      symbols: [_parser, _run_operation, main]
  - type: file
    locator: docs/operator_usage.md
    context: tribal-source
---

# Command Reference

The CLI exposes local validation and chunk preview, database-backed publishing, indexing, and retrieval. Every leaf command accepts `--json`; use `tribal --help` or a leaf's `--help` for parser-generated syntax. Installation, required environment variables, and MySQL setup live in [[Operations/Installation and Configuration]]. The vault map is [[Home]].

## Local commands

```text
tribal validate PATH [--knowledge-base KEY] [--domain KEY ...] [--json]
tribal chunk PATH [--knowledge-base KEY] [--domain KEY ...] [--revision-id UUID] [--json]
```

`PATH` is one file or a directory recursively scanned for lowercase `.md`. `validate` returns validation diagnostics; `chunk` also returns a preview layout. Neither opens the database. `--domain` may be repeated and each occurrence accepts one or more keys. Directory scans exclude `.git`, `.obsidian`, `.tribal-staging`, common virtual-environment folders, and directories containing `pyvenv.cfg`; they do not follow directory symlinks. See [[Authoring/Parser and Link Resolution]] and [[Authoring/Source Preserving Chunks]].

## Registry, publication, and lifecycle

```text
tribal db migrate [--json]
tribal kb ensure KEY --name NAME [--description TEXT] [--json]
tribal domain ensure KEY --knowledge-base KEY --name NAME [--description TEXT] [--json]
tribal ingest PATH --knowledge-base KEY [--author-type human|agent|system] [--author-id ID] [--change-summary TEXT] [--json]
tribal delete DOCUMENT_UUID --knowledge-base KEY --expected-revision UUID [--json]
tribal restore DOCUMENT_UUID --knowledge-base KEY --expected-revision UUID [--json]
tribal rechunk DOCUMENT_UUID --knowledge-base KEY [--revision-id UUID] [--json]
```

`--author-type` defaults to `human`, `--author-id` to `cli`; name and required assignment flags have no defaults. Registry ensure operations verify existing configuration. `ingest` defaults to the current author settings above, validates and atomically publishes the selected file batch, and never implies deletion for absent files. Root-directory import preserves nested paths. Delete and restore require the current authored revision as `--expected-revision`; rechunk defaults to the current revision and explicitly replaces its chunk set. See [[Operations/Vault Import Workflow]], [[Storage/Document Lifecycle]], and [[Storage/Publication and Revisions]].

## Profiles and indexing

```text
tribal profile ensure [--key KEY] [--provider openai] [--model MODEL] [--dimensions N] [--configuration JSON] [--json]
tribal profile activate PROFILE_UUID --knowledge-base KEY [--allow-partial] [--json]
tribal index backfill --knowledge-base KEY [--profile-id UUID] [--json]
tribal index retry --knowledge-base KEY [--profile-id UUID] [--json]
tribal index status --knowledge-base KEY [--profile-id UUID] [--json]
tribal index worker [--knowledge-base KEY] [--once] [--json]
```

Profile defaults are key `openai-text-embedding-3-small-v1`, provider `openai`, model `text-embedding-3-small`, and 1536 dimensions. Nondefault profiles need a JSON object configuration. `--profile-id` omitted from status, backfill, and retry selects the knowledge base's active profile. `index worker` can process all knowledge bases when `--knowledge-base` is omitted; it runs continuously unless `--once` is supplied. Worker and semantic/hybrid search require `OPENAI_API_KEY`. See [[Indexing/Embedding Profiles]] and [[Indexing/Durable Embedding Worker]].

## Retrieval

```text
tribal search QUERY --knowledge-base KEY [--mode semantic|lexical|hybrid] [--lexical-mode fulltext|literal] [--domain KEY ...] [--status active|superseded|archived ...] [--include-deleted] [--limit N] [--cursor TOKEN] [--json]
tribal read DOCUMENT_UUID --knowledge-base KEY [--revision-id UUID] [--start-byte N --end-byte N] [--json]
tribal context DOCUMENT_UUID REVISION_UUID CHUNK_ID --knowledge-base KEY [--budget-bytes N] [--json]
```

Search defaults to semantic mode, full-text lexical mode, active status, nondeleted documents, and 20 hits; limit is 1–100. Repeated domain/status options filter eligibility. Literal lexical matching treats `%` and `_` literally. A continuation cursor accepts a changed page size but requires the same query, mode, lexical mode, domain/status filters, deleted setting, and knowledge base. New semantic/hybrid searches need provider credentials; lexical search and reads do not. `read` defaults to the current revision and complete canonical source. Byte endpoints must be supplied together and must be UTF-8 boundaries. `context` defaults to a 65,536-byte source budget and returns complete chunks. Focused guidance: [[CLI/Search and Read Knowledge]], [[Retrieval/Search and Ranking]], and [[Retrieval/Source Reads and Context]].

## Output and exit codes

JSON output preserves the operation envelope and diagnostics. Successful results may still contain warnings. Exit `0` is success, including warnings and durable worker outcomes; exit `1` is an authored Markdown or namespace validation failure; exit `2` is usage, I/O, configuration, or operational failure. Parser syntax errors display usage. For installation and testing evidence, see [[Testing/Validation and Benchmarks]].
