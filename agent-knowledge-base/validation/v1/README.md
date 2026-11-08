# Validate a v1 Markdown knowledge base

Run this read-only validator against a complete project vault, including all
notes proposed for publication. It uses the existing Python and PyYAML environment.
From the Tribal repository root:

```sh
.venv/bin/python agent-knowledge-base/validation/v1/validate_knowledge_base_notes.py /path/to/project-vault
.venv/bin/python agent-knowledge-base/validation/v1/validate_knowledge_base_notes.py /path/to/project-vault --project-id checkout-demo --json
```

Exit status is `0` for structural/local cross-note success, `1` for validation
issues, and `2` for CLI usage errors. JSON output is always an array of objects
with `path`, `code`, and `message`; a valid vault produces `[]`. Issue paths are
relative to the vault. Text mode includes readable diagnostics. No files change.

For Python callers, place this directory on the import path and use:

```python
from validate_knowledge_base_notes import ValidationIssue, validate_vault

issues = validate_vault("/path/to/project-vault", expected_project_id="checkout-demo")
```

`ValidationIssue` is an immutable dataclass. Results are deduplicated and sorted
by path, code, and message. The validator recursively reads `.md` files, ignores
`.obsidian`, and rejects symlinked Markdown files/directories. All Markdown files
in the selected vault must be v1 notes; point it at the published project vault,
not the specification directory or the current historical context vault.

Checks cover the [common format](../../specs/v1/common-note-format.md) and all
[eleven types](../../specs/v1/README.md): UTF-8/LF/newlines, safe YAML and duplicate
keys, closed metadata and field types, quoted dates/hashes/refs/metadata links,
timestamp order, lifecycle/enums, required meaningful sections, internal paths,
heading targets, project scope, repository targets and related entrypoints,
local identity collisions, replacement cycles, and merge hash consistency.
Headings and links inside fenced or inline code are treated as code; HTML
comments do not create document structure or links. Archived and superseded
notes remain link targets. Required sections use a practical
empty/TODO check; a statement such as `None observed` is accepted.

The validator checks what local files can establish. It does not authenticate
the caller or prove that `project_id` is authorized; supply `--project-id` from
trusted application context. It does not contact Git, remotes, databases,
SeaweedFS, or other services. A lowercase hexadecimal hash is structurally
accepted without assuming SHA-1 length; a source adapter must establish its
completeness, identity, ancestry, and actual observation. Command/test success,
push outcomes, source freshness, approval, intent, truth, per-file change-list
completeness, and other natural-language claims still need source verification
and updater review. Prose discussing embedding models is allowed; undocumented
embedding/index metadata fields are rejected. Storage revisions, replay receipts,
permissions, concurrent updates, indexing, and cross-system publication remain
separate work. This is a validation tool, not the publication/storage protocol.
