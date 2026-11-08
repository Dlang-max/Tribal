# Markdown note specifications — v1

A valid note satisfies [the common format](common-note-format.md) and exactly one
note-type specification. Required means required for publication in the KB;
incomplete submissions stay outside the published vault for the updater to resolve.

| `type` | Specification | Purpose |
| --- | --- | --- |
| `project` | [Project](project-note.md) | Project purpose, repositories, and entry points. |
| `repository` | [Repository](repository-note.md) | Repository functionality, structure, and responsibilities. |
| `branch` | [Branch](branch-note.md) | Intended work and current progress on a branch. |
| `commit` | [Commit](commit-note.md) | Committed changes, affected files, and rationale. |
| `merge` | [Merge](merge-note.md) | Completed integration and its result. |
| `push` | [Push](push-note.md) | Successful remote ref updates. |
| `finding` | [Finding](finding-note.md) | Observed behavior, results, and known issues with evidence. |
| `insight` | [Insight](insight-note.md) | Interpretations, useful conclusions, and their basis. |
| `decision` | [Decision](decision-note.md) | A choice, its rationale, and approval state. |
| `handoff` | [Handoff](handoff-note.md) | Current work, blockers, and next steps for another agent. |
| `guide` | [Guide](guide-note.md) | Setup, testing, debugging, and working conventions. |

## Trigger mapping

| Trigger | Expected interaction |
| --- | --- |
| Agent turn start | Retrieve relevant project/repository notes, guides, branch work, handoffs, decisions, and knowledge. No new note is required merely because a turn started. |
| Successful branch checkout or switch | Create/revise a branch note using the agent's explicit work intention. |
| Successful Git commit | Create/reuse the commit note, including affected files and explanations grounded in the committed diff. |
| Completed Git merge | Create/reuse a merge note with source, target, and result. Conflicted or unfinished merges are handoff/finding material. |
| Successful Git push, if collected | Record successful ref updates in a push note. |
| Agent turn end | Submit useful findings, insights, decisions, guide updates, and a handoff when work remains. The updater may conclude no change is needed. |

## Minimal publication checks

1. Parse one Markdown file and its YAML frontmatter using the common format.
2. Check common and type-specific fields and required body sections.
3. Verify project scope, note identity, repository references, and internal links
   against the existing vault plus the complete proposed batch.
4. Verify Git facts and other source claims where required by the type. A
   structurally valid document is not proof that its claims are true.
5. Apply revision/conflict checks and replay deduplication in the storage layer.
   The knowledge-base agent decides the content; application code enforces these
   mechanical rules. All caller interactions remain through the project MCP/KB agent.

The [v1 validator](../../validation/v1/README.md) implements read-only structural
and local cross-note checks. Source verification, storage publication, trigger
collection, model selection, chunking, synchronization, and hard-deletion policy
remain separate work.

## Examples

Examples use a fictional `checkout-demo` project and invented source facts.
Each example names its vault-relative path; together they form a linked example
vault. Their example identities/hashes are illustrative, not discovered facts.
They are examples of valid completed documents, not copy-and-fill templates:
replace their IDs and claims when creating actual notes.
