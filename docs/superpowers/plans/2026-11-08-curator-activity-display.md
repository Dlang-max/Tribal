# Curator activity display implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development. The user requested implementation and KB interaction by subagents on 2026-11-08.

**Goal:** Explain observed curator actions through distinct graph cues, per-run focus, latest-read markers, and confirmed publication summaries.

**Architecture:** Extend existing backend SSE envelopes with optional structured metadata. Retain compact per-run observed targets alongside existing ten-second visits. Keep the existing React Flow graph, note reader, layout and storage boundary.

**Tech Stack:** Existing Python/FastMCP backend and React/TypeScript/Vite frontend; no new dependencies.

**Spec:** The user's request to implement the display ideas, subsequently narrowed by the explicit instruction to remove the timeline feature. Keep action distinctions, focus, latest observed reads and receipt-backed summaries. Do not ship an action timeline or retain event history for one. The user also requested removing the visible Search/Read/Traverse/Publish legend; retain the actual action visuals. The existing KG remains the main canvas.

## Global constraints

- Do not write tests unless explicitly instructed to do so. Run existing checks and manual probes.
- Preserve all existing uncommitted work, including graph labels, spacing and dragging. Work in the current feature checkout and leave changes uncommitted.
- Every code file begins with a purpose description; every Python function has a preceding one-line purpose comment before decorators.
- Show observed server curator actions only; do not imply model reasoning, caller activity, or fabricated graph traversals.
- Activity is browser-session-only and best-effort; make stream gaps/reconnect limitations visible. Do not include a timeline.
- Use names, shapes and text as well as color, accessible controls and reduced-motion support.

## Shared event contract

Existing required ActivityEvent fields remain unchanged. Add optional fields:

- `action`: `search | read | traverse | spec | publish`.
- `target_node_id`: stable ID of the actual read/traversal target (omit when absent).
- `run_kind`: `context | update`.
- `publication`: `{ status: updated | unchanged | needs_information, notes: [{ action: created | updated | archived, path: string, note_id?: string, title?: string }] }`.

Publication notes come from actual saved receipts, not requested changes/model claims. Resolve IDs/titles through graph snapshots when possible; archived/unavailable notes remain readable paths without a broken open control. Emit publication on successful graph changes and checked final update outcomes. Preserve actual saved receipts on failure after publication. Failed/invalid intermediate applies must not imply successful publication. Optional fields permit old events to remain renderable as generic visits.

## Review focus

1. Concurrent and overlapping actions: per-run state, focus and fades remain independent.
2. Old/malformed/out-of-order events: optional metadata is validated; last-read and receipts survive later generic lifecycle events.
3. Archives, unchanged outcomes and failure after save: report confirmed changes accurately even when nodes cannot be opened.
4. Reconnects, long sessions and pruned runs: bounds apply to associated target state, missing activity is explicit, stale focus can be cleared.
5. Narrow screens, keyboard use, reduced motion and opening notes: no lost viewport/focus or horizontal overflow.

### Task 1: Structured backend activity

**Files:** `src/tribal-mcp-server/tribal_kb/runtime.py` (and existing backend README if needed).

- [x] Add optional metadata to emitted envelopes while retaining existing fields and tool permissions.
- [x] Emit distinct action names and actual target IDs for searches, reads, verified traversals, spec reads and publications.
- [x] Enrich saved receipt notes with graph IDs/titles when available; preserve receipt truth across completion/failure.
- [x] Run existing runtime checks; report exact commands/results. Consult the KB first and submit verified findings afterward using a unique replay ID.

### Task 2: GUI activity experience

**Files:** `src/knowledge-base-gui/{types.ts,api.ts,activity.ts,useKnowledgeBase.ts,ActivityPanel.tsx,KnowledgeGraph.tsx,App.tsx,styles.css,README.md}`; a small focused source helper/component may be added if necessary.

- [x] Validate optional metadata; retain compact observed target sets, latest observed read and latest publication, following the existing latest 20 completed runs lifecycle. Do not retain full event history or conflate candidate search results with reads.
- [x] Add keyboard-accessible run focus/reset and receipt-backed outcome summaries. Latest read and publication note references offer graph highlighting and explicit Open controls. Use graph titles where available; show unavailable paths as text. No timeline controls.
- [x] Distinguish search outline, read fill, traversal direction pulse and publication confirmation. Retain concurrent overlays and ten-second fades. Show latest-read name tags without large opaque cards; use focus to reduce clutter.
- [x] Wire focus to dim unrelated graph content without moving the viewport. Latest-read and publication references highlight notes; separate open controls read actual notes. Highlight returns to the graph when the reader is open.
- [x] Keep scope/gap language visible and preserve note-reader stability and existing graph interaction.
- [x] Run existing GUI unit checks, typecheck/build and browser checks. Consult KB first and submit verified findings afterward.

### Task 3: Integration verification and independent review

- [x] Review task-specific diffs against pre-task snapshots so existing dirty changes are preserved.
- [x] Run appropriate combined checks and a controlled browser probe of new metadata, concurrent run focus, note highlighting/opening, archive handling and reduced motion/mobile layout.
- [x] Fix material issues, update plan checkboxes and README, and submit final verified evidence to Tribal KB. No commit, push, or deployment is requested.
