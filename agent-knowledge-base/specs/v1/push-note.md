# Push note — v1

Extends [the common format](common-note-format.md), with `type: push`.
This optional activity note records confirmed remote ref updates, not merely a
push command starting. Partial push success must distinguish successful and
rejected refs; it is not an all-success claim.

## Additional metadata

| Key | Requirement |
| --- | --- |
| `repository` | Required repository-note link. |
| `source_event_id` | Required persistent push-operation identity for replay deduplication. |
| `observed_at` | Required source-observation timestamp. |
| `remote_name` | Required exact configured Git remote name. |
| `remote_url` | Optional verified remote URL. |

## Required body sections

| Section | Required content |
| --- | --- |
| `Summary` | What was published and why. |
| `Ref updates` | For each attempted ref: full remote ref, observed outcome, known before/after object IDs, and whether created/updated/deleted. At least one must have succeeded. |
| `Verification` | Source of push confirmation and limits; push success is not deployment success. |
| `Related notes` | Repository and relevant commits/branches/merges. |

Use full observed object IDs. For a created/deleted ref, explain that its old/new
value does not exist rather than invent a hash. Mark an unavailable value
`unknown`. Forced updates must be stated if observed. A no-op or wholly rejected
push does not create a successful-push note; use a finding/handoff if useful.

## Example

Example vault path: `Pushes/Publish Discount Validation.md`.

```markdown
---
spec_version: 1
id: "push-note-demo"
type: push
title: Publish Discount Validation
project_id: "checkout-demo"
created_at: "2026-11-07T16:20:00Z"
updated_at: "2026-11-07T16:20:00Z"
status: active
repository: "[[Repositories/Checkout Service]]"
source_event_id: "push-operation-demo"
observed_at: "2026-11-07T16:19:00Z"
remote_name: "origin"
---
# Publish Discount Validation

## Summary
Publish the integrated discount validation on the remote main branch.

## Ref updates
`refs/heads/main` successfully updated from
`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` to
`bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`.

## Verification
The collector observed a successful remote ref update in Git's push result.
No deployment was performed or verified.

## Related notes
- [[Repositories/Checkout Service]]
- [[Merges/Integrate Discount Validation]]
```
