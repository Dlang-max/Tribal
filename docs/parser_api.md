# Python parser and validator API v1

This is the public implementation contract for `tribal_markdown_spec.md`. The parser is independent of Git, MySQL, MCP, remote evidence availability, and embedding providers. It validates submitted documents and an in-memory vault; persistence and revision conflict checking belong to a later service layer.

## Library

Python 3.12+, package `tribal`:

```python
from tribal import validate_document, validate_vault

validate_document(content, *, path="note.md", knowledge_base=None, domains=None)
validate_vault(documents, *, knowledge_base=None, domains=None)
```

`content` is `str` or UTF-8 `bytes`; `documents` maps vault-relative paths to content. `knowledge_base` optionally restricts the expected assignment; `domains` optionally supplies the registered domain keys. When omitted, assignment syntax and vault consistency are checked, but registry existence is not asserted. No working context is inferred from the process environment.

Both functions return JSON-compatible dictionaries and collect independent diagnostics. Invalid submitted data produces diagnostics rather than exceptions. Programmer errors such as passing an unrelated Python object are outside this guarantee.

A document result has `valid: bool`, `path: str`, `diagnostics: list`, `document: dict | None`. Fatal envelope/YAML failures may have no document; recoverable validation errors may retain a partial document. A parsed document has:

- `metadata`: parsed properties with interpreted defaults; transport property excluded.
- `canonical_markdown`: normalized complete authored file with the transport line removed.
- `body`: preserved normalized body.
- `content_hash`: lowercase SHA-256 hex over canonical UTF-8 bytes.
- `base_revision`: transport UUID string or `None`.
- `headings`: objects with `level`, extracted `text`, `line`, `column`.
- `blocks`: structural objects with `kind`, `start_byte`, `end_byte`, `heading_path`; tables, fenced code, and Mermaid must be identifiable as `table`, `code`, `mermaid` respectively. Ranges index canonical UTF-8 bytes, half open.
- `links`: internal occurrences with `ordinal`, `raw_link`, `target_text`, nullable `target_anchor`, nullable `source_anchor`, `kind` (`wiki` or `markdown`), nullable `target_document_id`, `resolution` (`resolved`, `unresolved`, `ambiguous`), `line`, `column`. Occurrence order and lexical exclusions follow the format spec. Standalone validation can resolve self links; unavailable external document targets remain unresolved warnings.

A vault result has `valid`, flattened `diagnostics`, `documents` mapping paths to document results, and `summary` with integer `files`, `errors`, `warnings`. Resolve links against the complete valid identity/path index; reject duplicate document UUIDs, portable path collisions, and mixed knowledge bases. An invalid file must not stop checking other files.

## Diagnostics

Every diagnostic has `code`, `severity` (`error` or `warning`), `message`, `path`, `line`, `column`, `field`, `expected`, `actual`, `hint`, and `excerpt`. Positions are 1-based in normalized submitted content before transport-line removal. `field` identifies the nested property when applicable (for example `contexts[0].details.commit`). Values may be null only when not applicable or unavailable. Error messages must describe what failed and how to fix it; preview long offending values without dumping the full document. Excerpts should show the relevant line. Collect multiple independent metadata errors where parsing permits. Use the spec's diagnostic codes; `E_IO` is allowed for CLI filesystem failures. Unchecked Mermaid semantics must be disclosed with `W_MERMAID_UNCHECKED`.

## CLI

`python -m tribal validate PATH [--json] [--knowledge-base KEY] [--domain KEY ...]`, also available as `tribal` after installation. A file validates one document; a directory validates recursively selected lowercase `.md` documents, ignoring `.git`, `.obsidian`, virtual environments, and `.tribal-staging`. A directory must be a Tribal vault; ordinary project docs need not conform. No Git initialization or probing occurs during validation.

Text diagnostics are verbose by default, including locations, fields, expectations, actual values, hints, and excerpts. JSON emits the same structured result as the library (document or vault as appropriate). Exit 0 for valid input, 1 for validation errors, 2 for usage/I/O errors. Warnings alone do not fail validation.

## Scope

Support the document syntax, metadata, canonicalization, rich block extraction, internal links, and static vault checks. Database transaction semantics, revision conflict resolution, chunks/embeddings, evidence fetching, and Mermaid rendering are excluded. Preserve opaque extension source and avoid speculative links. The written format spec remains authoritative for validity and lexical behavior.
