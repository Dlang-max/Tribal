# Tribal MCP server

A local project server with two public MCP tools, one ephemeral Codex curator per
request, five private KB tools, and live graph activity. Different curator runs
search and prepare updates concurrently. Only validated publication coordinates
project revisions. Production storage uses SeaweedFS S3 and MySQL; no simulated
curator or fallback database is installed.

Follow [Connect Codex to Tribal](../../docs/connecting-codex-to-tribal.md) for setup.

| Route | Purpose |
| --- | --- |
| `/mcp` | Public `seed_agent_context` and `update_knowledge_base` |
| `/internal/mcp` | Active run-token-scoped internal tools |
| `/api/graph` | Current project note/link graph |
| `/api/activity` | Broadcast SSE default messages and comment heartbeats |
| `/healthz` | Process health; does not certify Codex login or storage availability |
| `/` | Optional built dashboard from `TRIBAL_GUI_DIRECTORY` |

Context curators see `search_notes`, `read_note`, `follow_link`, and
`get_note_spec`. Update curators also see `apply_changes`. Every private request
requires its own active `x-tribal-run-token`; context sessions cannot write even
if they call the tool directly. Tokens expire when runs complete, fail, or cancel.

The runtime starts `codex exec --json --ephemeral --ignore-user-config
--ignore-rules --skip-git-repo-check --sandbox read-only` in a temporary workspace
with a JSON output schema and only its private KB MCP configuration. Shell,
local-image, and web-search tools are disabled. Storage credentials and the
optional embedding `OPENAI_API_KEY` are omitted from the child environment;
Codex can use its own configured account or dedicated `CODEX_API_KEY`.
Requests and stored notes are untrusted evidence, not runtime instructions.
The model is optional via `TRIBAL_CODEX_MODEL`.

Final sources must match notes the run actually read. An `updated` result must
match an actual publication receipt, and retries reconcile saved receipts before
starting another process. Concurrent identical replay IDs share one local run;
different payloads under a used ID fail. Durable successful receipts belong to
MySQL. Timeouts/cancellation terminate and reap the process group, revoke tokens,
and publish a failed lifecycle event. Stderr/JSONL reasoning is never broadcast.

Activity reflects successful tool wrappers, with edges highlighted only after
verified traversal. Each browser has a bounded queue; a slow client drops older
events. SSE is best effort without durable replay: refresh `/api/graph` on connect,
reconnect, and `graph_changed`. Runs have independent IDs, names, and colors.

`create_server(curator=None)` preserves the original injectable public boundary
and returns explicit disconnected errors. `create_app(service=..., curator=...,
events=...)` supports controlled integration checks; the console entrypoint loads
real configured adapters. Missing project configuration, resources, or backend
dependencies fail explicitly. Embeddings are optional and never gate valid writes.
