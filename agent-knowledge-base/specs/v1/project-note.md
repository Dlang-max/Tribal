# Project note — v1

Extends [the common format](common-note-format.md), with `type: project`.
Maintain one active project overview per KB. Match it by authenticated project
identity; creating another overview must not duplicate the project.

## Additional metadata

None. Omit `repository` because this note describes the complete project.

## Required body sections

| Section | Required content |
| --- | --- |
| `Summary` | Purpose, users, and main intended behavior. |
| `Repositories` | At least one repository-note link and its responsibility. |
| `Working context` | Current priorities and constraints, distinguishing plans from completed work. |
| `Related notes` | Useful entry points such as repositories, guides, and decisions. |

Update the overview when project scope or priorities change. Detailed event
history belongs in linked notes rather than an ever-growing project log.

## Example

Example vault path: `Projects/Checkout Platform.md`.

```markdown
---
spec_version: 1
id: "project-note-demo"
type: project
title: Checkout Platform
project_id: "checkout-demo"
created_at: "2026-11-07T14:00:00Z"
updated_at: "2026-11-07T14:00:00Z"
status: active
---
# Checkout Platform

## Summary
Help customers place orders and apply eligible discount codes.

## Repositories
- [[Repositories/Checkout Service]] owns order totals and discount validation.

## Working context
Current work adds discount validation. Production deployment is not yet verified.

## Related notes
- [[Repositories/Checkout Service]]
- [[Guides/Run Checkout Checks]]
```
