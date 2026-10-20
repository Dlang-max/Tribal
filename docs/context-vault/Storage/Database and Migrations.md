---
schema_version: 1
id: 82d3bea7-c33a-4ab6-9f22-28af0fadcbc5
title: Database and Migrations
knowledge_base: tribal
domain: storage
kind: reference
summary: Tribal stores authored revisions and their derived publication state in MySQL InnoDB. This note describes the schema boundaries, transaction policy, migration checksums, and native vector dimension guard.
status: active
verification_state: unverified
tags:
  - storage
  - mysql
  - migrations
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
    locator: src/tribal/storage.py
    context: tribal-source
    details:
      symbols: [Database, migrate, lock_knowledge_base, advance_generations]
  - type: code
    locator: src/tribal/migrations/001_content.sql
    context: tribal-source
    details:
      symbols: [knowledge_bases, document_revisions, document_chunks, chunk_embeddings, chunk_embeddings_dimensions_insert, chunk_embeddings_dimensions_update]
  - type: code
    locator: src/tribal/migrations/002_jobs_sessions.sql
    context: tribal-source
    details:
      symbols: [embedding_jobs, search_sessions, search_session_results]
  - type: test
    locator: tests/test_storage_contract.py
    context: tribal-source
    details:
      outcome: not-run-code-inspection
---

# Database and Migrations

Tribal uses MySQL 9.7 with InnoDB for its knowledge, indexing, and search state. Authored documents are represented by stable document identities plus immutable revision snapshots; chunks, links, sources, embedding jobs, and vectors are separate projections. For how a validated note enters these tables, see [[Storage/Publication and Revisions]]. The broader component picture is in [[Architecture/System Map]], and the model configuration stored alongside vectors is described in [[Indexing/Embedding Profiles]].

## Storage shape

`001_content.sql` defines the core schema. `knowledge_bases` owns independent `domains`, document namespaces, the active embedding profile, and two monotonic counters: `knowledge_generation` and `indexing_generation`. `documents` keeps the stable UUID, current vault-relative path, pointer to the current revision, and nullable `deleted_at`. `document_revisions` stores the historical Markdown bytes and parsed metadata, including path at the time of authorship, domain, parent revision, source hash, author attribution, and change summary. Composite foreign keys ensure a revision's document and domain belong to its declared knowledge base, and its parent belongs to the same document.

Revision-scoped evidence and outgoing links live in `document_sources` and `document_links`. `document_chunks` stores the derived chunk text, heading context, source byte range, ordinal, and chunker version. `embedding_profiles` records model/configuration and dimension identity. `chunk_embeddings` stores a MySQL `VECTOR(16383)` with declared dimensions and input hash. Migration `002_jobs_sessions.sql` adds durable `embedding_jobs`, plus search session snapshots and ranked results. All these tables use InnoDB so normal publication writes can commit or roll back together.

The database constraints cover ownership, uniqueness, JSON shape, source/chunk capacity, and valid ranges. Portable path collisions require application-level NFC and case-fold comparison under the knowledge-base lock; the database path collation is intentionally not the portability rule.

## Connections and lock order

`Database.transaction()` creates and closes a connection per call, disables autocommit, pins the session to UTC, utf8mb4, and strict SQL mode, and begins an explicit `REPEATABLE READ` transaction. Read-only transactions request a consistent snapshot. Success commits; exceptions roll back, with connector failures translated to `E_DATABASE`. Nested transactions on the same thread are rejected. Connections also require at least 64 MiB `max_allowed_packet` to carry the contract's maximum document and derived payload.

Mutating knowledge-base operations acquire `knowledge_bases` through `lock_knowledge_base()` (`SELECT ... FOR UPDATE`) first. They then lock involved documents by UUID order and update generations within the same transaction. This serializes namespace checks, revision pointer changes, and generation updates across concurrent clients. `advance_generations()` increments each selected counter at most once per logical operation; it is a no-op when neither flag is requested. See [[Storage/Document Lifecycle]] for the generation effects of deletion and rechunking, and [[Indexing/Durable Embedding Worker]] for the worker's publication lock boundary.

## Migration history and recovery limits

`migrate()` discovers packaged `.sql` files in filename order and computes SHA-256 over each file's exact bytes. It requires a selected MySQL 9.7 database and takes a database-specific advisory lock before inspecting `schema_migrations`. Applied entries must match both packaged checksums and an ordered prefix of known migrations; altered history, unknown future versions, or gaps are rejected as `E_MIGRATION`. Each completed migration records its version and 32-byte checksum, making repeat calls idempotent.

MySQL DDL may commit implicitly, so a failed migration file can leave partial schema changes even though its history row was not written. The transaction wrapper cannot make those DDL statements atomic. The migration error explicitly reports possible partial application; inspect the schema and use a fresh development database for recovery rather than assuming rollback restored it. The migration code and MySQL acceptance tests are evidence for these behaviors; this note does not claim that tests were run while preparing the vault.

## Native vector dimension check

The profile foreign key ensures `chunk_embeddings.dimensions` equals the profile's declared dimension. MySQL 9.7.2 rejects a `VECTOR` reference in a `CHECK`, so migration 001 also installs `BEFORE INSERT` and `BEFORE UPDATE` triggers. Both compare `VECTOR_DIM(NEW.embedding)` with `NEW.dimensions` and signal SQLSTATE `45000` on mismatch. This guards direct SQL writes as well as application writes; the acceptance contract explicitly exercises both trigger paths. See [[Indexing/Embedding Inputs and Vectors]] for how input hashes and numeric vector payloads relate to these rows.

## Related notes

[[Home]] links to the complete vault map. The authored and derived write boundary is detailed in [[Storage/Publication and Revisions]], while [[Operations/Installation and Configuration]] covers how a local instance is configured before migrations are run.
