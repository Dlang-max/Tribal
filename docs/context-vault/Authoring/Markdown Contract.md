---
schema_version: 1
id: 0ed97aa6-b2cc-4588-868d-435a15d6236e
title: Markdown Contract
knowledge_base: tribal
domain: authoring
kind: reference
summary: Defines Tribal's authored Markdown envelope, metadata rules, and preservation boundaries. Use it to prepare files that remain readable as ordinary Markdown and stable under import.
status: active
tags:
  - tribal
  - authoring
  - markdown
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
    locator: src/tribal/parser.py
    context: tribal-source
    details:
      symbols: [_document, _frontmatter, _metadata]
  - type: file
    context: tribal-source
    locator: docs/tribal_markdown_spec.md
    details:
      section: File envelope and canonical representation
---

# Markdown Contract

Tribal documents are ordinary UTF-8 Markdown files with a strict YAML envelope. The contract keeps stable identity and queryable metadata in frontmatter while preserving the authored file as source. This note summarizes the implementation and normative requirements in `docs/tribal_markdown_spec.md`; for link behavior see [[Authoring/Parser and Link Resolution]], and for retrieval slices see [[Authoring/Source Preserving Chunks]]. The broader architecture is in [[Home]] and changes to storage revisions are covered by [[Storage/Publication and Revisions]].

## Envelope and canonical bytes

The file starts with `---`, contains a YAML 1.2 mapping, closes frontmatter with a standalone `---`, and has a nonempty body. The parser accepts text or UTF-8 bytes through `validate_document(content, *, path='note.md', knowledge_base=None, domains=None)` and normalizes CRLF and CR to LF, adding a final LF if absent. It reports this as `W_NORMALIZED`. A BOM, NUL, invalid UTF-8, missing required structure, or empty body is an error. Apart from line endings and the final newline, it does not reformat YAML, reorder metadata, or rewrite Markdown.

The canonical authored file includes frontmatter and body but excludes the generated `tribal_base_revision` transport property when it is valid. `content_hash` is SHA-256 of those exact canonical UTF-8 bytes. The transport entry is constrained to a one-line UUID scalar of at most 256 bytes. The complete canonical file is capped at 8 MiB; summary and locator values have their own byte limits. Limits reject input before persistence in the service path; they do not authorize truncation.

## Metadata and identity

Required fields are integer `schema_version: 1`, a lowercase non-nil UUID `id`, nonblank single-line `title`, `knowledge_base`, `domain`, a supported `kind`, and plain-text `summary`. The parser checks strict types instead of coercing values: for example, quoted `"1"` is not the integer schema version. Optional values have interpreted defaults (`status: active`, empty `tags`, `contexts`, `scope`, and `sources`, and `verification_state: unverified`); defaults are not inserted into the source. Tags are lists and should use portable lowercase names.

The `id` remains the document's identity when title, path, or domain changes. Vault validation rejects duplicate IDs and paths that collide under Unicode NFC plus full case folding, while preserving original path spelling. A vault has one configured knowledge base; directory names do not assign domains. Unknown top-level fields are preserved with a warning; `x_` fields are intentional extensions and unknown `tribal_` fields are reserved and rejected. `contexts` declare working resources, `scope` describes applicability, and `sources` record evidence. They are not interchangeable: linking another note does not inherit its context. See [[Operations/Vault Import Workflow]] for import boundaries.

Verified state is a scoped assertion supplied by an author, not evidence that software proved a claim. A `verified` document must include timestamp, verifier, and at least one source. This vault records a code-reading snapshot with `verification_state: unverified`; it makes no assertion about Obsidian GUI rendering or live service behavior.

## Preserved body content

The parser structurally recognizes CommonMark/GFM blocks and Tribal wikilinks. Code, tables, Mermaid, blockquotes, HTML, comments, math, and selected Obsidian extensions are preserved as source. Link-looking text inside code, embeds, or opaque extension regions is not speculatively turned into graph relationships. Unsupported semantics may produce warnings; source remains available. Code blocks are never executed. Attachments and recursive embeds are not copied by the core interchange profile.

The spec and current parser are the authorities for exact supported syntax. Ordinary Markdown remains the portable baseline, with explicit links outside opaque regions when a graph edge matters. Embedding and retrieval derive data from canonical content as described in [[Indexing/Embedding Inputs and Vectors]].
