---
schema_version: 1
id: cd28b42a-6f61-49ed-b3e0-3d7b110cc26b
title: Diagnostics and Recovery
knowledge_base: tribal
domain: operations
kind: reference
summary: Tribal returns bounded structured diagnostics for operational failures and distinguishes configuration, I/O, database, migration, and provider errors. Recovery starts from the diagnostic code and hint, with special care around MySQL DDL because failed migrations can leave partial schema changes.
status: active
tags:
  - tribal
  - operations
  - diagnostics
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
    locator: src/tribal/errors.py
    context: tribal-source
    details:
      symbols: [TribalError, TribalError.as_dict]
  - type: code
    locator: src/tribal/cli.py
    context: tribal-source
    details:
      symbols: [_io, _database, _provider, main]
  - type: code
    locator: src/tribal/storage.py
    context: tribal-source
    details:
      symbols: [Database.transaction, migrate]
  - type: test
    locator: tests/test_cli_pipeline_contract.py
    context: tribal-source
    details:
      outcome: not-run-code-inspection
      symbols: [test_malformed_database_port_produces_safe_json_diagnostic, test_chunk_missing_file_is_safe_operational_error]
---

# Diagnostics and Recovery

## Error envelopes and exit status

A `TribalError` carries one bounded diagnostic with `code`, severity, message, optional path or field, expected and actual values, a recovery hint, and null source excerpt and line coordinates. `as_dict()` wraps it as `{"ok": false, "diagnostics": [...]}`. Error construction explicitly forbids credentials, connection strings, raw provider response bodies, and complete notes in public messages. With `--json`, the CLI emits this structure for machine handling; text mode prints the same diagnostic fields in readable form.

The CLI uses exit status `0` for success, `1` for invalid user data or an unsuccessful operation, and `2` for operational errors caught as `TribalError` or I/O failures. Validation and chunking retain parser diagnostics; a missing path produces `E_IO`. A missing `TRIBAL_DB_USER`, malformed `TRIBAL_DB_PORT`, or absent required `OPENAI_API_KEY` produces `E_ARGUMENT` with the relevant field and a hint. Database connector errors are normalized to `E_DATABASE`; the underlying connector message is not forwarded. See [[CLI/Command Reference]] for output formats and [[Authoring/Parser and Link Resolution]] for content diagnostics.

## Configuration triage

For `E_ARGUMENT`, correct the named field before retrying. Set the database user and password, ensure the port is an integer from 1 to 65535, and check that the selected database exists. `E_DATABASE` advises checking availability, configuration, and migrations; Tribal also checks that the server's packet limit is at least 64 MiB. Confirm the running service is MySQL 9.7 before migration. The Compose service configures these local-development constraints; details are in [[Operations/Installation and Configuration]] and [[Storage/Database and Migrations]].

An embedding provider failure is reported as a safe `E_EMBEDDING_PROVIDER` diagnostic, with only general availability/configuration guidance. Durable worker failures are recorded on the job and may be retried according to job state. Inspect `index status` before retrying; explicit retry resets failed jobs for the selected profile. The worker and status flow is described in [[Indexing/Durable Embedding Worker]].

## Migration recovery

`migrate` serializes migration attempts, verifies migration checksums and ordered history, and applies packaged SQL files by version. MySQL DDL commits implicitly, so an error inside a migration may leave some statements applied even though the migration history row is absent. The wrapper reports `E_MIGRATION` and explicitly warns that DDL may be partial. Do not assume a normal transaction rollback repaired the schema, and do not edit an already-applied migration to work around a checksum mismatch.

For a development database with a failed partial migration, inspect the schema and migration history first. The migration hint recommends recreating a fresh development database before retrying an incomplete migration. This is recovery guidance from the implementation; it does not authorize deleting a shared or production database. For a history mismatch, restore the matching packaged migration files. For concurrent migration, wait for the active attempt and retry. MySQL 9.7.2's rejection of `CHECK` constraints over `VECTOR` values is why the schema uses tested insert and update triggers to enforce vector dimensions; do not remove them as a workaround.

## Content and input failures

For `E_IO`, verify the selected path exists, is readable, and points to a file or vault with lowercase `.md` documents. For validation diagnostics, fix the specified field, location, or syntax reported in the envelope; a warning can coexist with valid content. `E_BASE_REVISION_REQUIRED` or `E_REVISION_CONFLICT` during publication indicates the local edit was based on a stale or unrelated revision; compare the current head before publishing. Consult [[Storage/Publication and Revisions]] for revision conflict behavior and [[Operations/Vault Import Workflow]] for import decisions.

## Related notes

- [[Home]] — system map and entry point.
- [[Operations/Installation and Configuration]] — environment prerequisites.
- [[Testing/Validation and Benchmarks]] — recorded test scope and evidence limits.
