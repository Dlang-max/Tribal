# Single-project Hosting Implementation Plan

> Execute inline in this session under superpowers:executing-plans. User already
> authorizes deployment, MCP bearer validation and a public dashboard/read API.

**Goal:** Run the existing Tribal app/frontend over HTTPS with bearer-authenticated MCP.
**Architecture:** Existing runtime plus built React, Caddy edge, existing private stores.
**Tech Stack:** Python/FastAPI/FastMCP, React/Vite, Docker Compose, Caddy.
**Spec:** ../specs/2026-11-08-single-project-hosting-design.md

## Global constraints

Preserve unrelated edits; deploy a filtered current-source snapshot, not stale HEAD.
No new tests, commits, pushes, storage replacement or laptop model-auth transfer.
Use the current feature checkout because deployment must include its latest user
changes; limit edits to authentication, packaging, deployment config and docs.

## Review focus

Invalid/duplicate auth must fail before dispatch. Protect both MCP slash forms.
Public browser APIs must continue to stream; private routes never reach Caddy.
No secret may enter the image/context/frontend/logs or curator environment.
Keep the existing copied data, network and volumes; preserve replay semantics.
Process health alone does not prove live curator/model/storage operation.

## Tasks

- [x] Add optional bearer settings and public MCP transport middleware; run existing backend checks and manual auth requests.
- [x] Package React using its lockfile, add hosted Compose/Caddy config, build filtered source and run existing frontend checks.
- [x] Transfer image/config privately and start app/Caddy against existing stores; verify TLS/routes.
- [ ] Complete fresh server Codex login after the account Security setting is enabled.
- [ ] Exercise real hosted discovery/seed/update/readback/replay and restart persistence; document actual results and update Tribal KB.
