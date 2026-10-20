---
schema_version: 1
id: 403b87ed-0435-4957-b13d-fd19ed296269
title: Validation and Benchmarks
knowledge_base: tribal
domain: testing
kind: reference
summary: Tribal separates parser and deterministic component contracts from optional real-MySQL acceptance, credentialed OpenAI smoke, and exact-search benchmark runs. The repository records a final 531-pass aggregate and specific traced and untraced timings; those report values describe their recorded environment, not a fresh run of this documentation pass.
status: active
tags:
  - tribal
  - testing
  - validation
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
  - type: file
    locator: docs/validation_report.md
    context: tribal-source
  - type: test
    locator: tests/conftest.py
    context: tribal-source
    details:
      outcome: not-run-code-inspection
      symbols: [pytest_configure, mysql_config, live_openai_enabled, mysql_db]
  - type: test
    locator: tests/test_parser_regressions.py
    context: tribal-source
    details:
      outcome: not-run-code-inspection
  - type: test
    locator: tests/test_exact_search_benchmark.py
    context: tribal-source
    details:
      outcome: not-run-code-inspection
      symbols: [test_full_path_exact_search_benchmark]
  - type: test
    locator: tests/benchmark_exact_search.py
    context: tribal-source
    details:
      outcome: not-run-code-inspection
      symbols: [run_benchmark]
---

# Validation and Benchmarks

## Test architecture

The suite divides fast local contracts from tests that require an explicit external prerequisite. Parser regressions and contracts cover Markdown envelopes, Unicode, diagnostics, source ranges, link resolution, and chunking without a database. CLI contracts test argument handling and subprocess output. Storage, publication, retrieval, worker, and end-to-end database contracts use the `mysql` marker and `mysql_db` fixture. `TRIBAL_TEST_MYSQL_CONFIG` must contain connector JSON for an isolated real MySQL database; when it is absent, pytest skips those tests. Once supplied, connection or implementation failures are test failures, not prerequisite skips. The tested server target is MySQL 9.7, with the recorded acceptance run on the pinned Community 9.7.2 image.

The embedding contracts use deterministic or fake providers for request formatting, hashing, vector validation, retries, and local pipeline behavior. A live smoke test is marked `live_openai`; it requires both `TRIBAL_TEST_LIVE_OPENAI=1` and `OPENAI_API_KEY`. This test makes an actual provider request. No live API request was included in the reported aggregate acceptance run.

The exact-search benchmark is separately marked `mysql` and `benchmark`, and additionally requires `TRIBAL_TEST_BENCHMARK=1`. Its controlled corpus uses a fixed deterministic query vector and no live API call. It seeds real database rows, exercises public semantic search, checks exact ranking against an oracle, and verifies the candidate-capacity error. Running it is a database write workload; do so only with an isolated test database. This note describes the architecture and recorded results, not a command execution during vault authoring.

## Recorded acceptance result

`docs/validation_report.md` records a fresh post-merge aggregate of **531 passed and 2 skipped** in 88.81 seconds. The report identifies the two skips as the optional live OpenAI smoke and the opt-in benchmark, which it says passed separately. It records **91.7910% statement coverage (2,091/2,278)** and **85.0731% branch coverage (815/958)**, above the stated 90% and 85% gates. These are quoted as recorded report outcomes; they are not fresh results for this note or a claim that tests ran at the source snapshot declared in this note. The report says the acceptance database used the pinned official MySQL 9.7.2 Community image.

## Recorded exact-search measurements

The report's traced benchmark used 1,000 documents and 1,000 eligible vectors of 1,536 dimensions. Three full public semantic searches checked exact top-100 results and materialized all 1,000 rankings. With Python `tracemalloc` active, median latency was **8.0691 seconds** and peak measured Python allocation was **20.23 MiB**. Four warm untraced trials after a first trial measured **0.774877, 0.737241, 0.747566, and 0.742360 seconds**; the reported five-run median was **0.747566 seconds**. Both used a fixed local query vector without a live provider call.

The traced and untraced timings include different instrumentation, so compare them as separate measurements. They are specific to the reported 1,000-vector corpus, code revision, and shared 16-logical-CPU host under variable load. The untraced warm median is not a cold-start guarantee or a service-level objective. The report says the default 100,000-candidate guard is a rejection bound, not a measured supported corpus size. See [[Retrieval/Search and Ranking]] for the scan and ranking behavior behind the benchmark.

## Evidence limits

Read contract tests as evidence of intended and asserted behavior only when their execution is separately recorded. The suite's deterministic provider does not demonstrate live OpenAI availability or semantic quality, and database acceptance does not establish production privileges under binary logging. The historical validation report is the source for the numerical outcomes above; benchmark JSON artifacts listed there retain the measured data. [[Operations/Diagnostics and Recovery]] covers failure response, while [[Home]] provides the vault map and [[Indexing/Durable Embedding Worker]] explains the tested background indexing path.

## Related notes

- [[Home]] — vault entry point.
- [[Operations/Installation and Configuration]] — prerequisites and provider key boundary.
- [[Retrieval/Search and Ranking]] — benchmarked search path.
