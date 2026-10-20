# Parser and validator implementation

1. Initialize a local repository and record a public Python API contract.
2. Give two Luna 6 high agents separate snapshots of the spec, fixtures, and contract. One implements the package and CLI; one independently authors black-box tests. Neither reads the other's files or conversation during authoring.
3. Integrate both completed outputs in this workspace. Run the independent suite, examine failures against the written specification, and correct implementation defects without weakening expectations.
4. Measure coverage, exercise verbose and JSON CLI failures, and document installation, usage, and material limits. Preserve existing design documents.

Acceptance: valid domain-agnostic notes are accepted; invalid notes produce actionable, located errors; canonical authored bytes and rich Markdown survive parsing; supported links resolve deterministically; batch validation recovers across invalid files. No database or remote repository is required.
