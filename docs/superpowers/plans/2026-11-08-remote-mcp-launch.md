# Remote Tribal MCP Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Planning does not authorize implementation, deployment, purchase or new test authorship.

**Goal:** Launch project-specific remote Tribal MCP endpoints, created by one administrator and accessed by participants through revocable keys.

**Architecture:** One proposed DigitalOcean VM runs Caddy, a Tribal host container, MySQL and SeaweedFS. The host owns administration, key validation, streaming proxying and one loopback-bound existing Tribal worker process per project. This replaces the earlier per-project-container suggestion with a smaller process-supervision baseline; review before implementation.

**Tech Stack:** Existing Python 3.12, FastAPI/FastMCP, httpx, PyMySQL, SeaweedFS/S3, React/TypeScript/Vite, Docker Compose; add Caddy for TLS. Keep current pinned application dependencies unless implementation proves a change necessary.

**Spec:** [Remote MCP launch design](../specs/2026-11-08-remote-mcp-launch-design.md), draft for review. All unchecked items below are future work.

## Global constraints

- Only the owner creates/manages servers. Participants connect with keys.
- Preserve exactly two public MCP tools and existing note validation/publication/replay behavior.
- Keep source under `src/`, container/deployment configuration under `docker/`; do not restore Kubernetes or old authentication code.
- Every code file needs a purpose description; every Python function needs a preceding purpose comment before decorators.
- Do not author tests unless explicitly instructed. Use manual checks plus existing suites; test-step templates do not override repository instructions.
- Preserve unrelated modified/untracked work. Create an isolated implementation checkout at execution time; stage only task-owned files. Do not commit this planning work automatically.
- Proposed initial limits: three running workers, two concurrent public tool calls, 1 MiB request body, 300-second curator timeout, 360-second upstream read timeout.
- Use one host ASGI process. Public routes never reach worker `/internal/mcp` or raw storage. Workers share a trusted OS identity.
- Cloud resource creation and provider/model charges require the user's execution authorization; this plan creates none.

## Review focus

- A valid server-A key used against server B or admin/private/read APIs is rejected before a curator starts (Tasks 2 and 4).
- Duplicate create requests, concurrent starts and crash recovery produce exactly one owned worker and preserve data (Tasks 1 and 3).
- Stop/disconnect/timeout during a possibly committed update cleans up process groups and preserves same-ID retry recovery (Tasks 3, 4 and 7).
- Switching project while a graph, note read or SSE event is pending cannot show old project content (Task 5).
- A healthy HTTP process with broken Codex login or unwritable S3 never passes live launch acceptance (Tasks 6 and 7).

## File and responsibility map

All host Python files below are new under `src/tribal-mcp-server/tribal_host/`:

| File | Responsibility |
| --- | --- |
| `__init__.py`, `configuration.py` | Package and host-only settings; explicit remote-required values |
| `repository.py` | Additive MySQL management tables and transactional records |
| `authentication.py` | Admin login/session/CSRF and participant key validation |
| `supervisor.py` | Worker startup, observation, cleanup and desired-state recovery |
| `proxy.py` | Route allowlist, auth boundary, bounded requests and streaming upstream |
| `server.py` | Admin API, host lifespan/static GUI and `tribal-host` entry point |

Modify `pyproject.toml` to package `tribal_host*` and add `tribal-host = "tribal_host.server:main"`. Preserve `tribal-mcp-server` and the existing server's local behavior. Add GUI `AdminApp.tsx`, `AdminLogin.tsx`, `ServerList.tsx`, `ServerDetails.tsx`, `UserAccess.tsx`, `adminApi.ts`; adapt existing flat `main.tsx`, `App.tsx`, `api.ts`, `useKnowledgeBase.ts`, `NoteReader.tsx`, `styles.css` and `vite.config.ts` only where needed. Create `docker/Dockerfile.host`, `docker/compose.remote.yaml`, `docker/Caddyfile`, `docker/remote.env.example` and `docs/remote-mcp-launch.md`. The remote example is tracked key-free configuration; confirm existing `.gitignore` treatment and keep actual secrets outside Git.

## Task 1: Management registry and explicit host configuration

**Files:** `tribal_host/__init__.py`, `configuration.py`, `repository.py`; `pyproject.toml`.

**Interfaces:** `HostSettings.from_env() -> HostSettings`; `HostRepository.create_server(name: str, creation_id: str) -> dict`; `list_servers() -> list[dict]`; `set_desired_status(server_id: str, status: str) -> dict`; `create_user(name: str) -> dict`; `set_user_enabled(user_id: str, enabled: bool) -> dict`. Use generated server/user IDs, not arbitrary user-provided filesystem names. Repository calls are synchronous and run off the event loop.

