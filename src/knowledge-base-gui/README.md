# Live knowledge explorer

Run the project server on `127.0.0.1:8000`, then from this directory:

```sh
npm ci
npm run dev
```

Vite proxies `/api` to the local server. The viewer requests `/api/graph`, loads selected note contents from `/api/notes/{encoded-note-id}`, and subscribes to `/api/activity` with native EventSource. Notes and link IDs come directly from the server. Curator names, task descriptions, colors and statuses come from observed server activity. No example graph or simulated curator is supplied when the server is unavailable.

`npm run build` typechecks and writes `dist/`; configure the server's optional GUI directory to this absolute directory when serving the built viewer. `npm run preview` previews assets only and does not proxy the API; use development mode or the backend for live data.

The full-height graph displays notes as small labeled dots and actual wikilinks as thin straight lines. Pan, zoom and fit controls are read-only. Tab to a dot and press Enter or Space, or click it, to open its complete Markdown source. The reader safely displays literal text, including frontmatter, and wraps long lines. Loading and failure states include retry. “Back to graph” or Escape returns to the previous graph position and zoom, with keyboard focus restored to the selected dot. The curator activity list stays visible beside the graph or reader, and stacks below on mobile. Opening a note in the viewer does not create curator activity.

Each reported node or edge visit fades independently over ten seconds using its server timestamp, with separate visible rings and strokes for overlapping runs. Completion and failure preserve existing trails until expiry. Stream reconnects refresh the graph snapshot; previous activity is not replayed by the server. The activity panel retains working runs and the latest 20 finished runs.

Independent tests live in `../../tests/knowledge_base_gui/`. Run them with `npm test` after those files are integrated.
