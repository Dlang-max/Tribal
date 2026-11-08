# Project knowledge-base MCP interface — v1

Status: initial interface specification for the hackathon. The basic local
server exposes these tool signatures without authentication, but the curator
and knowledge-base backend are not connected. See
[`src/tribal-mcp-server`](../src/tribal-mcp-server/README.md).

Each project MCP server exposes two tools. Project identity comes from the server
connection, not a caller-supplied `project_id`. The local server does not
authenticate callers or implement project isolation.
The KB agent handles retrieval and curation; senders do not need to format notes.

## Shared conventions

- Strings described as required must be nonblank. Omit unavailable optional
  fields. Requests and responses are JSON objects.
- `repository`, when supplied, is a canonical repository URL, or an explicitly
  established project-local repository key for a repository without a remote.
  Resolve it within this project; do not guess from an ambiguous display name.
- `branch` is an optional exact short branch name and requires `repository`.
  Omit it for detached HEAD or project-wide work.
- Calls finish synchronously. There is no public job queue or polling tool in v1.

## seed_agent_context

Retrieve relevant context at turn start or whenever the task changes.

| Input | Required | Meaning |
| --- | --- | --- |
| `task` | Yes | Plain-text description of what the agent is working on or needs to know. |
| `repository` | No | Repository scope using the shared convention. |
| `branch` | No | Current branch, when known. |

The KB agent searches notes, follows useful links, and returns a concise Markdown
answer plus the notes it used. Include applicable project/repository guidance,
relevant work and handoffs, decisions, findings, and uncertainties. Repository
scope prioritizes relevant context while allowing related notes elsewhere in the
same project. Archived/superseded notes are used only when historical context is
relevant and are clearly identified. Retrieval makes no KB changes.

| Output | Meaning |
| --- | --- |
| `context` | Markdown context with source references and explicit unknowns. |
| `sources` | List of `{ "path": string, "title": string }` for notes actually used. Paths are vault-relative and include `.md`. |

If there is no relevant knowledge, return an honest explanation with an empty
`sources` list. This is a successful empty result, not permission to invent context.
Callers can ask for detail through another `task`; no extra read/search tool is
needed for the demo. Response-size limits are server configuration.

### Example

All examples below are fictional.

Request:

```json
{
  "task": "Add expiration validation for discount codes. What should I know?",
  "repository": "https://github.com/example/checkout",
  "branch": "feature/discount-validation"
}
```

Response:

```json
{
  "context": "Discount eligibility is handled in src/checkout/discounts.py. The repository guide describes the focused checks. Browser error handling has not been verified.",
  "sources": [
    {"path": "Repositories/Checkout Service.md", "title": "Checkout Service"},
    {"path": "Guides/Run Checkout Checks.md", "title": "Run Checkout Checks"}
  ]
}
```

## update_knowledge_base

Submit new information or request a correction. The KB agent decides how the
published notes should change.

| Input | Required | Meaning |
| --- | --- | --- |
| `request_id` | Yes | Unique replay key for this submission; a UUID is a suitable default. Reuse it for an identical retry. |
| `content` | Yes | Plain text or Markdown describing the observation/request, its evidence, and relevant limitations. This is not a published-note document. |
| `repository` | No | Repository context using the shared convention. |
| `branch` | No | Relevant branch, when known. |

Use the same tool for project/repository registration, branch intentions,
commits, merges, pushes, findings, insights, guides, handoffs, and corrections.
Include the trigger in `content` in ordinary language. For Git activity, include
full observed hashes and relevant source facts. Commit submissions include all
affected files with descriptions; report checks actually run and unknowns.
Do not require a note type, note path, YAML frontmatter, or prewritten section
headers. Do not invent missing source evidence.

The curator reads related notes, reviews the submission, chooses the note types,
and prepares any creates/revisions/archives. It validates the resulting notes and
links before saving. The sender requests outcomes; the curator owns note edits.
New repositories may be introduced through this tool. Missing information can
be requested without publishing incomplete notes.

| Output | Meaning |
| --- | --- |
| `status` | `updated`, `unchanged`, or `needs_information`. |
| `message` | Short explanation; for `needs_information`, specify what is missing. |
| `notes` | List of `{ "path": string, "action": "created" / "updated" / "archived" }`. Empty unless `status` is `updated`. |

`updated` means the listed Markdown changes were saved, not merely received.
Supersession is an update to the old note and usually creation of its replacement.
`unchanged` means review completed without a needed change. On
`needs_information`, send the supplemented request with a new `request_id`.
Embeddings may be refreshed later; valid Markdown writes do not wait for them.

Retain completed request results within the project so retrying the same ID and
payload returns the previous result. Reusing an ID with different content/scope
is an error. A failed or timed-out attempt must be reconciled before retrying
its writes; an error is not evidence that nothing was saved. Publication/recovery
implementation is separate work. For the demo, process one update at a time per
project and preserve note history through archive/supersede rather than hard delete.

### Example

Request:

```json
{
  "request_id": "discount-validation-commit-observation-demo",
  "repository": "https://github.com/example/checkout",
  "branch": "feature/discount-validation",
  "content": "Committed bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb: Reject expired discounts. Modified src/checkout/discounts.py to reject expired codes before total calculation. Modified tests/test_discounts.py to cover expired and unexpired codes. No tests were run. Browser behavior is unverified."
}
```

Response:

```json
{
  "status": "updated",
  "message": "Recorded the commit and updated the branch progress note.",
  "notes": [
    {"path": "Commits/Reject Expired Discounts.md", "action": "created"},
    {"path": "Branches/Checkout Discount Validation.md", "action": "updated"}
  ]
}
```

## Failures and boundaries

Use normal MCP/tool errors with a useful message for invalid arguments, denied
access, or failed dependencies/storage. Never present these as successful empty
retrieval or `unchanged`. Retry transient failures with the same update request ID.
No extra error-code framework is required for the hackathon.

The interface does not grant the curator repository access. Direct source access
versus bundled evidence remains a runtime choice. Preserve evidence attribution
and uncertainty; note validation alone does not prove a Git or testing claim.

Storage/search adapters and the curator's internal tools remain implementation
details. The [published-note specs](specs/v1/README.md) and
[validator](validation/v1/README.md) define the separate publication format.
