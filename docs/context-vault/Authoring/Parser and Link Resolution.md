---
schema_version: 1
id: b12ac38b-4936-4be1-914f-3c805e7d9961
title: Parser and Link Resolution
knowledge_base: tribal
domain: authoring
kind: overview
summary: Explains how Tribal validates Markdown, extracts eligible structure and links, then resolves links against a selected vault. Resolution is path and heading based, with explicit ambiguity warnings.
status: active
tags:
  - tribal
  - parser
  - wikilinks
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
      symbols: [_markdown, _resolve, validate_document, validate_vault]
  - type: code
    locator: src/tribal/structure.py
    context: tribal-source
    details:
      symbols: [parse_structure, build_structure]
  - type: file
    context: tribal-source
    locator: docs/tribal_markdown_spec.md
    details:
      section: Identity, paths, and links
---

# Parser and Link Resolution

The parser separates file validation, structural extraction, and target resolution. `validate_document` validates one file; internal links whose targets are outside that single-file view remain unresolved warnings. `validate_vault` validates an in-memory mapping of vault paths to file contents, enforces vault-wide identity/path constraints, and resolves links across that selected set. Neither API performs database or provider I/O. See [[Authoring/Markdown Contract]] for the metadata envelope, [[Authoring/Source Preserving Chunks]] for shared structural ranges, and [[Home]] for the system map. Link resolution feeds document relationships used by [[Retrieval/Search and Ranking]].

## Extraction precedence and opaque content

`_document` normalizes file-level newlines and parses frontmatter, forms canonical bytes, then calls `_markdown`; it computes the content hash after Markdown extraction. The parser recognizes Markdown block structure before scanning eligible inline source. Fenced and indented code, inline code, Mermaid, HTML, comments, math, and other opaque regions are preserved but do not contribute speculative links or headings. Standard Markdown links consume their full source span, so a wikilink inside their label or destination does not become a second edge. An Obsidian `![[...]]` embed is opaque. Unsupported extension semantics are reported as warnings while source stays intact.

For Tribal wikilinks the target syntax is `[[path-or-stem#Heading|label]]`; anchor and label, when supplied, must be nonempty. The first `]]` on the same line closes the candidate. Malformed candidates remain literal and produce `W_WIKILINK_SYNTAX`; a valid candidate exceeding projection limits is an error. Escaped openings are ignored. In table cells, source `\|` denotes the alias separator. Standard relative Markdown links ending in `.md` are also extracted, including reference-style uses, and empty-path heading fragments refer to the current file.

## Identity, paths, and targets

The vault path is a vault-root-relative POSIX path ending in `.md`; it is distinct from the stable UUID `id`. `validate_vault` rejects duplicate IDs, portable path collisions (Unicode NFC plus case folding), and mixed knowledge-base assignments. Directory names do not assign domains. Portable collision checks protect files moving between case-sensitive and case-insensitive filesystems without changing stored spelling.

Path-qualified wikilinks use the vault root, with optional terminal `.md`: `[[Authoring/Markdown Contract]]` resolves by exact case-sensitive path and can naturally cross domain folders. Ordinary path-qualified wikilinks are the preferred Obsidian graph link for cross-domain references. A target without `/` is a filename stem and resolves only if unique across the whole selected vault; title and aliases are not alternate identities. The parser never guesses among duplicate stems or similar paths. Standard Markdown `.md` links resolve relative to the containing file and normalize `.` and `..`; a destination that escapes the vault is unresolved.

Heading fragments match exact plain heading text, excluding the marker and surrounding whitespace. The target must contain exactly one heading with that text; duplicate headings or inline-marked headings cannot resolve. Nested heading paths and `^block-id` are preserved extensions and reported unsupported. Missing, ambiguous, or unsupported targets produce warnings rather than invalidating otherwise valid documents. Resolution records source order, original raw syntax, target text and anchor, resolution state, and target UUID when the document itself resolves.

## Interfaces and limits

`validate_document(content, *, path='note.md', knowledge_base=None, domains=None)` returns a result with validity, diagnostics and a parsed document (or `None` for earlier failures). `validate_vault(documents, *, knowledge_base=None, domains=None)` returns aggregate counts/diagnostics plus per-path results. `parse_structure` in `structure.py` returns the ordinary validation result and its shared structural representation; `chunk_document` uses that same pipeline. These are pure in-memory APIs in the inspected implementation.

The parser applies a 512-code-point path cap and path syntax restrictions; a wikilink's exact raw source is limited to 16 KiB, target text to 1,024 code points, and heading anchors to 255. Validation checks local syntax and vault membership, not external URLs, source availability, Obsidian's rendered graph, or GUI compatibility. For the complete normative rules consult `docs/tribal_markdown_spec.md` sections 7 and 10.
