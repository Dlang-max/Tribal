# Chunking, storage, and search implementation status

The [implementation plan](superpowers/plans/2026-10-20-chunking-storage-search.md) is **partially implemented**. Work is retained on `chunking/integration` and isolated feature branches. Work has resumed after an account usage interruption; the remaining services are being implemented. This is not a completed milestone.

## Delivered and reviewed

| Component | State |
|---|---|
| Contracts | Frozen [API/schema contracts](implementation_contracts.md), pinned runtime dependencies and hash-checked lock. |
| Structure/chunking | Shared parser structure, exact source-preserving chunks, protected units and source mapping; exported `chunk_document`. |
| Storage | Executable MySQL migrations, native vectors, registry/profile APIs, transactions, generation primitives and pinned Docker image. |
| Embedding primitives | Exact input wrapper/hash/token counting, float32 normalization, deterministic provider and OpenAI adapter. |

These components passed GPT-6 Luna high reviews, including scoped reviews of corrections. The existing parser API remains compatible. Only the dedicated tester agent authored new tests and test data.

The latest coordinator verification against the official pinned MySQL 9.7.2 Community Docker container passed **365 tests**, with **one skipped credentialed OpenAI smoke test**, in 7.56 seconds. This verifies the currently integrated components; it does not cover unimplemented services. Storage separately passed all 15 real MySQL tests against both Docker and the extracted official server executable. After resumption, 21 CLI checks passed; the CLI owner also verified real database migration and registry/profile commands. The runtime lock also passed a fresh hash-checked installation, dependency check and tokenizer/import smoke check.

MySQL 9.7.2 rejects a CHECK constraint referencing a VECTOR column. Tested BEFORE INSERT and BEFORE UPDATE triggers enforce vector dimensions instead, while preserving native VECTOR storage and the profile dimension foreign key. Development Docker configuration disables binary logging; a deployment with logging enabled needs sufficient migration privileges for trigger creation.

## Remaining work

| Branch | Remaining action |
|---|---|
| `chunking/cli` | CLI commands and operator guide are reviewed and integrated; final service-pipeline checks remain. |
| `chunking/embeddings` | Implement durable queue/worker fencing, transaction-local enqueue, backfill/retry/status and profile activation. |
| `chunking/publication` | Implement atomic ingestion, lifecycle changes, complete link refresh, path swaps/history and explicit rechunking. |
| `chunking/retrieval` | Implement ranking, durable search sessions/pagination, revision-pinned reads and diagram context. |
| `chunking/tests` | Acceptance suites for the remaining services and a full-path 1,536-dimensional search benchmark are committed; run them against reviewed implementations, measure full coverage and add missing cases. |
| `chunking/integration` | Integrate reviewed components, run all Docker acceptance checks, benchmark and final whole-integration review; report the credentialed OpenAI smoke separately. |

The plan's final 90% statement/85% branch coverage thresholds, full Docker pipeline, search benchmark and live OpenAI verification have not been achieved or claimed. No PR, push or merge into `main` has been performed for the feature implementation.

## Resume information

The coordinator's detailed ledger, branch-specific briefs, author/reviewer reports, review diffs, and private test-server startup/configuration are retained in the ignored `.superpowers/sdd/2026-10-20-chunking-storage-search/` workspace. Resume from that ledger; do not recreate completed branches. All feature worktrees were clean when the usage limit interrupted the agents.

The integration checkout also contains an unrelated untracked order-management benchmark plan. It was left untouched.
