# Tribal MCP authentication: hackathon approach

Updated: 2026-11-07. Research and proposal only; no authentication has been implemented or exercised. The user clarified that this is a hackathon idea and the solution should stay simple.

## What we need to demonstrate

A person signs in with GitHub, creates a project on Tribal, and gets a remote MCP URL. They connect Codex to that URL, authorize it through GitHub, and the agent can access that project's context. Tribal hosts the app.

## Small proposed implementation

- Run one hosted application with a project-specific MCP route, such as `/projects/<id>/mcp`. Project creation adds a record and route binding in that app.
- Use an existing MCP OAuth integration with GitHub sign-in. Keep its authorization endpoints in the same deployment when supported. Let the integration handle discovery, browser callbacks, PKCE, token issuance, and validation.
- Store a small project record: ID, name, creator's GitHub account ID, allowed GitHub account IDs, and knowledge-base binding. Reuse existing project IDs; keep access settings separate from ontology fields. The creator is initially allowed; a simple configured access list is enough for demo collaborators.
- Give allowed members the same context access. Check the project access list on each request and bind its knowledge-base calls to that project.
- Use one simple persistent store for project/access records; select it during implementation. Use clearly labeled sample context while the knowledge-base service is unavailable.

This replaces the earlier recommendation to begin with a separate authorization-broker service and a detailed role system. Runtime/library choice remains an implementation decision. FastMCP's GitHub OAuth bridge is a candidate if Python is used; verify it works with the project's endpoint/resource configuration before adopting it. [FastMCP OAuth proxy](https://gofastmcp.com/docs/servers/auth/oauth-proxy).

## How authentication works

The developer authorizes their MCP client in a browser. The client then sends a Tribal access token on agent requests. The existing OAuth integration should issue tokens for the intended MCP resource and validate them on every request; GitHub API tokens stay inside the sign-in integration. [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization).

GitHub supplies the person's identity through its OAuth callback and authenticated user API. Store the account ID as the identity key. [GitHub OAuth](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps), [authenticated user API](https://docs.github.com/en/rest/users/users#get-the-authenticated-user).

Codex documents remote MCP OAuth and `codex mcp login <server-name>`, so we can use its existing login flow. [Official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

For this demo, “GitHub SSO” is interpreted as Sign in with GitHub. Enterprise organization SAML enforcement is deferred under this proposed scope; it is a separate GitHub feature. [GitHub apps and SSO](https://docs.github.com/en/enterprise-cloud@latest/authentication/authenticating-with-single-sign-on/authorizing-an-app-for-single-sign-on).

## Keep the demo focused

Use the auth library's standard credential lifecycle. Leave custom roles, invitation workflows, unattended service accounts, separate auth infrastructure, per-project containers, and additional Kubernetes work for later.

The basic checks are: GitHub login works, an allowed agent can read context, a nonmember is denied, and one project cannot retrieve another project's context. No live authentication or hosting check has been performed yet.

See the [four small work items](work-items/github-authenticated-project-mcp-servers.md).
