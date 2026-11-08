# Merge note — v1

Extends [the common format](common-note-format.md), with `type: merge`.
A merge note records completed integration. Failed commands, unresolved
conflicts, and planned merges belong in findings/handoffs until completed.

## Additional metadata

| Key | Requirement |
| --- | --- |
| `repository` | Required target-repository note link. |
| `source_event_id` | Required stable identity of the observed integration; retries reuse it. |
| `observed_at` | Required source-observation timestamp. |
| `source_ref` | Required observed source ref or full source commit hash. |
| `source_commit` | Required full source-tip hash used for integration. |
| `target_branch` | Required exact target branch ref. |
| `target_before` | Required full target-head hash before integration. |
| `target_after` | Required full resulting target-head hash. |
| `merge_kind` | Required `merge_commit`, `fast_forward`, or `squash`. |

Deduplicate by source-event identity within the project. Verify the resulting
source/target facts against Git. A fast-forward's `target_after` equals
`source_commit`; a merge-commit result must be the actual new merge commit.
An already-up-to-date no-op does not establish a new integration.
`git merge --squash` alone does not produce a resulting commit: publish a squash
integration note only after the corresponding commit is observed.

## Required body sections

| Section | Required content |
| --- | --- |
| `Summary` | What was integrated, why, and into which target. |
| `Integrated changes` | Changes actually introduced relative to `target_before`, with affected paths/descriptions and relevant commit links. Do not claim squash imported source ancestry. |
| `Conflicts and verification` | Conflicts/resolutions actually observed, checks run, and limitations. |
| `Related notes` | Target repository and available branch/commit/decision notes. |

## Example

Example vault path: `Merges/Integrate Discount Validation.md`.

```markdown
---
spec_version: 1
id: "merge-note-demo"
type: merge
title: Integrate Discount Validation
project_id: "checkout-demo"
created_at: "2026-11-07T16:15:00Z"
updated_at: "2026-11-07T16:15:00Z"
status: active
repository: "[[Repositories/Checkout Service]]"
source_event_id: "merge-operation-demo"
observed_at: "2026-11-07T16:14:00Z"
source_ref: "feature/discount-validation"
source_commit: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
target_branch: "main"
target_before: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
target_after: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
merge_kind: fast_forward
---
# Integrate Discount Validation

## Summary
Fast-forward main to include server-side discount-expiration validation.

## Integrated changes
[[Commits/Reject Expired Discounts]] changes `src/checkout/discounts.py` and
`tests/test_discounts.py`. No merge commit was created.

## Conflicts and verification
No conflicts were observed. No additional checks ran after integration.

## Related notes
- [[Repositories/Checkout Service]]
- [[Branches/Checkout Discount Validation]]
- [[Commits/Reject Expired Discounts]]
```
