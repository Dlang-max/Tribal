# Chunking, storage, and search implementation status

The [implementation plan](superpowers/plans/2026-10-20-chunking-storage-search.md) is implemented and merged to `main` at `f3c7c12e8b61a15c48777d6de1cefb05c5058946`. It is verified against MySQL 9.7.2, both strict coverage gates pass, and the final whole-integration review found no Critical or Important issues. The fresh post-merge aggregate check also passed. See the [validation report](validation_report.md) for exact evidence and limits. Credentialed live OpenAI behavior has not been verified.

## Delivered

| Area | Delivered capability |
|---|---|
| Contracts and structure | Frozen API/schema contracts, shared source structure, exact UTF-8 source-preserving chunks, protected units, location mapping, and compatible parser exports. |
| Storage | Versioned MySQL migrations, native vectors with tested dimension triggers, registry/profile APIs, transactions, and generation primitives. |
| Embeddings | Exact input wrapper/hash/token counting, float32 normalization, deterministic test provider, OpenAI adapter, durable jobs, retry/backfill/status, and profile activation. |
| Publication | Atomic batch ingestion, revision checks, namespace swaps, link refresh, soft delete/restore, and explicit rechunking. |
| Retrieval | Semantic/lexical/hybrid ranking, materialized cursor sessions, revision-pinned reads, and source context. |
| CLI and operations | Validate/chunk/ingest, indexing and profile operations, deletion/restoration, search/read/context, JSON diagnostics, Docker development setup, and operator recovery guidance. |

The dedicated tester authored the added acceptance tests and test data. Existing parser interfaces remain compatible. Component, correction, and final whole-integration reviews are recorded in the task workspace; the final review passed without Critical or Important findings.

## Verification

The fresh aggregate run on the merged `main` commit completed with **531 passed and 2 skipped** in 88.81 seconds (89.237 seconds including the runner wrapper), against the pinned MySQL 9.7.2 Community Docker image. The skips are the opt-in live OpenAI smoke and the opt-in exact-search benchmark; that benchmark was run separately and passed. Source and test revisions remained stable at `f3c7c12e8b61a15c48777d6de1cefb05c5058946`; the run includes assertion follow-up `0e2f71d`. Coverage was **91.7910% statement** (2,091/2,278) and **85.0731% branch** (815/958), meeting the strict 90% and 85% gates.

The full suite includes the CLI and service acceptance checks. The CLI-specific suite separately passed all 22 checks against the same MySQL version. The exact-search benchmark and an untraced operator-latency measurement are documented in the validation report. The live OpenAI smoke remains unrun because no API key was supplied.

MySQL 9.7.2 rejects a CHECK constraint that references a VECTOR column. Tested BEFORE INSERT and BEFORE UPDATE triggers enforce vector dimensions while preserving native VECTOR storage and the profile-dimension foreign key. The supplied single-node development Compose configuration disables binary logging; external servers with logging enabled may require additional privileges to create those triggers.

## Remaining work

| Work | State |
|---|---|
| OpenAI smoke | Optional credentialed check remains unrun; deterministic-provider tests do not prove live provider availability. |

The branch-specific reports, test metadata, coverage artifacts, and private database startup/configuration are retained in the ignored `.superpowers/sdd/2026-10-20-chunking-storage-search/` workspace. Runtime configuration files may contain credentials and must not be copied into project documentation.
