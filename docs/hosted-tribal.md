# Single-project hosted Tribal

The deployment target is the existing `tribal-demo` Droplet at `157.245.218.183`.
The selected hostname is `tribal-ub-hacking-2026.duckdns.org`.
The user explicitly selected a public React dashboard and public read APIs;
MCP alone requires a shared bearer token. See the verification section below
for the actual acceptance checkpoint.

## Services and configuration

`docker/Dockerfile` builds the existing React app with its lockfile and packages
it with the Python server, Codex CLI and validator. The server serves both the
dashboard and MCP. `docker/compose.hosted.yaml` and `docker/Caddyfile` add Caddy
HTTPS on ports 80/443 with persisted certificates. The app has no published port
and joins the existing `tribal-storage_default` network for copied storage.
Caddy permits only `/`, `/assets/*`, `/api/graph`, `/api/notes/*`, `/api/activity`,
`/healthz`, `/mcp` and `/mcp/`; private curator routes are unavailable publicly.
SSE and MCP streams are flushed immediately.

On the host, `/opt/tribal/app/compose.yaml`, `Caddyfile` and private `.env` run the
stack. The existing storage settings remain in `/opt/tribal/storage/app.env`.
The application persists server authentication in `tribal-app_codex-auth`, running
as UID 10001. No laptop Codex credentials or embedding key are copied. The stores
still contain the earlier verified snapshot; no automatic synchronization or
local caller cutover is performed.

The bearer token is generated privately and stored in host `/opt/tribal/app/.env`
and the operator's local `~/.config/tribal/tribal-ub-hacking-2026.env`, both mode
0600. The local file contains the MCP URL and `TRIBAL_MCP_BEARER_TOKEN` only.
Public React assets contain no bearer secret. Rotate by changing the host value,
recreating `app`, and updating authorized callers; previous values immediately
stop working after recreation. Do not delete persistent volumes during rotation.

## Client connection

Dashboard: `https://tribal-ub-hacking-2026.duckdns.org/`.
MCP: `https://tribal-ub-hacking-2026.duckdns.org/mcp`.

Load the private local credentials into the client process environment, then
configure a client that sends an Authorization bearer header. For Codex:

```toml
[mcp_servers.tribal-hosted]
url = "https://tribal-ub-hacking-2026.duckdns.org/mcp"
bearer_token_env_var = "TRIBAL_MCP_BEARER_TOKEN"
```

The server exposes exactly `seed_agent_context` and `update_knowledge_base`.
Missing/wrong bearer credentials receive `401` with `WWW-Authenticate: Bearer`.
This is shared-token authentication; it does not provide OAuth discovery or
per-participant revocation. Retry interrupted updates using the same request ID,
content and scope. Public health reports process status, not model/storage health.

## Operator commands

```bash
ssh -o ForwardAgent=no root@157.245.218.183
cd /opt/tribal/app
docker compose ps
docker compose logs --tail 50 app caddy
docker compose exec app codex login status
docker compose exec app codex login --device-auth
docker compose restart app caddy
```

Server login follows the official
[headless device authentication procedure](https://learn.chatgpt.com/docs/auth?surface=cli).
The browser sign-in is the operator's step. Optional embedding credentials remain
unconfigured; existing copied chunks are retained and new retrieval can use the
lexical index.

## Verification

The app and React frontend are deployed over trusted HTTPS. Public root, graph,
note reads and activity SSE work; an actual Chrome browser rendered the graph with
no page errors. MCP rejects missing/wrong credentials with 401, and configured
bearer credentials initialize and discover exactly the two public tools. Private
curator routes, including encoded path variants, return 404. The app and both
stores publish no ports; only Caddy publishes TCP 80/443. Caddy normalizes `/mcp/`
to `/mcp` internally, avoiding an HTTPS-to-HTTP backend redirect. These checks
passed after restarting the application/Caddy and after the KB migration.

The deployed app image is `tribal-demo:hosted-0c75c8c7bc3d`, Docker image ID
`sha256:e48229049017555de42f371a099a1c3d891276ecbf6ee1f5cec19ad5c84cc35c`.
The filtered source manifest SHA-256 is
`0c75c8c7bc3d478aaf7ca6d443d812a5f469b6b89ac96e4e00309a6a2a148fec`.
Its on-host record is `/opt/tribal/releases/0c75c8c7bc3d/source-manifest.sha256`;
the live Caddy configuration also includes the subsequent slash rewrite.
Caddy is pinned to
`caddy@sha256:78bd35025c7ba85961dd149ae670315129954e77abe2383ac47c89106b35ade9`.

At the user's request, `/home/daniel-lang/.codex/config.toml` updates the existing
`tribal-project` entry to the remote endpoint with a static Authorization bearer
header and `tool_timeout_sec = 360`. The config and its timestamped private backup
are mode 0600. Parsed TOML comparison preserved all unrelated settings. The Codex
CLI accepted the saved entry, and a new connection using its exact headers
successfully discovered the remote tools. Restart/reconnect Codex to load the
change into existing sessions. Static headers are supported by the
[official configuration documentation](https://learn.chatgpt.com/docs/extend/mcp).

### Latest local KB port

Snapshot captured at `2026-11-08T07:49:44.301352+00:00`. The remote current notes,
immutable revision history and replay receipts were verified as an earlier subset
of local authoritative data, with no divergent or remote-only authoritative rows.
The remote application was paused for a consistent private SQL/object backup at
`/opt/tribal/backups/before-local-kb-port-20261108T075102Z` before importing local data. Existing object bytes
were verified before copying; no remote objects were deleted.

The imported snapshot has 12 current notes, 57 revisions, 32 replay receipts,
119 derived chunks, one project and 57 S3 objects (640453 bytes). Every ordered
SQL row hash and every object SHA-256 matches the source; all 69 current/history
object references were verified. A private `port-verification.json` receipt is
retained in the remote backup directory. The app restarted successfully; the
public API and real browser both show 12 notes. Local services/data were preserved.
This remains a point-in-time port, not continuous replication.

### Pending model authentication

Server Codex login is not complete. The user must enable device-code sign-in in
ChatGPT Security Settings and complete a fresh server device login. The setting
is not exposed to the available tools. Earlier login processes were stopped by
application restarts; previous device codes should not be reused. No laptop model
credentials were copied. Live hosted seed/update/readback/replay remain unverified
until server model login succeeds. Process health, TLS and tool discovery do not
establish model execution. No commit or push was performed.
