# Live knowledge graph tests

Install the GUI package's dependencies, then run its independent component suite:

```sh
npm ci --ignore-scripts --prefix src/knowledge-base-gui
npm test --prefix src/knowledge-base-gui
```

The suite renders the real App and React Flow components. Only browser layout APIs, HTTP responses, EventSource, and the clock are controlled. No backend, OpenAI account, or network data is required.

Run the native Chromium checks from the repository root:

```sh
src/knowledge-base-gui/node_modules/.bin/playwright install chromium
src/knowledge-base-gui/node_modules/.bin/playwright test --config tests/knowledge_base_gui/playwright.config.ts
```

An existing Chromium executable can be selected with `TRIBAL_CHROMIUM_EXECUTABLE`. The browser tests start the Vite development server on port 4187 and control `/api/graph`, the EventSource boundary, and time; no backend is needed. They verify rendered SVG path geometry, independent concurrent trails, graph inspection/zoom, and 390px layout with reduced motion enabled.

`TRIBAL_GUI_SOURCE_DIR` optionally points both configurations at a different GUI source package for isolated source/test worktrees. Otherwise all imports and tools resolve from this checkout's source package and its local dependency install. Tests remain outside the source package in accordance with repository guidance.
