# Repository note — v1

Extends [the common format](common-note-format.md), with `type: repository`.
Maintain one active overview per repository identity in this project. Do not
merge unrelated repositories because their names match.

## Additional metadata

| Key | Requirement |
| --- | --- |
| `repository_key` | Required nonblank durable project-local repository identity. Preserve across name/path changes; the collector maintains its verified mapping. |
| `remote_url` | Optional nonblank canonical repository URL. Omit for local-only repositories or unknown remotes. |

Omit the common `repository` field; a repository overview does not link to itself.

## Required body sections

| Section | Required content |
| --- | --- |
| `Purpose` | Functionality and boundaries of the repository. |
| `Structure` | Known important source paths/modules and their responsibilities. |
| `Working instructions` | Verified setup/testing instructions or links to guides; explicitly state unknowns. |
| `Dependencies and connections` | Known external systems or other repositories, or an explicit statement of what is unknown. |
| `Related notes` | The project note and relevant guides/work. |

Keep this as the durable repository entry point. Native repository URLs and
local directories are source references, not cross-project authorization.

## Example

Example vault path: `Repositories/Checkout Service.md`.

```markdown
---
spec_version: 1
id: "repository-note-demo"
type: repository
title: Checkout Service
project_id: "checkout-demo"
created_at: "2026-11-07T14:01:00Z"
updated_at: "2026-11-07T14:01:00Z"
status: active
repository_key: "checkout-service"
remote_url: "https://github.com/example/checkout"
---
# Checkout Service

## Purpose
Calculate order totals and validate discount codes for the checkout platform.

## Structure
- `src/checkout/discounts.py` validates discount eligibility.
- `tests/` contains the repository's automated checks.

## Working instructions
Follow [[Guides/Run Checkout Checks]] for local verification.

## Dependencies and connections
The service calls a catalog API. Its owning repository is not yet identified.

## Related notes
- [[Projects/Checkout Platform]]
- [[Guides/Run Checkout Checks]]
- [[Branches/Checkout Discount Validation]]
```
