---
schema_version: 1
id: e8db30b8-0536-40e4-bf04-77c5f4473744
title: Source Preserving Chunks
knowledge_base: tribal
domain: authoring
kind: overview
summary: Describes the deterministic chunk preview built from canonical Markdown body bytes. Chunk ranges cover the source exactly while preserving structural units and reporting units larger than the soft target.
status: active
tags:
  - tribal
  - chunking
  - source-preservation
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
    locator: src/tribal/chunking.py
    context: tribal-source
    details:
      symbols: [chunk_document, TARGET_BYTES, CHUNKER_VERSION]
  - type: code
    locator: src/tribal/structure.py
    context: tribal-source
    details:
      symbols: [Structure, build_structure, _attach_gaps]
  - type: file
    context: tribal-source
    locator: docs/tribal_markdown_spec.md
    details:
      section: Structural parsing and chunking
---

# Source Preserving Chunks

Chunking is derived retrieval structure; authors do not add artificial chunk markers, IDs, or vectors to Markdown. `chunk_document` validates and partitions a document's canonical body in memory, preserving complete source slices. Each chunk carries a half-open UTF-8 byte range, ordinal, heading path, optional section anchor, revision ID if supplied, and `chunker_version` (`tribal-structure-bytes-v1`). See [[Authoring/Markdown Contract]] for canonicalization and [[Authoring/Parser and Link Resolution]] for shared parsing boundaries. Resulting chunks are inputs to [[Indexing/Embedding Inputs and Vectors]] and part of [[Storage/Document Lifecycle]]. The overall flow is mapped in [[Home]].

## Structural boundaries

`parse_structure` delegates validation and extraction to the parser, then `build_structure` keeps ranges in canonical UTF-8 bytes. Frontmatter is excluded: `body_start_byte` is the first byte after the closing delimiter in the canonical file. Root-level body headings define sections and heading ancestry. Headings inside lists, quotes, and code do not create top-level section boundaries. The initial passage before a root heading has an empty heading path. A `section_anchor` is exposed only for a unique plain-text heading; duplicate or formatted headings still appear in `heading_path` but have no usable anchor.

Structural units include paragraphs, tables, fenced and indented code, Mermaid, lists, quotes and other parsed blocks. Protected regions also include opaque math/comments/HTML and reference or footnote definitions, whose source may not appear as ordinary rendered Markdown tokens. `_attach_gaps` assigns leading text and blank-line gaps to neighboring units so those bytes are not lost. Overlapping or crossing protected ranges are unioned before packing.

## Packing and oversized units

The soft target is 4,096 source bytes, not characters or model tokens. Units are greedily packed in source order while the resulting slice fits the target; there is no rebalancing. An oversized list can be split between complete immediate list items. Nested rich content stays with its containing item, so an oversized item remains intact. Other indivisible oversized blocks (including code fences, tables and opaque preserved regions) are emitted whole and receive `W_OVERSIZED_BLOCK` with source location, byte range and unit kind. The warning documents a soft-target exception; it does not truncate content. The spec's 8 MiB file acceptance cap bounds total authored input, but no model token capacity is promised by this chunker.

Every emitted chunk must satisfy `start_byte < end_byte` and decode cleanly as UTF-8. `chunk_document` checks that ranges form a contiguous partition from `body_start_byte` to the end of canonical bytes, that each `content` equals its exact source slice, and that concatenated chunk content reconstructs the full body. A violated invariant raises `E_CHUNK_INVARIANT`; invalid documents return no partial chunks. The 4,096-byte target is intentionally distinct from a downstream embedding model's input limit. A worker must handle an input that exceeds model limits explicitly, as described in [[Indexing/Durable Embedding Worker]].

## API and evidence boundary

`chunk_document(content, *, path='note.md', revision_id=None, knowledge_base=None, domains=None)` returns validity, diagnostics, document/revision identity, content hash, body start, chunker version and an ordered list of chunks. It performs no persistence or I/O. Repeated calls over identical canonical content produce the same layout under the current version. A policy change requires a new chunker version and deliberate regeneration of derived records; it does not change authored document content.

`tests/test_chunking_contract.py` specifies coverage, Unicode byte accounting, 4,095/4,096/4,097 boundaries, oversized protected blocks, list-item behavior and deterministic layout. This is a source-reading reference to test cases; tests were not executed for this note. Implementation claims here are limited to the inspected snapshot and do not certify model-provider behavior.
