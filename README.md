# Tribal frontend preview

Tribal is a local, illustrative workspace for exploring how shared repository
context could be organized for AI agents. The Overview, Repositories, Agents
and Tasks, Knowledge Explorer, and Settings screens use sample data only. The
preview has no live repository, agent, or knowledge-service connections.

## Run locally

Requirements: Node.js 22.12 or newer and npm.

```sh
npm ci
npm run dev
```

Open the local URL printed by Vite. To check the production bundle, run
`npm run typecheck` and `npm run build`, then use `npm run preview` to serve the
built files locally.

The Knowledge Explorer supports switching between sample projects, searching
and filtering entities, panning and zooming the graph, and inspecting entity
and relationship fields. It is read-only; no changes are saved.
