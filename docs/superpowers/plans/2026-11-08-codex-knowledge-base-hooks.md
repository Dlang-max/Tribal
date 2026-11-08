# Codex knowledge-base reminder hooks

The user's latest request replaces the earlier collector design with three simple
reminders: retrieve context at turn start, request a KB update after Git commands,
and review useful knowledge at turn end. The calling agent supplies evidence and
uses existing Tribal MCP tools; the server-side agents handle context and notes.

- [x] Replace the collector with `src/codex_kb_hooks.py`.
- [x] Remove `src/tribal-codex-hooks/`, including evidence/state/receipt helpers.
- [x] Register only UserPromptSubmit, PostToolUse/Bash, and Stop reminders.
- [x] Preserve unrelated hooks and other working-tree changes.
- [x] Rewrite `agent-knowledge-base/agents/codex-knowledge-base-hooks/AGENTS.md`.
- [x] Check syntax, representative reminder output, filtering, and Stop recursion.
- [ ] Native fresh-session dispatch and actual MCP delivery acceptance.

No new test files or dependencies. Earlier collector verification applies only to
the superseded implementation. Activation requires normal `/hooks` review/trust.
