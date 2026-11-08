# Guide note — v1

Extends [the common format](common-note-format.md), with `type: guide`.
Provide reusable setup, testing, debugging, or working instructions. Guides are
retrieval entry points at turn start, not chronological activity logs.

## Additional metadata

| Key | Requirement |
| --- | --- |
| `repository` | Required for repository-specific instructions; omit for project-wide guidance. |
| `verified_at` | Optional quoted RFC 3339 timestamp of actually running/reviewing the procedure against its stated basis. Not automatically changed when the note is edited. |
| `verified_commit` | Optional full source commit hash against which instructions were checked; requires `repository`. |

## Required body sections

| Section | Required content |
| --- | --- |
| `Purpose and scope` | What the guide enables and where it applies. |
| `Prerequisites` | Known environment/tools/access; explicitly state gaps. |
| `Procedure` | Ordered actionable steps or concrete working conventions. |
| `Verification` | How to recognize success and which steps were actually checked, including source revision and limitations. Mark unverified instructions honestly. |
| `Troubleshooting` | Known failure cases/remedies, or an explicit lack of established troubleshooting guidance. |
| `Related notes` | Owning project/repository and supporting findings/decisions. |

Do not turn suggested commands into claims of executed checks. Revise guidance
when source evidence changes; preserve rationale and replace stale links through
the updater. Credentials and machine-specific secrets must not be included.

## Example

Example vault path: `Guides/Run Checkout Checks.md`.

````markdown
---
spec_version: 1
id: "guide-note-demo"
type: guide
title: Run Checkout Checks
project_id: "checkout-demo"
created_at: "2026-11-07T14:05:00Z"
updated_at: "2026-11-07T16:02:00Z"
status: active
repository: "[[Repositories/Checkout Service]]"
verified_at: "2026-11-07T16:01:00Z"
verified_commit: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
---
# Run Checkout Checks

## Purpose and scope
Run the discount-validation unit checks in the fictional checkout repository.

## Prerequisites
Use the repository's configured Python environment with its dependencies installed.
An exact installation procedure has not yet been documented.

## Procedure
1. Open a terminal at the repository root and activate its Python environment.
2. Run the focused command:

```sh
python -m pytest tests/test_discounts.py
```

## Verification
The command passed at the recorded commit in this example. This does not verify
the UI or production deployment. New runs should confirm their own exit status.

## Troubleshooting
If imports fail, check environment activation. Further remedies are not established.

## Related notes
- [[Projects/Checkout Platform]]
- [[Repositories/Checkout Service]]
- [[Findings/Expired Code Accepted]]
````
