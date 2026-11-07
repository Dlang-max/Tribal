# Task 1 code review — round 2

## Verdict

**Specification: GREEN LIGHT. Quality: GREEN LIGHT.** The round-one `PUBLIC_BASE_URL` path-prefix finding is fixed. I found no remaining Task 1 blocker in the reviewed settings, management authentication, or project worker code.

## Round-one finding resolution

- **P2 — non-root public URL paths:** Resolved. `src/tribal/settings.py` now accepts only an origin URL with an empty path or `/`, rejects other path prefixes, and normalizes the accepted root to `scheme://netloc`. This matches the approved contract: project endpoints live under `/projects/<uuid>`, while OAuth discovery routes are registered at the host root. A URL such as `https://example.test/tribal` now raises `SettingsError` before its prefix can disagree with the mounted routes.

## Regression review

- **Management callback and redirects:** The normalized origin keeps `urljoin(settings.public_base_url + "/", "auth/callback")` aligned with the registered `/auth/callback` route. Callback success/failure session handling, verified positive numeric GitHub IDs, session clearing before identity storage, and the session-bound logout CSRF check are unchanged.
- **Worker URLs and route mounting:** `build_project_worker()` still derives the issuer/resource base as `<origin>/projects/<uuid>`, mounts MCP and OAuth operations at that project prefix, and registers library-generated discovery routes at the host root. Health/readiness and stateless JSON MCP configuration are unchanged.
- **Project authorization:** The worker middleware still reads the verified FastMCP token subject and denies unavailable or non-allowlisted GitHub IDs before invoking a tool. No auth/worker regression from the settings change was found.
- **Settings behavior:** Root URLs with or without a trailing slash normalize to the same origin. Worker-only settings can still omit `SESSION_SIGNING_KEY`; management session middleware still requires it.

## Review limits

This was a source review of the supplied Task 1 snapshot and repository code. I did not run tests or exercise live GitHub OAuth, deployed ingress, Kubernetes, or a Codex client connection. Those remain outside this code-review verdict.
