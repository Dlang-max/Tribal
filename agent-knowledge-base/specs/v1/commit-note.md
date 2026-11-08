# Commit note — v1

Extends [the common format](common-note-format.md), with `type: commit`.
Record actual committed changes, not the current uncommitted working tree.

## Additional metadata

| Key | Requirement |
| --- | --- |
| `repository` | Required repository-note link. |
| `commit_hash` | Required complete source-verified commit hash. |
| `branch_name` | Optional exact branch ref observed when collecting the commit. A commit is not permanently owned by one branch. |

Deduplicate by repository-note ID plus full commit hash. An amend/rebase that
creates a different hash describes a different commit; preserve the old note.
Verified source facts must not be silently changed. Corrections to explanations
may be recorded through the updater with revision history and an explicit reason.

## Required body sections

| Section | Required content |
| --- | --- |
| `Summary` | Concise description of what was committed and why, grounded in the commit. |
| `Commit message` | Original full commit message, preserving meaningful formatting. |
| `Affected files` | Every changed path and a per-file description, based on the committed diff. Include change kind and old/new paths for renames or copies. |
| `Verification` | Checks actually run, their results, and limitations; state when none ran. |
| `Related notes` | Repository plus branch/decision/finding links when available. |

For root commits compare to the empty tree. For merge commits, explicitly state
the parent/comparison basis; there is no implicit single-parent diff. Empty
commits must say no files changed. Large change lists must remain complete in
the note or linked Markdown continuation notes; do not silently truncate.

## Example

Example vault path: `Commits/Reject Expired Discounts.md`.

```markdown
---
spec_version: 1
id: "commit-note-demo"
type: commit
title: Reject Expired Discounts
project_id: "checkout-demo"
created_at: "2026-11-07T16:00:00Z"
updated_at: "2026-11-07T16:00:00Z"
status: active
repository: "[[Repositories/Checkout Service]]"
commit_hash: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
branch_name: "feature/discount-validation"
---
# Reject Expired Discounts

## Summary
Reject expired discount codes before computing the discounted total.

## Commit message
Reject expired discounts

Return a validation error before calculating the discounted order total.

## Affected files
Comparison: commit against its first and only parent.

| Change | Path | Description |
| --- | --- | --- |
| modified | `src/checkout/discounts.py` | Reject codes whose expiration precedes the request time. |
| modified | `tests/test_discounts.py` | Cover expired-code rejection. |

## Verification
In this fictional example, `python -m pytest tests/test_discounts.py` passed.
Browser behavior was not checked.

## Related notes
- [[Repositories/Checkout Service]]
- [[Branches/Checkout Discount Validation]]
- [[Findings/Expired Code Accepted]]
```
