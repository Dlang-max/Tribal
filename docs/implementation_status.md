# Chunking, storage, and search implementation status

The [implementation plan](superpowers/plans/2026-10-20-chunking-storage-search.md) is implemented on the integration branch, and all service code has received component or scoped review. Final strict branch-coverage verification and the whole-integration review remain open; see the [validation report](validation_report.md) for evidence, limits, and current measurements. The feature has not yet been merged into `main`.

## Delivered

| Area | Delivered capability |
|---|---|
| Contracts and structure | Frozen API/schema contracts, shared source structure, exact UTF-8 source-preserving chunks, protected units, location mapping, and compatible parser exports. |
| Storage | Versioned MySQL migrations, native vectors with tested dimension triggers, registry/profile APIs, transactions, and generation primitives. |
| Embeddings | Exact input wrapper/hash/token counting, float32 normalization, deterministic test provider, OpenAI adapter, durable jobs, retry/backfill/status, and profile activation. |
| Publication | Atomic batch ingestion, revision checks, namespace swaps, link refresh, soft delete/restore, and explicit rechunking. |
| Retrieval | Semantic/lexical/hybrid ranking, materialized cursor sessions, revision-pinned reads, and source context. |
| CLI and operations | Validate/chunk/ingest, indexing and profile operations, deletion/restoration, search/read/context, JSON diagnostics, Docker development setup, and operator recovery guidance. |

The dedicated tester authored the added acceptance tests and test data. Existing parser interfaces remain compatible. Component and correction reviews are recorded in the task workspace; the remaining required check is the final whole-integration review.

## Verification still in progress

The latest saved full acceptance run against the pinned MySQL 9.7.2 Community Docker image reports **527 passed and 2 skipped**. The skips are the opt-in live OpenAI smoke and the opt-in exact-search benchmark; the benchmark was run separately and passed. It reports **91.6118% statement coverage** and **84.9687% branch coverage** (814 of 958 branches); branch coverage is strictly below the 85% target despite rounded display showing 85%. One additional branch is needed to clear that threshold. Do not treat this as the final threshold-passing run until a fresh aggregate run confirms it.

The full suite includes the CLI and service acceptance checks. The CLI-specific suite separately passed all 22 checks against the same MySQL version. The exact-search benchmark and a second untraced operator-latency measurement are documented in the validation report. No live OpenAI request has been verified because no API key was supplied.

MySQL 9.7.2 rejects a CHECK constraint that references a VECTOR column. Tested BEFORE INSERT and BEFORE UPDATE triggers enforce vector dimensions while preserving native VECTOR storage and the profile-dimension foreign key. The supplied single-node development Compose configuration disables binary logging; external servers with logging enabled may require additional privileges to create those triggers.

## Remaining work

| Work | State |
|---|---|
| Coverage threshold | Add or exercise the missing branch, then rerun the aggregate suite with strict branch coverage. |
| Whole-integration review | Final independent review is pending after the threshold run. |
| OpenAI smoke | Optional credentialed check remains unrun; deterministic-provider tests do not prove live provider availability. |
| Main integration | User-requested merge to `main` remains to be completed after review. |

The branch-specific reports, test metadata, coverage artifacts, and private database startup/configuration are retained in the ignored `.superpowers/sdd/2026-10-20-chunking-storage-search/` workspace. Runtime configuration files may contain credentials and must not be copied into project documentation.
