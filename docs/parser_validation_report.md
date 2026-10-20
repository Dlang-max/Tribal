# Parser validation report

Date: 2026-10-20. Runtime: Python 3.12.3 on Linux.

The implementation and initial test suite were authored in separate directories and conversations. At the user's request, both agents were switched from Luna 6 high to GPT-6.1 Sol high during authoring. Each replacement received only its own task and existing files. Neither implementation author nor test author read the other's source or conversation. A separate read-only review examined the implementation without reading the tests.

The independently authored suite collected 275 cases before integration. Its frozen source had SHA-256 `900286a7823be5c80c1b5f6d7c3179713c878ee52a84ba18569917e48c1e851a`. Integration corrected one test expectation: a 513-code-point path requires `E_LIMIT` under specification Section 2.1, rather than `E_PATH`. The public API was clarified so heading columns point to opening syntax, consistently with link locations.

Review and integration added 15 regression cases for YAML-escaped surrogates, comment markers inside inline code, non-LF Unicode separators, empty self-anchor display aliases, and fence closure under indentation/list/quote containers. These regressions were observed failing before fixes and passing after them.

## Results

`python -m pytest -q --cov=tribal --cov-branch --cov-report=term-missing`:

- 290 tests passed.
- Statements: 679 of 716 covered (94.83%).
- Branches: 338 of 374 covered (90.37%).
- Combined coverage: 93.30%, including CLI subprocesses.

All 16 fixture canonical hashes and the complete baseline link-binding oracle are covered. The suite exercises valid and invalid metadata, YAML restrictions, context/source profiles, explicit Git semantics, Unicode/path/identity collisions, canonical byte preservation, rich blocks, link precedence and resolution, limits, batch recovery, diagnostic locations and detail, CLI output and exit codes, and absence of implicit Git probing.

Additional checks exercised malformed metadata through the public API without runtime exceptions, validated verbose and JSON errors for an abbreviated Git commit, and built a wheel containing the pinned Unicode folding data and attribution. The wheel was checked independently of the editable source installation.

These results cover the ingestion parser and static validator. They do not establish database import transactions, revision conflict handling against live state, external evidence availability or truth, Mermaid syntax/rendering, embeddings, or manual Obsidian Properties-panel compatibility.
