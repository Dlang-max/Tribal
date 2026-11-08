# Connect Codex to Tribal

Tribal's basic MCP server lives in `src/tribal-mcp-server/` inside the repository’s `src/` directory.
It runs without GitHub sign-in, Kubernetes, or project-worker provisioning.

From the Tribal repository root:

```sh
python3.12 -m venv .venv
.venv/bin/pip install .
.venv/bin/tribal-mcp-server
```

Alternatively, run `.venv/bin/python src/tribal-mcp-server/src/server.py` after
installing dependencies. The HTTP MCP endpoint is `http://127.0.0.1:8000/mcp`.

In another terminal:

```sh
codex mcp add tribal-project --url http://127.0.0.1:8000/mcp
codex mcp list
```

There is no MCP login step. The available tools are `seed_agent_context` and
`update_knowledge_base`. Both return an explicit MCP error until a curation agent
is supplied to `create_server`; storage, search, replay, and realtime GUI activity
are still integration work.

The server defaults to localhost. `HOST` can override the bind address. It has no
authentication and is intended for a trusted local environment.

## Optional container

```sh
docker build -f docker/Dockerfile -t tribal-mcp:local .
docker run --rm -p 127.0.0.1:8000:8000 tribal-mcp:local
```

The container binds internally to all interfaces; the example publishes the port
only on the host's loopback interface. No Kubernetes resources are required.
