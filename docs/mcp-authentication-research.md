# Tribal MCP authentication and demo topology

Updated: 2026-11-07. This note records the approved local demo approach and its limits. It is implementation guidance, not a claim of live GitHub login or a deployed cluster.

## Current demo

The approved implementation plan uses a management app plus one stateless worker Deployment and Service per project in local KinD. A single image runs either `python -m tribal management` or `python -m tribal worker`. The management app uses Authlib for browser GitHub sign-in; FastMCP's GitHub provider handles MCP OAuth, discovery, PKCE, token issuance, and validation. SQLite persists project ownership and status. A per-project allowlist is checked for each tool call. See the [approved Kubernetes demo plan](superpowers/plans/2026-11-07-kubernetes-project-mcp-demo.md) and [connection walkthrough](connecting-codex-to-tribal.md).

The current sample tool returns `get_project_context` with `sample: true`. It is not connected to the remote knowledge base or graph. Each project starts with its creator as its only allowed GitHub account. There are no roles, invitations, or enterprise SAML enforcement.

## OAuth and public URL

Both management and project MCP endpoints need the same GitHub OAuth application. Management uses `https://HOST/auth/callback`; project workers use callbacks below `https://HOST/projects/{project-id}/auth/callback`. Register `https://HOST/` as the callback URL with wildcard matching enabled so both callback paths are allowed. GitHub warns that wildcard matching permits callback subdirectories and subdomains; use a dedicated host that you control for this app. Do not enable this on a shared, untrusted callback domain.

Set `PUBLIC_BASE_URL` to the public HTTPS origin before starting management or creating projects. A changed tunnel host requires updating this setting and the OAuth app callback, restarting management, and recreating demo projects whose stored MCP URLs use the old origin. Quick Tunnels are temporary, provide a changing `trycloudflare.com` hostname, and are intended for development. The demo uses Streamable HTTP with stateless JSON responses, not SSE.

## Earlier shared-app proposal

The original research proposed a single shared application with project-specific MCP routes and left hosting and runtime open. That proposal is superseded for this local demo by separate per-project Kubernetes workers sharing one image. The broader product goal remains remote Tribal MCP access; this demo does not decide production hosting or knowledge-base integration.

## Verification boundary

Local source and packaging checks do not prove GitHub consent, a working OAuth callback, Kubernetes provisioning, or a live Codex connection. Report those as unverified unless they have actually been run with credentials and a cluster. KinD's default CNI may not enforce the included NetworkPolicies.
