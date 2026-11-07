# Hosted project MCP servers: hackathon work items

Updated: 2026-11-07. Proposed implementation tasks only. This four-item backlog replaces the earlier eight-item AUTH-01 through AUTH-08 proposal after the user clarified the hackathon scope. Tribal hosts the app; GitHub sign-in authorizes developers and their agents. See the [short authentication research](../mcp-authentication-research.md).

## Shared assumptions

Use one hosted app, project-specific MCP routes, an existing GitHub OAuth integration, and a simple allowed-user list. All allowed members have the same context access. Runtime/library choice belongs to the auth implementer; use that same runtime throughout.

Keep integration to three small boundaries: auth returns a verified GitHub account ID, project lookup returns that project's access list and knowledge-base binding, and MCP context access receives the resolved project ID. Agree on their concrete shapes when work starts. Tasks 1–3 can be developed independently using substitutes; integration uses the actual implementations.

## DEMO-01 — Get GitHub login working for an MCP client

**Own:** `src/auth/`.

**Build:** Choose a small existing MCP OAuth integration with GitHub support and configure it in the app. Support browser sign-in, expose the verified GitHub account ID for project creation/access checks, and let the library handle MCP metadata, PKCE, and credentials. Document the GitHub App setup and required environment variables. Start with a single example project endpoint.

**Done when:** Codex can authorize the example endpoint through GitHub and make an authenticated request. Missing or invalid credentials fail. Tokens are valid for the intended MCP resource; GitHub secrets remain on the service.

**Dependency:** None; use a fixed example project and allowed account initially. Share the runtime choice early with the other implementers.

## DEMO-02 — Create projects and return MCP URLs

**Own:** `src/projects/`.

**Build:** Add a minimal authenticated create-project operation. Save the project ID, name, creator's verified GitHub account ID, allowed account IDs, and knowledge-base binding in a simple persistent store. Initially allow the creator. Return its hosted MCP URL and provide lookup/access-list helpers. A configured list of collaborators is enough; no invitation UI is required.

**Done when:** A signed-in person can create two projects with distinct URLs, and both records survive an app restart. Anonymous creation fails. Lookup returns only the requested project's configuration.

**Dependency:** Develop with a substitute verified identity. Connect DEMO-01 for the real flow.

## DEMO-03 — Serve context through protected project MCP routes

**Own:** `src/mcp/`.

**Build:** Serve `/projects/<id>/mcp` using the chosen MCP library. Resolve the project from the route, require a valid token for the endpoint's configured resource, and check its allowed GitHub account IDs. Bind all context operations to that project. Connect the context service if available; otherwise expose a clearly labeled sample read operation. Writes, when available, use the context updater.

**Done when:** An allowed user can connect and read their project's context, a nonmember is denied, and changing a route or tool argument cannot expose another project's data. Sample data is clearly identified.

**Dependency:** Develop with substitute identity/project/context adapters. Integrate DEMO-01 and DEMO-02 for real access.

## DEMO-04 — Run the hosted demo and document connection

**Own:** `src/app/` for app assembly and `docs/connecting-codex-to-tribal.md`. Add container assets under `docker/` only if the hosting method needs them.

**Build:** Wire the three components into one app, document running it at an HTTPS URL, and provide copyable Codex add-server/login commands. Include GitHub callback setup and a short demonstration: sign in, create a project, connect an agent, read context. Choose the simplest available hosting method.

**Done when:** Someone can follow the instructions and complete the demo. Also show a nonmember being denied. State whether the context backend is real or illustrative.

**Dependency:** Documentation can start immediately; the real demo needs DEMO-01 through DEMO-03. Do not add another service or Kubernetes setup unless hosting actually requires it.

## Verification

Use manual demo checks. Do not write tests unless explicitly requested, following repository guidance. No implementation, deployment, or live login has been performed by this planning task.
