---
schema_version: 1
id: "a64fafa5-fe86-4db9-bf38-1d8e6e6d58b5"
title: "Tribal Context Vault"
knowledge_base: tribal
domain: architecture
kind: overview
summary: "A linked guide to Tribal architecture, source contracts, and practical CLI workflows, scoped to the first implementation."
status: active
tags: [tribal, architecture, context-vault]
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
    locator: docs/implementation_contracts.md
    context: tribal-source
  - type: file
    locator: docs/validation_report.md
    context: tribal-source
  - type: code
    locator: src/tribal/cli.py
    context: tribal-source
---

# Tribal Context Vault

This vault explains how Tribal's first implementation works and how to operate its CLI. Start with [[Architecture/System Map]] for the system, or [[Operations/Vault Import Workflow]] to publish knowledge later. These are ordinary Markdown files: opening the vault does not import notes, create jobs, or call an embedding provider.

## Open in Obsidian

Use Obsidian's **Open folder as vault** action and select `docs/context-vault` inside the Tribal checkout. Open this `Home` note, then open the built-in **Graph view** to see the notes and their relationships. Open a note's local graph to explore nearby linked notes. The folder uses visible wikilinks, unique filenames, and ordinary Markdown; it requires no community plugins or database connection. Mermaid diagrams supplement the prose, while wikilinks provide the graph edges.

Open this folder itself as the vault root. Opening the entire repository would include ordinary project documents and acceptance fixtures outside this curated collection. Folder names organize topics; each note's `domain` frontmatter supplies its Tribal classification.

## Read by goal

- **Understand the system:** [[Architecture/System Map]], [[Storage/Publication and Revisions]], and [[Indexing/Durable Embedding Worker]].
- **Write valid knowledge:** [[Authoring/Markdown Contract]], [[Authoring/Parser and Link Resolution]], and [[Authoring/Source Preserving Chunks]].
- **Understand persistence:** [[Storage/Database and Migrations]] and [[Storage/Document Lifecycle]].
- **Understand indexing:** [[Indexing/Embedding Profiles]] and [[Indexing/Embedding Inputs and Vectors]].
- **Understand retrieval:** [[Retrieval/Search and Ranking]], [[Retrieval/Search Sessions and Cursors]], and [[Retrieval/Source Reads and Context]].
- **Use the CLI:** [[Operations/Installation and Configuration]], [[Operations/Vault Import Workflow]], [[CLI/Command Reference]], [[CLI/Search and Read Knowledge]], and [[CLI/Edit and Repair Knowledge]].
- **Troubleshoot and check evidence:** [[Operations/Diagnostics and Recovery]] and [[Testing/Validation and Benchmarks]].
- **Keep this collection useful:** [[Operations/Maintaining This Vault]].

## Scope and evidence

The notes describe source snapshot `245e7c3ccc19aaa8022c749d805a53f7560cf72e` on `main`. Their frontmatter pins an explicit local Git context and lists source files or inspected tests. Code-reading notes remain `unverified`: machine-valid metadata and peer review do not independently prove every assertion or universal applicability. Historical acceptance and performance results are identified as recorded results, with their original conditions.

Tribal validates, chunks, stores, indexes, and retrieves knowledge; it does not automatically synchronize Obsidian edits, prove claims, or consolidate findings. Live OpenAI behavior was not exercised for this collection. Obsidian GUI behavior has not been manually tested here; the vault uses the shared file and link conventions rather than a custom rendering integration.

## Files only for now

This collection has not been added to the Tribal database. The command examples are instructions for a future operator run. Local validation and chunk preview need no database. If you later choose to import this vault, use knowledge-base key `tribal` and register its declared domains: `architecture`, `authoring`, `storage`, `indexing`, `retrieval`, `operations`, `testing`, and `cli`. See [[Operations/Maintaining This Vault]] before changing IDs, moving notes, or importing later edits.
