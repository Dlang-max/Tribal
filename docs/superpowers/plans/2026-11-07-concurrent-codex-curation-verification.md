# Concurrent Codex curation verification

The implementation is merged into the original checkout `/home/daniel-lang/Desktop/UB_Hacking_2026/Tribal`, current branch `feat/kubernetes-project-mcp-demo`, at source commit `909032c`. Development used `feat/concurrent-codex-kb-curation` in an isolated worktree.

The original uncommitted changes, including the later flat server layout, are incorporated. An exact pre-merge snapshot remains on `snapshot/original-checkout-before-curation-merge` at `aa0f172`, plus a named Git stash backup. The old Kubernetes server deletions were preexisting user changes, preserved by the initial snapshot.

## Implemented

- Two public MCP tools; concurrent server-side Codex curators with active run tokens and five private KB tools. Context runs cannot write.
- Whole-vault Markdown validation, revision checks, immutable SeaweedFS S3 objects, transactional MySQL manifests/history, and durable request replay.
- Optional OpenAI `text-embedding-3-small` indexing and lexical lookup without a key. Embeddings stay outside notes and do not gate valid publication.
- Graph snapshots, broadcast SSE, and a React GUI showing named curators, current actions, and independent colored node/edge trails fading over ten seconds.
- Flat server source at `src/tribal-mcp-server/server.py` and `src/tribal-mcp-server/tribal_kb/`; GUI at `src/knowledge-base-gui/`.
- Setup in [Connect Codex to Tribal](../../connecting-codex-to-tribal.md); architecture diagram in the sibling Obsidian vault at `Project/Tribal Project Diagram.md`.

## Verification actually run

- Final complete Python suite in the original checkout: **377 passed**, two upstream websocket deprecation warnings, **52.96 seconds**. The flat-layout implementor separately ran all 377 in 51.72 seconds.
- Original-checkout GUI: **20 Vitest tests**, **3 native Chromium tests**, production build and TypeScript checks passed. Browser checks cover overlapping trails, persistent graph measurement, mobile/reduced motion, and read-only keyboard inspection.
- Assembled smoke: real KnowledgeBaseService/native validator with eleven canonical note types, controlled object/catalog adapters and an actual controlled child executable, public/private HTTP MCP, graph endpoint, two SSE subscribers, verified edge traversal, update/durable replay, and revision two passed.
- Final no-op receipt regression: five actual service/runtime HTTP cases failed before the fix and pass afterward. Intermediate empty/already-matching applies no longer finalize public requests; final needs-information/no-change messages survive retry. Actual publications retain atomic receipts and recover after child failure.
- Final flat-layout wheel built and installed into a fresh environment. Installed resource discovery, all eleven note specs and validator, curator resources, console/module/direct-script CLI modes, and explicit static index/assets serving passed.
- Original-checkout editable installation, dependency check, compileall, whitespace check, and Docker Compose configuration check passed. The obsolete Kubernetes Python client from the old server was removed from the local virtual environment because it conflicted with Boto3’s dependency pin; no current dependency requires it.
- Python comment audit: **22 files and 251 functions**, no missing module descriptions or preceding purpose comments.
- Independent source and independent test review gates passed for storage, runtime, and GUI. The final whole-branch review, focused receipt fix review, and flat-layout integration review are **SPEC GREEN, QUALITY GREEN**; see [review](2026-11-07-concurrent-codex-curation-review.md).

A local trailing `k` appeared in Vite configuration during post-merge checks and blocked the first GUI run. Its bytes were saved at `/tmp/tribal-vite-config-before-restore-lvdalw75.ts`, and the exact reviewed config was restored before the successful build/browser rerun. No unreviewed application change was retained.

## Boundaries and operator steps

No live OpenAI embedding/model request, authenticated Codex curator run, Docker image build, or live MySQL/SeaweedFS deployment was executed. Controlled adapter/HTTP/process checks do not establish live provider or service compatibility; the Docker daemon was unavailable. Start Docker/storage and configure the server’s Codex authentication following the setup guide. The embedding key can be supplied later. No push or deployment was performed.

The curator relies on submitted evidence and stored notes; Git/GitHub adapters, automatic client trigger hooks, and Obsidian export/sync remain outside this implementation. SSE is best effort in one trusted local server process.

## Implementation decisions

- Use isolated source/test/review worktrees as requested, preserve the original dirty state, then merge locally when explicitly requested. Keep backup snapshot and stash; do not push.
- Parallel authors work in disjoint worktrees. Source and independent test lanes are reviewed separately.
- Coordinate revision-checked publication rather than entire curator runs, matching the accepted concurrent-agent design.
- Keep embeddings optional, retain lexical search, and supply no fake vectors, production memory database, or simulated production curator.
- Report controlled verification separately from live provider/deployment verification. Hosted authentication, durable activity replay, distributed workers, source adapters, and vault synchronization were not added for the hackathon.
