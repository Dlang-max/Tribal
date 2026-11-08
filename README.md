# Tribal

Tribal is a hackathon project for sharing project knowledge between AI agents.
The current basic MCP server runs locally without GitHub sign-in. See
[Tribal MCP server](src/tribal-mcp-server/README.md) for startup and connection
instructions.

The two MCP tools are exposed, but the knowledge-curation agent, Markdown storage,
search, and realtime GUI integration are not connected yet. Tool calls return an
explicit error until a curator is implemented.

The previous GitHub-authenticated server and its project-worker deployment
resources have been removed. See [Connect Codex to Tribal](docs/connecting-codex-to-tribal.md)
for the local connection steps. Earlier design and review documents are historical.

The [knowledge-base specifications and validator](agent-knowledge-base/README.md)
define and check the planned Markdown note format.
