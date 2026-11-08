# Decision note — v1

Extends [the common format](common-note-format.md), with `type: decision`.
Record a choice and why it was made. An agent's recommendation must not be
presented as an approved decision without observed approval or delegated authority.

## Additional metadata

| Key | Requirement |
| --- | --- |
| `repository` | Required for a repository-specific choice; omit for project-wide choices. |
| `decision_state` | Required `proposed`, `accepted`, or `rejected`. A replacement uses common `status: superseded` and `superseded_by`. |

## Required body sections

| Section | Required content |
| --- | --- |
| `Context` | Problem, constraints, and relevant evidence. |
| `Decision` | Proposed/adopted/rejected choice, matching `decision_state`. |
| `Rationale and alternatives` | Reasons and meaningful options considered; say when no alternatives were assessed. |
| `Authority` | Who approved/rejected it and source of that authority, or explicitly pending approval. |
| `Consequences` | Expected effects, tradeoffs, and follow-up; distinguish predictions from observed outcomes. |
| `Related notes` | Owning project/repository and supporting work/knowledge. |

## Example

Example vault path: `Decisions/Server Owns Discount Validation.md`.

```markdown
---
spec_version: 1
id: "decision-note-demo"
type: decision
title: Server Owns Discount Validation
project_id: "checkout-demo"
created_at: "2026-11-07T15:20:00Z"
updated_at: "2026-11-07T15:20:00Z"
status: active
repository: "[[Repositories/Checkout Service]]"
decision_state: proposed
---
# Server Owns Discount Validation

## Context
[[Findings/Expired Code Accepted]] identifies missing server-side validation.

## Decision
Propose keeping discount eligibility checks in the checkout service.

## Rationale and alternatives
Server checks can cover all clients. UI-only validation would leave direct API
calls unchecked. A separate validation service has not been evaluated.

## Authority
Agent recommendation only; owner approval is pending in this example.

## Consequences
Clients would handle validation errors. Cross-client behavior still needs review.

## Related notes
- [[Repositories/Checkout Service]]
- [[Insights/Validate Discounts Before Totals]]
```
