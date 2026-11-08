# Connect Codex to Tribal

Tribal runs one local project server with concurrent server-side Codex curators.
Use a trusted machine: public MCP, graph, and activity routes do not authenticate
users. All published host ports below bind to loopback. Internal run tokens are
runtime scoping, not a replacement for deployment authentication.

## Start local storage

Install Python 3.12, Docker with Compose, and Node.js for the Codex CLI. From the
repository root:

```sh
docker compose -f docker/compose.yaml up -d mysql seaweed initialize-bucket
docker compose -f docker/compose.yaml ps
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install --no-deps .
```

Compose initializes MySQL's `tribal` database/user and the SeaweedFS S3 bucket
`tribal`. Data survives container restarts in named volumes. Sample storage
credentials are local demo defaults only. Configuration is shown in
[`docker/local.env.example`](../docker/local.env.example); copy it to a private
file outside the repository if needed. The server reads the process environment,
not an automatic dotenv file. Export variables explicitly or source the example:

```sh
set -a
. docker/local.env.example
set +a
```

The native server uses loopback MySQL port 3306 and Seaweed S3 port 8333. If ports
are occupied, change Compose's host mappings and `TRIBAL_MYSQL_PORT` or
`TRIBAL_S3_ENDPOINT_URL`. `TRIBAL_PROJECT_ID` is required and must match published
notes. One process represents one project; project selection is server configuration.

## Authenticate the server's Codex

```sh
npm install --global @openai/codex@0.167.0
codex --version
codex login
codex login status
.venv/bin/tribal-mcp-server
```

The runtime uses CLI flags verified against Codex 0.167.0. Use the account under
the operating-system user that starts the server. A separate `CODEX_HOME` may
isolate server authentication; set it for both `codex login` and server startup.
Alternatively provision Codex's dedicated `CODEX_API_KEY` through your secret
manager. Never put actual keys into tracked files or build images. An available
model may be selected with `TRIBAL_CODEX_MODEL`; otherwise Codex chooses its default.

The embedding key is separate: optional `OPENAI_API_KEY` enables direct HTTP
`text-embedding-3-small` indexing/search. It is not forwarded to curator children.
Without it, search stays lexical. Provider/index failures do not prevent valid
Markdown publication. No placeholder vectors are generated.

The server starts at `http://127.0.0.1:8000`; `HOST` and `PORT` override it.
`TRIBAL_INTERNAL_URL` must point back to this same server's `/internal/mcp` route
and remain reachable from the local Codex process. Keep bind/URL ports aligned.
`TRIBAL_CURATOR_TIMEOUT_SECONDS` defaults to 300.

Codex [noninteractive execution](https://learn.chatgpt.com/docs/non-interactive-mode)
and the [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
describe structured output, MCP headers/tool allowlists, and authentication behavior.
The runtime disables command execution, local images, and web search. Curators
have bundled request evidence and existing notes; they do not inspect a mounted
repository or GitHub. Supply observed source facts and preserve uncertainty.

## Connect a calling agent

In another terminal, using the calling agent's own Codex configuration:

```sh
codex mcp add tribal-project --url http://127.0.0.1:8000/mcp
codex mcp list
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/api/graph
```

The public tools are `seed_agent_context(task, repository?, branch?)` and
`update_knowledge_base(request_id, content, repository?, branch?)`. Reuse the same
request ID only for identical retries. A failed request may already have saved
notes; retries reconcile the durable publication receipt. Only updates with real
save receipts return `updated`. Missing dependencies or Codex login fail as tool
errors, never as successful empty retrieval.

## Run the dashboard

```sh
cd src/knowledge-base-gui
npm ci
npm run dev
```

Vite proxies `/api` to the local server. To serve a built dashboard from Python,
run `npm run build`, export `TRIBAL_GUI_DIRECTORY` to its absolute `dist` path,
and restart the server. Open `http://127.0.0.1:8000/`.
The GUI shows actual server curator runs, note reads, verified link traversals,
and saves. The SSE stream is best effort and graph snapshots recover reconnects.

## Optional application container

```sh
docker compose -f docker/compose.yaml --profile app build app
docker compose -f docker/compose.yaml --profile app run --rm app codex login --device-auth
docker compose -f docker/compose.yaml --profile app up -d
```

This image installs the real Codex CLI and ships specifications/validator.
Authentication is created at runtime in the `codex-auth` volume, never copied from
the host or included in an image layer. The server runs as UID 10001. The app
container connects to service names `mysql` and `seaweed`; its private MCP URL
uses container loopback. The default image exposes APIs; build/serve the optional
GUI separately or mount a built directory and set `TRIBAL_GUI_DIRECTORY`.

Docker build and live storage/Codex operation require the operator's available
Docker daemon, image registry access, and authenticated Codex account. Controlled
integration tests do not call OpenAI or require login. This runtime is a local
demo and does not include Kubernetes or hosted multiuser isolation.
