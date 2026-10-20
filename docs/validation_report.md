# Chunking, storage, and search validation report

**Date:** 2026-10-20  
| Validation | Snapshot |
|---|---|
| Full acceptance source | `6f2b193` |
| Full acceptance tests | `11f7b89` |
| Search benchmark source | `57006f3f2d7b281db53747b761ecea6d5e9c5152` |

## Acceptance checks

The full run against the pinned MySQL 9.7.2 Community Docker image completed with **531 passed and 2 skipped in 88.89 seconds**. One skip is the optional live OpenAI smoke; the other is the opt-in exact-search benchmark, which was run separately and passed. Source and test trees remained stable during that run. Coverage was **91.7910% of statements (2,091/2,278)** and **85.0731% of branches (815/958)**, meeting the strict 90% statement and 85% branch targets.

The CLI's independent real-MySQL suite passed **22 checks**. Component acceptance suites and fixes received scoped review, and the final whole-integration review passed with no Critical or Important findings (see the task workspace's `review-final-integration.md`). The full validation does not include a live OpenAI request; no API key was supplied, and deterministic-provider coverage verifies local behavior only. After the aggregate run, assertion-only test follow-up `0e2f71d` passed four focused tests in 2.10 seconds. A post-merge aggregate rerun including that follow-up remains pending.

MySQL verification used the pinned official Community 9.7.2 image. MySQL rejects CHECK constraints over VECTOR values, so the schema enforces vector dimensions with tested BEFORE INSERT and BEFORE UPDATE triggers. The development Compose configuration disables binary logging. Production-like installations with binary logging may require elevated migration privileges to create the triggers.

## Exact-search benchmark

The full benchmark seeded 1,000 documents and 1,000 eligible 1,536-dimensional vectors, then ran three public semantic searches with a fixed deterministic query vector and no provider API call. Each search checked the exact top 100 against its oracle and materialized all 1,000 ranked results into the session; the benchmark also verified that an over-capacity request returns `E_SEARCH_CAPACITY` without a partial page.

The three measured latencies were **8.7383 s, 8.0691 s, and 7.7829 s** (median **8.0691 s**, maximum **8.7383 s**). This benchmark run collected Python allocations with `tracemalloc`; its peak was **21,214,813 bytes (20.23 MiB)**. The traced timings include database scanning, exact ranking, session materialization, and page provenance. They are useful as a full-path instrumented benchmark, not as a normal operator latency headline.

On the same 1,000-vector corpus, five additional `LIMIT 100` public searches ran with neither `tracemalloc` nor debug tracing enabled. Their latencies were **1.795894, 0.774877, 0.737241, 0.747566, and 0.742360 s**; median **0.747566 s**. The first trial was 1.80 s and the four following trials were 0.74–0.77 s. A fixed query vector was used, with no live API call. This is the more representative measured warm operator-search latency; it is not a cold-start guarantee.

These runs used a shared 16-logical-CPU host with no swap and approximately 556–608 MiB available memory around the full benchmark. The host was under variable load. The results cover only this corpus, software snapshot, and host; they do not establish capacity or latency for larger corpora or other machines. Search-process Python allocation measurements exclude seeding, native allocations, and MySQL server memory. The default 100,000-candidate guard is a rejection bound, not a measured supported corpus size.

Machine-readable benchmark data is kept in [exact-search-2026-10-20.json](benchmarks/exact-search-2026-10-20.json), [exact-search-host-2026-10-20.json](benchmarks/exact-search-host-2026-10-20.json), and [operator-search-untraced-2026-10-20.json](benchmarks/operator-search-untraced-2026-10-20.json).

## Completion gates

The strict coverage gates and final whole-integration review have passed. The remaining check is a post-merge aggregate rerun that includes `0e2f71d`. The feature is ready for the authorized merge to `main`. Live OpenAI smoke testing remains optional and requires an API key; report its result separately from offline and database-backed validation.
