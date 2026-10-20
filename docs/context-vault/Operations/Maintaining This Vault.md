---
schema_version: 1
id: "01c08506-67c3-4355-959f-011eedd18575"
title: "Maintaining This Vault"
knowledge_base: tribal
domain: operations
kind: procedure
summary: "How to edit, validate, and navigate this context vault while preserving evidence, identities, and compatibility."
status: active
tags: [tribal, operations, context-vault]
verification_state: unverified
contexts:
  - key: tribal-source
    type: git_repository
    locator: "/home/daniel-lang/Desktop/Tribal"
    details:
      branch: main
      commit: "245e7c3ccc19aaa8022c749d805a53f7560cf72e"
scope:
  source_snapshot: "245e7c3ccc19aaa8022c749d805a53f7560cf72e"
sources:
  - type: file
    locator: docs/tribal_markdown_spec.md
    context: tribal-source
  - type: code
    locator: src/tribal/parser.py
    context: tribal-source
  - type: code
    locator: src/tribal/cli.py
    context: tribal-source
  - type: code
    locator: src/tribal/publication.py
    context: tribal-source
---

# Maintaining This Vault

Keep this collection as a small map of implementation behavior and practical workflows. Each note is both an Obsidian document and a Tribal v1 knowledge document. [[Home]] is the navigation hub; [[Architecture/System Map]] connects the modules; [[CLI/Command Reference]] provides operator entry points.

## Preserve identity and evidence

Keep the existing `id` when editing, renaming, or moving a note. Generate a new UUID only for a new independent note. Keep `schema_version: 1`, `knowledge_base: tribal`, and the appropriate registered `domain`. Frontmatter supplies meaning; folders do not implicitly choose domains. Preserve lowercase `.md` extensions, UTF-8, LF endings, and the final newline.

Update the explicit source context and source references when new implementation behavior is documented. The current source snapshot is `245e7c3ccc19aaa8022c749d805a53f7560cf72e`; a later Git revision does not automatically make every statement false. Re-read the affected symbols and update claims, scope, and evidence deliberately. Do not mark a note `verified` merely because the parser accepted it. [[Authoring/Markdown Contract]] explains the verification contract.

## Keep the graph useful

Use visible ordinary wikilinks with exact vault-root-relative paths, for example the existing link to [[Authoring/Parser and Link Resolution]]. Connect a new note to its prerequisites and consumers, and add it to the relevant navigation path in [[Home]]. Names and aliases are presentation; the UUID remains identity. Avoid duplicate filename stems and ambiguous heading references.

A graph edge should explain a real relationship. A Mermaid edge only draws a diagram; it does not create a Tribal knowledge link. Keep required explanations and evidence in prose rather than hidden comments, embeds, or plugin queries. This vault needs no community plugins, attachments, or external rendering service.

## Validate files without a database

From the repository root, with the installed CLI available:

```bash
tribal validate docs/context-vault --knowledge-base tribal --json
tribal chunk docs/context-vault --knowledge-base tribal --json
```

Both commands inspect files locally. Validation checks metadata, identity/path collisions, and internal links across the selected collection. Chunk preview checks how accepted canonical source becomes exact UTF-8 ranges; it does not allocate stored IDs or enqueue jobs. Mermaid source is preserved, but its diagram syntax can remain explicitly unchecked. A source citation being well formed does not mean the validator contacted its resource or verified the claim.

[[Authoring/Source Preserving Chunks]] describes the range invariants. [[Testing/Validation and Benchmarks]] distinguishes these local checks from database-backed acceptance and opt-in live provider checks. No new test files are required to maintain prose.

## Import only when explicitly chosen

The collection is currently files only. Opening it in Obsidian does not publish it, and editing a file does not automatically update MySQL. Future ingestion requires database setup, knowledge-base key `tribal`, and the eight domain keys listed in [[Home]]. An active embedding profile is needed to queue indexing work. Follow [[Operations/Vault Import Workflow]] only when database publication is intended.

After a note has been imported, later authored edits require the current database revision UUID in the `tribal_base_revision` transport property. Keep that token distinct from the stable document `id` and the external Git source commit. Tribal removes the transport property from canonical stored Markdown. The CLI does not silently write a fresh token into the local file. [[CLI/Edit and Repair Knowledge]] explains how to read the current revision and prepare an edit; [[Storage/Publication and Revisions]] explains stale-edit conflicts.

## Review changes in context

Read linked notes when changing cross-module behavior. Profile changes may affect [[Indexing/Embedding Profiles]] and [[Retrieval/Search Sessions and Cursors]]; lifecycle or rechunking changes may affect [[Storage/Document Lifecycle]] and [[Retrieval/Source Reads and Context]]. Keep command examples aligned with the real CLI parser. [[Operations/Diagnostics and Recovery]] explains the distinction between authored validation errors, operational failures, and durable worker outcomes.
