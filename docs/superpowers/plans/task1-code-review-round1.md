# Task 1 code review — round 1

## Verdict

**Specification: NEEDS CHANGES. Quality: NEEDS CHANGES.** One configuration-path mismatch remains in the reviewed Task 1 source.

## Finding

- **P2 — `PUBLIC_BASE_URL` accepts a path prefix that the worker does not mount.** In `src/tribal/settings.py:22-29`, `_public_root()` validates an absolute HTTP(S) URL and preserves any path component. In `src/tribal/project_worker.py:59-65`, that preserved value is used to advertise the MCP OAuth issuer and resource base, so `PUBLIC_BASE_URL=https://example.test/tribal` yields advertised project URLs under `/tribal/projects/<uuid>`. But the worker mounts its operational routes at `/projects/<uuid>` (`project_worker.py:112`) and puts discovery routes at the host root (`project_worker.py:111`); the management callback is similarly registered at `/auth/callback` while its redirect URL retains the configured prefix (`authentication.py:121-124`). The approved Task 1 contract describes `PUBLIC_BASE_URL` as the root and exposes `BASE/projects/UUID`. Reproduction: configure a nonempty path such as `https://example.test/tribal`, then compare the advertised resource/MCP and callback URLs with the routes registered by these apps; they do not include that prefix. Reject non-root paths in settings, or make all route mounting and ingress handling consistently support the prefix.

## Spec and quality review

- **GitHub identity trust:** The browser callback exchanges OAuth state via Authlib, fetches the authenticated `/user` response, validates its positive numeric ID and login, clears the prior session, and stores the verified numeric ID. Worker OAuth uses the pinned FastMCP GitHub provider; membership reads its verified `sub` claim and denies missing/nonmember identities before each tool call.
- **Sessions and CSRF:** Management sessions use Starlette's signed `SessionMiddleware`, HttpOnly default, SameSite=Lax, a 12-hour lifetime, and Secure for HTTPS. Login creates a fresh random session-bound CSRF value; logout enforces it using a constant-time comparison. The current helper contract is available for management mutation routes.
- **MCP token/resource scoping:** FastMCP 4.1.6 `GitHubProvider` supports the configured `base_url`, `resource_base_url`, `issuer_url`, signing key, scopes, and consent options. The code calls `get_well_known_routes("/mcp")` and mounts those host-root discovery routes, with per-project issuer/resource URLs. These APIs and imports were checked against the 4.1.6 wheel source.
- **Worker behavior:** The worker exposes only the no-argument `get_project_context()` sample payload, explicitly marks it `sample: true`, and configures FastMCP JSON responses and stateless HTTP. Health and readiness routes are present.
- **Dependencies/build:** `pyproject.toml` constrains Python to 3.12 and reads runtime dependencies from the pinned `requirements.txt`; FastMCP is pinned to 4.1.6. The separate lock contains the matching FastMCP/Starlette family. No package install, tests, Docker build, GitHub OAuth flow, or live deployment was run as part of this review.

## Review limits

This is a source review only. Docker and GitHub live behavior remain unverified; no claim is made that login, token exchange, discovery, or deployed routing succeeds end to end.