- [ ] Define host settings for public origin, internal port, storage, admin-key digest, worker port range, limits, GUI/resources and Codex configuration. Hosted startup rejects absent credentials and an invalid public origin; local standalone settings are unchanged.
- [ ] Implement additive `tribal_host_*` tables from the spec, using PyMySQL transactions and parameterized SQL. Do not alter KB publication tables.
- [ ] Implement replay-safe create and atomic port assignment. An identical creation ID/name returns one server; changed name returns 409. Start is rejected at capacity before spawning.
- [ ] Add packaging/entrypoint declarations alongside the existing ones.
- [ ] **Verify:** in a disposable MySQL schema, issue repeated/concurrent creates, rename-display-only input checks, enable/disable and registry reload after reconnect. Confirm one server per creation ID, no duplicated reserved port, original KB rows untouched. Report actual evidence; do not use the working application's database for destructive checks.
- [ ] Suggested implementation commit: `feat: persist hosted Tribal servers and participant records`.

## Task 2: Owner session and participant keys

**Files:** `authentication.py`, `repository.py` and host API assembly in `server.py`.

**Interfaces:** `authenticate_admin(secret: str) -> bool`; `create_admin_session() -> tuple[str, str]` returning session and CSRF tokens; `require_admin(request) -> dict`; `issue_key(server_id: str, user_id: str) -> tuple[dict, str]`; `authenticate_key(server_id: str, authorization: str | None) -> dict`; `revoke_key(key_id: str) -> None`. Token generation/digest comparison uses standard-library secrets/hashlib/hmac.

- [ ] Add `tribal-host admin-secret` bootstrap mode generating a high-entropy owner secret once and its digest; never persist the raw secret in app records/logs. Wire normal startup separately.
- [ ] Implement session-token digests, eight-hour expiry, CSRF tokens, secure cookie, configured Origin validation, logout invalidation and bounded login failure tracking. The only non-Secure development mode is explicit and loopback-only.
- [ ] Implement one-server participant keys, metadata-only listings, no-store issuance, expiry/revocation and disabled-user rejection. Keys cannot be used as admin credentials and the admin secret cannot be used as a participant key.
- [ ] Register the management routes exactly as specified. Return generic login errors; suppress raw secrets, Authorization, cookies and request bodies from logs.
- [ ] **Verify:** in a disposable local host, try missing/wrong/revoked/expired/other-server keys, disabled users, admin-cookie versus key access, logout, expiry and missing/foreign Origin or CSRF on mutations. Confirm invalid requests start zero curators and no full key appears in list responses/logs.
- [ ] Suggested commit: `feat: add owner sessions and revocable server access keys`.

## Task 3: Existing project workers with bounded lifecycle

**Files:** `supervisor.py`, `configuration.py`, `server.py`.

**Interfaces:** `WorkerSupervisor.reconcile(server_id: str) -> None`; `address(server_id: str) -> str`; `observed_status(server_id: str) -> dict`; `close() -> None`. Async reconcile/close; synchronous status/address access only process-owned state. No persistent PID is authority.

- [ ] Launch the existing installed `server` module using an argument list and an explicitly constructed environment, including project ID, loopback port and the same worker's private callback. Exclude host-admin/session/key configuration.
- [ ] Coordinate create/start/stop per server and report observed states separately from durable desired state. Poll expected-project `/healthz` for up to thirty seconds before reporting running.
- [ ] Reconcile on startup; bound restart attempts and reset counters only after sixty stable seconds. Keep stopped servers stopped. A failed port bind/start releases owned resources and reports failure safely.
- [ ] Implement graceful termination and descendant cleanup. Account for Codex children using independent process groups in `runtime.py`; track owned descendants, reap processes, and verify cleanup before port reuse. Do not assume `killpg(worker_pid)` cleans up those groups. Use an existing installed process facility if available, or add one narrowly scoped process-inspection dependency with a pinned lock update if reliable descendant tracking requires it.
- [ ] **Verify:** create two workers with different IDs, verify their reported project IDs/callbacks, race start requests, interrupt a worker during a live curator, stop/restart the manager and confirm expected desired states, no duplicated workers or orphan descendants, and no admin secrets in worker environments. Use a disposable project and authorized model credentials for live checks.
- [ ] Suggested commit: `feat: supervise project workers and recover their desired state`.

## Task 4: Key-authorized MCP proxy and private dashboard reads

**Files:** `proxy.py`, `server.py`.

