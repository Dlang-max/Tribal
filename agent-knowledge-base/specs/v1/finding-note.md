# Finding note — v1

Extends [the common format](common-note-format.md), with `type: finding`.
A finding records an observation, result, or known issue with its evidence.
Use it for bugs and failed checks without adding a separate issue type in v1.

## Additional metadata

`repository` is required for a repository-specific finding; omit it for a
project-wide finding. There are no other additional fields.

## Required body sections

| Section | Required content |
| --- | --- |
| `Observation` | What was actually observed, in which conditions, and its scope. |
| `Evidence` | Repro steps, command/result, source excerpt, or source link. Supply repository path and commit/ref context when known. |
| `Implications` | What the observation suggests, remaining uncertainty, and whether it remains current. Separate interpretation from observation. |
| `Related notes` | Owning project/repository and available fixes/insights/guides. |

Do not deduplicate findings by semantic similarity alone: different environments
may produce different results. A fixed issue may retain an active historical
finding with a clearly described resolution, or be archived by the updater;
neither implies its original observation never happened.

## Example

Example vault path: `Findings/Expired Code Accepted.md`.

```markdown
---
spec_version: 1
id: "finding-note-demo"
type: finding
title: Expired Code Accepted
project_id: "checkout-demo"
created_at: "2026-11-07T15:10:00Z"
updated_at: "2026-11-07T16:05:00Z"
status: active
repository: "[[Repositories/Checkout Service]]"
---
# Expired Code Accepted

## Observation
An expired discount code was accepted by the local validation function before
the expiration check was added.

## Evidence
In this fictional reproduction at commit
`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`, calling the function in
`src/checkout/discounts.py` with yesterday's expiration returned a discounted total.

## Implications
The server needed expiration validation. [[Commits/Reject Expired Discounts]]
adds that check; UI behavior remains unverified.

## Related notes
- [[Repositories/Checkout Service]]
- [[Commits/Reject Expired Discounts]]
- [[Insights/Validate Discounts Before Totals]]
```
