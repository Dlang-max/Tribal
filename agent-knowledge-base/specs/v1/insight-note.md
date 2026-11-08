# Insight note — v1

Extends [the common format](common-note-format.md), with `type: insight`.
An insight is an interpretation, useful conclusion, or lesson. It is not proof
that a predicted event occurred or that an explanation is certainly correct.

## Additional metadata

`repository` is required for a repository-specific insight; omit it for a
project-wide insight. There are no other additional fields.

## Required body sections

| Section | Required content |
| --- | --- |
| `Insight` | The conclusion and its applicable scope. |
| `Basis` | Linked findings or concrete source evidence supporting it. Explicitly identify hypotheses and limitations. |
| `Implications` | How future work should use it and what could invalidate it. |
| `Related notes` | Owning project/repository and supporting/contradicting notes. |

The updater may consolidate compatible insights, retaining source links and
meaningful history. Contradictory evidence must be represented rather than
silently overwritten. Use a decision note when recording an adopted choice.

## Example

Example vault path: `Insights/Validate Discounts Before Totals.md`.

```markdown
---
spec_version: 1
id: "insight-note-demo"
type: insight
title: Validate Discounts Before Totals
project_id: "checkout-demo"
created_at: "2026-11-07T15:15:00Z"
updated_at: "2026-11-07T15:15:00Z"
status: active
repository: "[[Repositories/Checkout Service]]"
---
# Validate Discounts Before Totals

## Insight
Validate discount eligibility before calculating discounted order totals.

## Basis
[[Findings/Expired Code Accepted]] shows the local calculation accepted an
expired code. This example does not establish behavior in production.

## Implications
Future discount rules should run before total calculation. Revisit this guidance
if eligibility moves to a separate authoritative service.

## Related notes
- [[Repositories/Checkout Service]]
- [[Findings/Expired Code Accepted]]
- [[Decisions/Server Owns Discount Validation]]
```
