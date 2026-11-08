# Single-project HTTPS hosting and MCP bearer validation

The user authorizes deployment of the existing backend and React frontend to the
existing tribal-demo Droplet and explicitly chooses a public dashboard/read API
with bearer protection only for MCP. Reuse the copied storage without replacing
it or changing local connections. Preserve the current modified source tree.

Add optional TRIBAL_MCP_BEARER_TOKEN to server settings. When configured, the
public HTTP MCP transport rejects missing, malformed, duplicate or incorrect
Authorization headers with 401 and WWW-Authenticate before MCP dispatch. Compare
SHA-256 token digests in constant time; never accept query-string credentials.
Local deployments without that setting retain their existing behavior. Hosted
Compose requires the setting. Private per-curator run tokens remain separate.

Build React into the existing runtime image using its lockfile. A Caddy container
provides automatic HTTPS for tribal-ub-hacking-2026.duckdns.org, proxies only the
known dashboard/assets/read API/health/MCP routes and streams immediately. No
internal curator route or storage port is published. Persist Caddy certificates
and fresh server Codex authentication. Generate a new MCP bearer secret privately.
Use the official device login flow rather than transferring laptop model auth.

This simple shared-token approach fits the one-project hackathon request.
Per-participant OAuth, accounts and a management dashboard are deferred. Proxy-only
authentication was rejected because the user requested validation in the MCP
server itself. The existing app can serve the built frontend, avoiding a separate
Node production server.

Verify actual HTTP rejection/acceptance, exact two-tool discovery, public React
assets/read APIs, blocked private paths, trusted TLS, live curator retrieval and
publication, and restart persistence. Do not author tests; use existing suites and
manual protocol checks. Deployment and model authentication are separate milestones.
