# Live knowledge explorer

Dots grow with the number of distinct connected notes, counting incoming and outgoing links together. Reciprocal links count once; growth is capped to keep the graph readable. Curator visits color the dots themselves, with concurrent visits sharing the fill in colored sections.

Note labels stay at a readable screen size with a subtle text shadow and up to two lines. Labels that would overlap another label or dot are hidden, prioritizing the active and most connected notes. Below 65% zoom, labels disappear; hover or keyboard focus reveals a dot's label at any zoom. Full titles remain available in the dot's tooltip and accessible name.

Opening an archived note shows an “Archived” badge beside its title in the reader, in both Preview and Source views. This requires the backend version that includes lifecycle status in note responses.

Nodes automatically spread apart when their dots or label areas overlap, including after zooming or loading new notes, then stop moving. Reduced-motion preferences apply the settled spacing without animation. Hovered, focused and most recently dragged dots stay stationary while their neighbors make room; spacing pauses during dragging and while reading a note. Drag dots to arrange the graph. Positions are retained through graph refreshes, with overlapping neighbors adjusted as needed; reloading restores the automatic layout. Click a dot to read its note. Arrangement only changes the local view.

Run the project server on `127.0.0.1:8000`, then from this directory:

```sh
npm ci
npm run dev
```

Vite proxies `/api` to the local server. The viewer requests `/api/graph`, loads selected note contents from `/api/notes/{encoded-note-id}`, and subscribes to `/api/activity` with native EventSource. Notes and link IDs come directly from the server. Curator names, task descriptions, colors and statuses come from observed server activity. No example graph or simulated curator is supplied when the server is unavailable.

`npm run build` typechecks and writes `dist/`; configure the server's optional GUI directory to this absolute directory when serving the built viewer. `npm run preview` previews assets only and does not proxy the API; use development mode or the backend for live data.

The full-height graph displays notes as small labeled dots and actual wikilinks as thin straight lines. Pan, zoom and fit controls are read-only. Tab to a dot and press Enter or Space, or click it, to open a rendered Markdown preview. Preview supports headings, lists, tables, task lists, quotes, links and code blocks, omitting YAML frontmatter. The Source control shows the complete original text, including frontmatter, with wrapped long lines. Raw HTML is skipped and standard Markdown URLs use the renderer’s default sanitization. Known `[[note/path|label]]` wikilinks open the target note within the reader; unresolved links remain text, and code examples stay literal. Loading and failure states include retry. “Back to graph” or Escape returns to the previous graph position and zoom, with keyboard focus restored to the selected dot. The curator activity list stays visible beside the graph or reader, and stacks below on mobile. Opening a note in the viewer does not create curator activity.

Each reported node or edge visit fades independently over ten seconds using its server timestamp. A visited dot fills with the curator's color; a traversed edge is colored along its existing line. Concurrent runs share a dot's fill or an edge's length in colored sections, keeping each run visible without halos or offset strokes. Completion and failure preserve existing trails until expiry. Stream reconnects refresh the graph snapshot; previous activity is not replayed by the server. The activity panel retains working runs and the latest 20 finished runs.

Structured curator events distinguish search candidates with an outline, actual reads with fill, verified link traversal with a directional pulse and a static chevron, and confirmed publication with a check. Generic events from older servers keep their original visit rendering. Search results never become latest reads; a verified traversal reads its target. Small plain-text tags identify the latest observed read for working runs, or for the focused run after completion. Reduced motion keeps the chevron while stopping the pulse.

Focus a run to dim unrelated graph content and other curators without changing graph positions or the viewport; “Show all runs” clears focus. Clicking a file name in the latest read or publication summary opens its note directly and highlights its graph node for when you return. The latest read and confirmed receipts survive later lifecycle messages and delayed events. Focus retains up to 200 observed node IDs and 200 edge IDs per retained run independently of fading trails. Publication summaries count actual created/updated/archived receipts, retain saved changes after failure, and show unavailable paths as text. Archived notes can still be opened when present in the current graph.

Observed activity exists only in memory for this browser session and is best-effort, not a durable audit log. Working runs remain; only the latest 20 completed runs remain once their trails expire. Their associated target sets and receipts are pruned together. A persistent history-gap notice remains after disconnects or unreadable events, even when the live connection recovers. The UI observes server curator actions, not the caller's private activity or model reasoning. Structured details require the updated backend process; an already running older backend must be restarted to emit them.

Independent tests live in `../../tests/knowledge_base_gui/`. Run them with `npm test` after those files are integrated.

Highlighted outgoing edges render above ordinary links. Active curator trails render above both and return to their normal layer after fading.