**Interfaces:** `proxy_mcp(request, server_id: str) -> Response`; `proxy_admin_read(request, server_id: str, kind: str, note_id: str | None = None) -> Response`. Only these handlers resolve supervisor-owned upstream addresses. A shared httpx client belongs to the host lifespan.

- [ ] Expose `/servers/{id}/mcp` with exact/slash variants and the worker-supported MCP methods. Validate keys before forwarding initialization, discovery or calls. Preserve current tool names, signatures and project-wide replay IDs.
- [ ] Allow only the graph, note and activity upstream routes for authenticated administrators. Never implement a catch-all worker proxy. Validate raw/encoded-path edge cases and preserve note IDs containing encoded slashes.
- [ ] Implement streamed response forwarding and cleanup, redirect rejection, header sanitization, configured Origin checks and trusted loopback Host. Forward all negotiated MCP protocol/session headers needed by the actual clients; do not invent compatibility from a single protocol version.
- [ ] Bound bodies and enforce the two-active-`tools/call` cap without limiting short initialization/discovery traffic. Return 429/Retry-After when full; 503 for unavailable workers; release slots on cancellation/error. Keep the host responsive while calls run. Set connect five seconds and read curator-timeout plus sixty seconds; activity SSE remains streamed with heartbeats.
- [ ] **Verify:** actual MCP discovery through the proxy; two clients calling concurrently; wrong-server key; direct/encoded attempts to reach `/internal`; malformed bodies; quota rejection; encoded note reads; long call and SSE; client disconnect and slot/process cleanup. Replay an interrupted update with the same request ID and compare the saved receipt/readback.
- [ ] Suggested commit: `feat: proxy hosted MCP traffic through scoped access keys`.

## Task 5: Minimal admin dashboard and project-aware graph

**Files:** new GUI components/API file and existing flat GUI files listed in the map.

**Interfaces:** `AdminApp` owns admin session and selected server; `ServerDetails({server})` mounts `<App key={server.id} apiBase={...} />`; `useKnowledgeBase(apiBase?: string)`; `fetchGraph(signal?: AbortSignal, apiBase?: string)`; `fetchNote(noteId: string, signal?: AbortSignal, apiBase?: string)`. Preserve the old default `/api` base for standalone mode and adapt `NoteReader` explicitly.

- [ ] Add admin login, server list/create/start/stop, named users/disable, key list/issue/revoke and one-time key display/copy. Display initial/failed states truthfully and poll lifecycle status while pending. Keep visual styling within the existing GUI.
- [ ] Add API helpers carrying same-origin cookies and CSRF on mutations; clear private UI state and close streams on logout/session failure. Keep raw keys in transient component memory only.
- [ ] Parameterize every graph/note/activity URL, thread the base through `App` and `NoteReader`, and reset/remount on project selection. Preserve source/preview, keyboard access, graph viewport behavior and independent curator trails within a project.
- [ ] Add copyable generic MCP connection instructions with bearer-header placeholders and request-ID retry rules. Advertise only clients verified during launch.
- [ ] **Verify:** build/typecheck; existing GUI suite; manually log in, create a server/user/key, switch between different graphs while reads/events are pending, revoke a key, stop a worker, logout and reload. Check no stale content or key storage; check keyboard access and a narrow viewport.
- [ ] Suggested commit: `feat: manage hosted project servers and user keys in Tribal`.

## Task 6: Reproducible host image and private local launch

**Files:** `docker/Dockerfile.host`, `docker/compose.remote.yaml`, `docker/Caddyfile`, `docker/remote.env.example`, `docs/remote-mcp-launch.md`.

- [ ] Build the existing runtime image first; do not assume it works because a Dockerfile exists. Verify installed package resources, Node/Codex version, non-root writable auth/work directories and CLI entrypoints. Resolve build issues before spending on a VM.
- [ ] Build the GUI with the existing lockfile in a Node stage, then copy built assets into a host image based on that runtime. Run `tribal-host` as the existing non-root user; enable container init/restart policy. No Docker socket or host root filesystem mounts.
- [ ] Create a standalone remote Compose file with explicit secret substitutions (no local demo credential defaults), persistent volumes and no published backend/store ports. Caddy publishes 80/443 and proxies unchanged paths with immediate streaming flush; its admin API stays private. Do not edit running local Compose defaults.
- [ ] Document both local HTTP verification mode and real HTTPS configuration. Set public origin/domain, model/auth method, optional embedding state, limits, resource paths, DNS and firewall inputs. Warn that Compose configuration renderings may contain secrets; never paste production-rendered output into reports.
- [ ] **Verify locally:** image build; installed host/worker resources; disposable storage S3 write/read; full MCP update and seed through the host; replay/readback; three-worker cap; container restart; clean shutdown/descendant cleanup. A 200 health check alone is insufficient. Start with lexical retrieval; semantic indexing is separate acceptance.
- [ ] Run existing Python suites in the isolated implementation environment and existing GUI checks. Record exact commands/results rather than expected counts. No new test files.
- [ ] Suggested commit: `build: package the remote Tribal host and HTTPS deployment`.

