# Tribal MCP server

A minimal, unauthenticated project MCP endpoint. It exposes
`seed_agent_context(task, repository?, branch?)` and
`update_knowledge_base(request_id, content, repository?, branch?)`. The server
accepts the existing FastMCP dependency; it does not need GitHub, Kubernetes,
a database, or OAuth configuration.

From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/pip install .
.venv/bin/tribal-mcp-server
```

In another terminal:

```sh
codex mcp add tribal-project --url http://127.0.0.1:8000/mcp
```

The server listens only on localhost. It has no authentication; use it only in a
trusted environment. One running instance represents one project; project selection
and multi-user isolation are not implemented.

The source lives at `Tribal/src/tribal-mcp-server/server.py`. It can also be
started directly with `.venv/bin/python src/tribal-mcp-server/server.py`.
`HOST` overrides the default bind address. Container startup and connection
steps are documented in [Connect Codex to Tribal](../../docs/connecting-codex-to-tribal.md).

The curation agent, knowledge storage, search, and realtime GUI activity stream
are not implemented or connected. Both tools return an MCP error until a curator
is supplied to `create_server`. They never report a successful update or an empty
search when the backend is unavailable. The `Curator` protocol is the integration
point for future curation runs and their activity events. The curator is responsible
for storage, request replay, and the documented result semantics in
[`mcp-interface-v1.md`](../../agent-knowledge-base/mcp-interface-v1.md).
