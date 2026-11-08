# Handoff note — v1

Extends [the common format](common-note-format.md), with `type: handoff`.
Capture unfinished work and enough context for another turn or agent to resume.
A handoff is temporary working context; durable knowledge should also be linked
from findings, insights, decisions, or guides where appropriate.

## Additional metadata

| Key | Requirement |
| --- | --- |
| `repository` | Required for repository-specific work; omit for project-wide coordination. |
| `branch_name` | Optional exact ref; requires `repository`. |
| `head_commit` | Optional full observed commit hash; requires `repository`. |

Do not require a session identity when unavailable. Concurrent agents' unrelated
handoffs must remain distinguishable; a new turn alone is not grounds to replace
another agent's unfinished work. Archive once explicitly resolved or obsolete,
with a reason and resolution links, instead of relying on age alone.

## Required body sections

| Section | Required content |
| --- | --- |
| `Goal` | Work to complete and why. |
| `Completed work` | What actually finished and supporting notes/commits. |
| `Current state` | Repository/branch state, known uncommitted work or conflicts, and checks actually performed. Explicitly state unknowns. |
| `Blockers` | Blockers, pending approvals/review gates, or an explicit none-known statement. |
| `Next steps` | Concrete ordered actions, including checks needed before claiming completion. |
| `Related notes` | Owning project/repository and relevant branch/commit/finding/guide notes. |

## Example

Example vault path: `Handoffs/Checkout UI Verification.md`.

```markdown
---
spec_version: 1
id: "handoff-note-demo"
type: handoff
title: Checkout UI Verification
project_id: "checkout-demo"
created_at: "2026-11-07T16:06:00Z"
updated_at: "2026-11-07T16:06:00Z"
status: active
repository: "[[Repositories/Checkout Service]]"
branch_name: "feature/discount-validation"
head_commit: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
---
# Checkout UI Verification

## Goal
Confirm that the checkout UI explains discount-expiration errors.

## Completed work
[[Commits/Reject Expired Discounts]] adds the server-side expiration check.

## Current state
The source branch is at the recorded commit. The collector observed a clean
working tree. Focused unit checks passed; browser behavior was not checked.

## Blockers
No browser test session has been started. No other blocker is known.

## Next steps
1. Recheck the current branch/head and working tree before making changes.
2. Follow [[Guides/Run Checkout Checks]] and inspect the UI error response.
3. Record the observed result and update this handoff when resolved.

## Related notes
- [[Repositories/Checkout Service]]
- [[Branches/Checkout Discount Validation]]
- [[Commits/Reject Expired Discounts]]
```
