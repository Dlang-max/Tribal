# Tribal knowledge-base bootstrap agent

Use these instructions when explicitly asked to build a project's initial
knowledge base through Tribal. You are the calling agent: inspect the available
repositories and submit grounded evidence. Tribal's server-side curator chooses
and publishes the Markdown notes.

This guide populates the KB behind an existing project MCP connection. It does
not provision a server, create a database, or change client configuration. If
the connection is missing, report that prerequisite and refer to the
[connection guide](../../../docs/connecting-codex-to-tribal.md).

## 1. Establish the project and connection

- Read the user's request and the applicable repository `AGENTS.md` files.
  Follow their instructions when inspecting source or running checks.
- Identify the project purpose, intended users, repository roots, and scope of
  the requested bootstrap. Ask only for information that available evidence
  cannot establish. Do not assume the repository name is the project name.
- Use the intended project's MCP connection. Project identity is configured on
  the server; neither public tool accepts a caller-supplied `project_id`.
  If the connection's project is ambiguous, resolve it before writing.
- Discover the public tools: `seed_agent_context` and `update_knowledge_base`.
  A tool error means retrieval failed; it does not establish that the KB is empty.

## 2. Retrieve before adding anything

Call `seed_agent_context` with a task that explicitly asks for the existing
project overview, repository overviews, working instructions, decisions, and
gaps relevant to initial setup. Supply `repository` when its identity is known.

`repository` must be a canonical repository URL or an explicitly established
project-local key for a repository without a remote. Do not submit a local
directory or guess a key from an ambiguous name. If identity is unresolved,
omit the optional scope and describe the uncertainty in the request content.
`branch` is the exact short branch name, requires `repository`, and should be
omitted for detached HEAD or project-wide work.

Read both the returned `context` and `sources`. An empty sources list means no
relevant context was returned for that query; it does not prove the whole KB is
empty. Broaden retrieval if needed. Preserve useful existing knowledge and ask
the curator to extend or correct it instead of duplicating overviews or resetting
the KB. Never clear an existing KB as part of bootstrap.

## 3. Inspect the repositories and collect evidence

Start with READMEs, repository instructions, manifests/lockfiles, important
source entry points, configuration examples, and relevant architecture or setup
documentation. Inspect enough implementation to explain the main behavior and
how the components connect. Use read-only Git inspection to establish repository
identity, branch, and full HEAD hash when available. Distinguish working-tree
observations from committed source, especially if there are local changes.

Prepare a concise evidence summary covering:

- **Project:** purpose, users, intended behavior, current priorities, and constraints.
- **Repositories:** each inspected repository's identity, responsibility,
  important paths/modules, and connections to other repositories or services.
- **Working instructions:** prerequisites, documented setup/run/check commands,
  and applicable development conventions.
- **Current state:** implemented behavior, plans, known limitations, and open
  questions, with the source paths and revisions supporting each claim.
- **Verification:** checks actually run, their outcomes, and what remains
  unverified. Label commands found in documentation as documented instructions
  unless you executed them and observed the result.

Prefer durable information that helps the next agent work. Follow useful links
and inspect relevant components without copying the whole repository into the
submission. Do not fabricate decisions, historical Git events, test results,
deployment status, or details about repositories you have not inspected. Do not
include credentials, `.env` values, or unrelated private material.

The curator currently receives your submitted evidence and existing KB notes;
it cannot inspect your checkout or fetch GitHub sources itself. Supply concrete
observations, source references, and limitations rather than asking it to scan
a local path or URL.

## 4. Submit the initial knowledge through Tribal

Use `update_knowledge_base(request_id, content, repository?, branch?)`. Generate
a fresh unique request ID, such as a UUID, and retain the exact ID and payload
until the outcome is known. Put the evidence in freeform `content`; callers do
not need to write YAML, choose note IDs/paths, or call private curator tools.

Request one project overview linked to an overview for each evidenced repository,
creating or revising existing notes as appropriate. Include repository purpose,
structure, working instructions, dependencies, and known gaps. Request additional
guides, decisions, or findings only when the evidence supports them. The curator
handles note specifications, links, validation, revisions, and publication.

Use the following outline for `content`, replacing every placeholder with
observed facts or an explicit unknown before submission:

```text
Trigger: first-time project knowledge-base bootstrap.
Project: <confirmed name, purpose, users, and scope>.
Repository evidence: <canonical URLs/established keys, inspected paths,
full observed revisions, and any local-change limitations>.
Implemented behavior and structure: <observations with supporting source paths>.
Working instructions: <documented prerequisites/commands and conventions>.
Dependencies and connections: <observed systems and repository relationships>.
Current priorities and constraints: <attributed plans and confirmed requirements>.
Checks actually run: <commands and results, or explicitly none>.
Unknowns and conflicts: <missing, stale, contradictory, or unverified information>.
Requested outcome: create or revise the project/repository entry points and
useful supported guides, preserve existing valid knowledge, and link the notes.
```

For a small project, submit the initial linked overview together. If more evidence
must be gathered later, use separate focused submissions and fresh request IDs.
Do not create an exhaustive event history just to populate the graph.

## 5. Handle the result and verify retrieval

- `updated`: the listed note changes were saved. Record the returned paths and
  actions; this does not prove embeddings or external deployment succeeded.
- `unchanged`: review completed without a needed change. Do not force duplicate
  notes; retrieve again to confirm the existing context covers the request.
- `needs_information`: address the stated gaps and send the supplemented payload
  under a new request ID. If the evidence is unavailable, report the blocker.
- Error or timeout: do not assume nothing was saved. Retry/reconcile using the
  same request ID and identical content and scope. Never change the payload
  under that ID or blindly resubmit under a fresh ID.

After publication, call `seed_agent_context` again, asking for the project's
purpose, repository map, working instructions, and remaining uncertainties.
Check that the returned answer and cited sources cover the bootstrap evidence.
If information is missing or wrong, submit a focused correction with evidence
and a new request ID. Stop and report persistent tool failures or missing evidence.

Finish by reporting the saved or reused note paths, what was verified through
retrieval, and any remaining gaps. Continue ordinary work by retrieving relevant
context at turn start and submitting useful verified changes as work completes;
automatic client triggers are not part of this guide.

## References

- [Public MCP contract](../../mcp-interface-v1.md)
- [Published-note specifications](../../specs/v1/README.md)
- [Project note](../../specs/v1/project-note.md)
- [Repository note](../../specs/v1/repository-note.md)
- [Guide note](../../specs/v1/guide-note.md)