## Task 7: DigitalOcean launch and remote acceptance

**Files:** update `docs/remote-mcp-launch.md` with executable operator steps and actual outcomes; no secrets.

**Inputs needed at execution:** permission to create billable resources; DigitalOcean account access; owner-controlled hostname/DNS; owner admin secret; server's approved Codex credentials and spending limits. These inputs are not needed to review this plan.

- [ ] Confirm provider, VM size/region and current costs before provisioning. Proposed initial candidate: one Ubuntu VM with 2 vCPU / 4 GiB and persistent local disk; capacity is unmeasured. Create it using the provider UI/API, then install Docker Engine/Compose from official instructions.
- [ ] Configure DNS A record to the VM; publish AAAA only if IPv6 is actually configured. Restrict SSH to the owner; allow inbound 80/443. Confirm no MySQL, SeaweedFS, worker or raw host-app ports are publicly reachable, including Docker-published-port behavior.
- [ ] Transfer reviewed immutable application images/source, create private host configuration and volumes, start stores and initialize the bucket, then authenticate Codex inside the persistent auth environment. Verify authentication as the runtime UID. Official docs support `codex login --device-auth` when enabled; API-key automation is an alternative that must be checked with the pinned installed CLI. Never expose credentials to participants or bake them into images.
- [ ] Start host/Caddy and confirm trusted HTTPS. Log in as the owner, create server A and two named participants/keys. Connect two separately configured remote clients, discover exactly two tools, publish real notes and retrieve them again. Create server B and prove key/data isolation.
- [ ] Execute all eight design acceptance scenarios, including revoked/disabled keys, unauthorized read/admin/internal routes, interrupted replay, long requests, project switches, restart and process cleanup. Record pass/fail evidence and actual capacity observations. Do not mark launch complete if storage or live model calls fail.
- [ ] If authentication, domain or credentials fail, retain the functioning local milestone and report the specific blocked external check. Do not replace real curators/storage with successful-looking placeholders.
- [ ] Suggested documentation commit: `docs: record remote Tribal launch and acceptance evidence`.

## Task 8: Backup, restore and handoff

**Files:** `docs/remote-mcp-launch.md`, `docs/connecting-codex-to-tribal.md`.

- [ ] Document daily operator backup: stop/drain host writers, dump MySQL and capture SeaweedFS objects while writes are paused, restart host, encrypt and copy off-VM. Include protected handling of Codex auth material; a VM snapshot alone is not a proved application restore.
- [ ] Restore into an isolated stack and verify server records, key validation, published note reads and seed retrieval. Record recovery instructions and the last known good image tags.
- [ ] Verify rollback to the previous compatible application image without dropping management/KB tables or deleting volumes. Warn that in-flight requests may require identical-ID replay and that SSE activity is transient.
- [ ] Update connection guide with endpoint/key setup, rotation, troubleshooting and verified client-specific configuration. Add a concise limitations section covering shared OS identity, quotas, operator-paid curator execution, lexical-only launch and lack of OAuth discovery.
- [ ] Suggested commit: `docs: add remote Tribal recovery and participant connection guide`.

## Milestones and definition of done

1. **Private launch rehearsal:** image plus local host authenticates two clients, publishes/reads actual notes and preserves data across restart.
2. **First remote server:** the same behavior works over trusted HTTPS from another machine.
3. **Managed servers:** the owner creates A/B from the dashboard, assigns/revokes keys and sees separate graphs; lifecycle and isolation checks pass.
4. **Recoverable demo:** backup restoration and application rollback are exercised and documented.

Tasks 1–4 establish the management backend, Task 5 adds the owner workflow, Task 6 proves packaging before cloud spend, and Tasks 7–8 establish actual launch acceptance. The earlier 2–3 developer-day estimate was rough and unmeasured; revise it after the container/auth rehearsal and lifecycle review rather than treating it as a deadline.

## Planning verification and execution handoff

The planning turn inspects source/vault and official provider/protocol/auth documentation only. It does not run the implementation acceptance commands, build images, author tests, create cloud resources or configure credentials. Review the baseline architecture and defaults before execution. Execute natively in small tasks by default; this plan does not itself request parallel implementers.
