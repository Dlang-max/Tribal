# Tribal

Tribal shares project knowledge between AI agents through Markdown notes.
Each public MCP request starts an independent server-side Codex curator. Curators
search, read, and traverse notes concurrently; validated publication checks revisions
and coordinates only the save. SeaweedFS stores immutable Markdown, while MySQL
tracks current revisions, replay receipts, and optional embeddings.

The two public tools are `seed_agent_context` and `update_knowledge_base`.
A live graph and SSE feed show observed curator tool activity. The server runs in
a trusted local environment, with optional bearer authentication for hosted MCP.

Follow [Connect Codex to Tribal](docs/connecting-codex-to-tribal.md) for local
MySQL/SeaweedFS setup, server-side Codex authentication, optional embeddings, and
the dashboard. See the [server README](src/tribal-mcp-server/README.md),
[MCP interface](agent-knowledge-base/mcp-interface-v1.md), and
[publication/storage contract](agent-knowledge-base/storage-v1.md) for details.

The [note specifications and validator](agent-knowledge-base/README.md) define
the published Markdown format. Earlier authentication/Kubernetes design documents
are historical; this local runtime does not use Kubernetes.

## Hosted deployment

See [Hosted Tribal](docs/hosted-tribal.md) for HTTPS configuration, bearer-protected
MCP access, public dashboard reads, and the recorded deployment acceptance limits.

## Standalone frontend preview

The earlier frontend workspace is also available from the repository root. Its
Overview, Repositories, Agents and Tasks, Knowledge Explorer, and Settings screens
use sample data. The deployed dashboard remains in `src/knowledge-base-gui/`.

With Node.js 22.12 or newer and npm, run the preview from the repository root:

```sh
npm ci
npm run dev
```

Run `npm test`, `npm run build`, and `npm run test:e2e` at the root to check the
preview. Run `npm test` and `npm run build` in `src/knowledge-base-gui/` to check
the live dashboard. The preview and dashboard use separate test configurations.
