# Validate Tribal Markdown

The Python library validates the format in [the v1 specification](tribal_markdown_spec.md). It does not need a Git repository, MySQL, or network access. Git contexts are checked only when explicitly declared in a note.

## Install

From the project directory, using Python 3.12 or later:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

## Submit a file or vault

```bash
tribal validate tests/acceptance_fixtures/markdown_v1/baseline/Guide.md
python -m tribal validate tests/acceptance_fixtures/markdown_v1/baseline --json
tribal validate tests/acceptance_fixtures/markdown_v1/baseline --knowledge-base fixture-kb \
  --domain documentation --domain database --domain authentication --domain botany
```

Point directory validation at a knowledge vault. This project's specifications and README are ordinary Markdown, so validating the entire project as a vault will report missing Tribal metadata in those files.

Omit registry arguments for standalone format checks. Supply `--knowledge-base` and repeated `--domain` options when checking assignments against an existing registry. Without a registry, the validator checks assignment syntax and consistency, not whether the keys exist in a database.

Warnings allow acceptance and disclose unresolved references or unchecked features. Errors reject the submission. Exit codes are 0 for valid input, 1 for format errors, and 2 for usage or filesystem failures.

## Library

```python
from pathlib import Path
from tribal import validate_document, validate_vault

result = validate_document(
    Path("note.md").read_bytes(),
    path="research/note.md",
    knowledge_base="research",
    domains={"botany", "fieldwork"},
)
if not result["valid"]:
    for diagnostic in result["diagnostics"]:
        print(diagnostic)

# Keys are vault-relative paths; content can also be UTF-8 bytes.
vault = validate_vault({"Guide.md": Path("note.md").read_bytes()})
```

The library returns JSON-compatible results. Diagnostics include a stable code, severity, path, line and column, relevant field, expected and actual values, suggested correction, and source excerpt. Locations refer to normalized submitted text before removal of the generated revision token. Independent errors are collected so an author can correct several problems in one edit.

Parsed results retain the canonical authored Markdown, its SHA-256 hash, interpreted metadata, headings, structural blocks, and internal link occurrences. Defaults affect interpreted metadata without rewriting the source. Rich Markdown remains available as authored text; code and Mermaid are never executed.

## Scope and verification

This is an ingestion parser, not a Markdown renderer or persistence service. It does not verify the truth of evidence, contact source URLs, execute tests recorded in notes, render Mermaid, generate embeddings, or compare revision tokens against database state. Diagram syntax is explicitly reported as unchecked. A standalone file cannot resolve links to other documents; validate the full vault to resolve those references.

Run the independent suite and coverage report:

```bash
python -m pytest --cov=tribal --cov-branch --cov-report=term-missing
```

The implementation and black-box tests were authored by separate agents from identical copies of the public specification, fixtures, and [API contract](parser_api.md). Neither author received the other's conversation or source during initial authoring. Integration runs the completed tests against the implementation.
