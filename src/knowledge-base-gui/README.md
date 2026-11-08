# Live knowledge explorer

Run the project server on `127.0.0.1:8000`, then from this directory:

```sh
npm ci
npm run dev
```

Vite proxies `/api` to the local server. The viewer requests `/api/graph` and subscribes to `/api/activity` with native EventSource. Notes and link IDs come directly from the server. Curator names, task descriptions, colors and statuses come from observed server activity. No example graph or simulated curator is supplied when the server is unavailable.

`npm run build` typechecks and writes `dist/`; configure the server's optional GUI directory to this absolute directory when serving the built viewer. `npm run preview` previews assets only and does not proxy the API; use development mode or the backend for live data.

The note list provides a keyboard alternative to graph selection. Search and note-type filters apply to both views. Selecting a note exposes metadata and linked neighbors; the graph endpoint does not include Markdown bodies. Each reported node or edge visit fades independently over ten seconds using its server timestamp, with separate visible colors for overlapping runs. Completion and failure preserve existing trails until expiry. Stream reconnects refresh the graph snapshot; previous activity is not replayed by the server. The activity panel retains working runs and the latest 20 finished runs.

Independent tests live in `../../tests/knowledge_base_gui/`. Run them with `npm test` after those files are integrated.
