# Simple Codex reminders for a Tribal knowledge base

Use three lightweight hooks to remind the calling agent to ask the appropriate
Tribal agent for context or a KB update. The calling agent gathers relevant
evidence and uses its existing public MCP tools. Tribal's server-side agents
retrieve context and curate the notes.

## Hook behavior

| When | Codex event | Reminder |
| --- | --- | --- |
| A user turn starts | `UserPromptSubmit` | Ask the context agent for task-relevant context using `seed_agent_context`. |
| After a Git command | `PostToolUse`, matcher `^Bash$` | Inspect the command result and ask the KB agent to update useful knowledge using `update_knowledge_base`. |
| A turn ends | `Stop` | Ask the KB agent to record useful new findings, decisions, changes, checks, or handoff context. |

The hooks only provide reminders. Evidence gathering, checking command results,
request IDs, retries, and avoiding duplicate submissions belong to the calling
agent. A read-only Git command, failed operation, or turn without useful new
knowledge does not require a KB update.

Do not add a Git evidence collector, delivery database, background worker, or
separate agent session for these hooks. The existing MCP tools already route the
request to Tribal's corresponding server-side agent; no new subagent is needed.

## Existing implementation and configuration

- Source: [`src/codex_kb_hooks.py`](../../../src/codex_kb_hooks.py).
- Registration: [`.codex/hooks.json`](../../../.codex/hooks.json).
- Scope and connection: [`.codex/tribal-hooks.json`](../../../.codex/tribal-hooks.json).

The script supports `turn-start`, `after-git`, and `turn-end` modes. Commands in
`hooks.json` use the absolute interpreter and script paths. Update them and the
checkout setting if the repository moves. Keep source under `src/`; a separate
hooks source folder is unnecessary.

Before changing configuration, read the repository's applicable `AGENTS.md` and
relevant notes in `../UB Hacking 2026/`, particularly
`Design/Repository Context Triggers.md` and `Decisions/Tribal Decision Log.md`.
Confirm the installed Codex version and intended existing connection with
`codex --version` and `codex mcp list`.

For this project, use connection `tribal-project`, canonical repository
`https://github.com/Dlang-max/Tribal`, and the existing default endpoint
`http://127.0.0.1:8000/mcp`. If the connection is missing, report the limitation.
Do not provision a server or replace authentication as part of hook setup.

Preserve unrelated hooks and user configuration. Use one hook representation per
configuration layer. Open a fresh Codex session in the checkout and use `/hooks`
to review/trust the commands; `features.hooks` must be enabled. Do not bypass trust
or change tool approval policies.

## Reminders and recursion

Command hooks read one event JSON object from stdin. Use `cwd` to ignore events
outside the configured checkout. Identified child-agent events are ignored.

`UserPromptSubmit` returns `hookSpecificOutput.additionalContext` asking the
calling agent to retrieve context for the actual task and use its returned context
and sources. A greeting is not a substitute for the task.

`PostToolUse` uses `^Bash$`, which covers supported Codex shell/unified-exec calls.
Inspect `tool_input.command` inside the handler to recognize Git commands,
including `git -C` and `git -c`; merely quoted command examples must not count as
execution. The reminder tells the calling agent to inspect the actual result
once the command finishes. The hook does not infer success or parse Git outcomes.
Arbitrary scripts and wrappers are outside the simple recognizer's coverage.

`Stop` requests one continuation with `decision: "block"` and a short `reason`.
Return `{}` when `stop_hook_active` is true so it cannot keep requesting updates.
Prefix the continuation with `TRIBAL_KB_TURN_END:` and ignore that prompt in the
turn-start hook. After updating or deciding there is nothing new, return the
original user-facing answer.

## Calling the corresponding Tribal agent

Retrieve task context through `seed_agent_context`:

```json
{
  "task": "The actual current user task",
  "repository": "https://github.com/Dlang-max/Tribal"
}
```

Ask the KB agent to review useful knowledge through `update_knowledge_base`:

```json
{
  "request_id": "a-new-unique-request-id",
  "repository": "https://github.com/Dlang-max/Tribal",
  "content": "Useful verified changes, findings, decisions, checks actually run, relevant source evidence, and remaining uncertainty."
}
```

Include the exact short `branch` when relevant; omit it for detached HEAD or
project-wide work. Do not pass `project_id` or use a local directory as repository.
For Git changes, provide the relevant full revisions, affected files and their
meaning, and actual outcomes. Pending/conflicted merges and rejected/dry-run
pushes must not be described as successful operations. The curator cannot inspect
the caller's checkout itself.

Read tool results. Retry errors/timeouts with the same request ID and identical
payload; new evidence after `needs_information` uses a new ID. Do not resubmit
already-recorded Git facts as new turn-end occurrences. The curator owns note
selection, formatting, links, and publication; do not submit prewritten note YAML.

## Verification

Check Python syntax and parse the JSON configuration. Manually invoke the script
with representative turn-start, Git/non-Git, turn-end, repeated-Stop, and
out-of-scope event objects. Do not author tests unless explicitly requested.
Then verify native dispatch and actual MCP calls in a fresh trusted Codex session.
Report these separately: valid configuration and manual reminder output do not
establish end-to-end delivery.

The simplified reminders replace the earlier collector at the user's request.
Current manual checks passed; native fresh-session dispatch and end-to-end MCP
acceptance remain unverified.

References: [public MCP contract](../../mcp-interface-v1.md),
[Codex hooks](https://learn.chatgpt.com/docs/hooks), and
[advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced).
