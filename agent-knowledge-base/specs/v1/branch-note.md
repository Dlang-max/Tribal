# Branch note — v1

Extends [the common format](common-note-format.md), with `type: branch`.
Create/revise after an observed successful branch checkout or switch. The agent
must supply intended work; a branch name alone is not evidence of intent.

## Additional metadata

| Key | Requirement |
| --- | --- |
| `repository` | Required repository-note link. |
| `branch_name` | Required exact short Git branch ref; preserve spelling and slashes. |
| `work_status` | Required `planned`, `in_progress`, `blocked`, `done`, or `abandoned`. |
| `base_commit` | Optional full verified base commit hash. |
| `head_commit` | Optional full hash of the latest observed branch head. |

Match active notes by repository-note ID plus exact branch name, not name alone.
Detached HEAD does not establish a branch. Reuse/recreation of an old branch name
must be reviewed before reviving archived intentions. Partial reports must not
erase another agent's known work; preserve attribution and unresolved conflicts.

## Required body sections

| Section | Required content |
| --- | --- |
| `Intent` | Agent-stated goal and scope, clearly described as intended work. |
| `Progress` | Observed completed work and links to relevant commits/merges. |
| `Remaining work` | Next actions, blockers, or an explicit completion statement. |
| `Related notes` | Repository and relevant handoff/knowledge notes. |

## Example

Example vault path: `Branches/Checkout Discount Validation.md`.

```markdown
---
spec_version: 1
id: "branch-note-demo"
type: branch
title: Checkout Discount Validation
project_id: "checkout-demo"
created_at: "2026-11-07T15:00:00Z"
updated_at: "2026-11-07T16:05:00Z"
status: active
repository: "[[Repositories/Checkout Service]]"
branch_name: "feature/discount-validation"
work_status: in_progress
base_commit: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
head_commit: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
---
# Checkout Discount Validation

## Intent
Add server-side validation for expired discount codes before calculating totals.

## Progress
[[Commits/Reject Expired Discounts]] implements the expiration check.

## Remaining work
Verify the checkout UI against the validation response. No UI check has run yet.

## Related notes
- [[Repositories/Checkout Service]]
- [[Handoffs/Checkout UI Verification]]
```
